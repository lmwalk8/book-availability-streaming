"""
Kafka -> parse -> stateful dedupe -> sink-shaped rows -> PostgreSQL.
"""
import os
from datetime import datetime
import psycopg2

from pyflink.common import Row, SimpleStringSchema, Types, WatermarkStrategy
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaOffsetsInitializer, KafkaSource
from pyflink.datastream.functions import FlatMapFunction, MapFunction, RuntimeContext
from pyflink.datastream.state import ValueStateDescriptor

from openlibrary_row import OpenLibraryRow
from parse_kafka import parse_kafka_value

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
KAFKA_TOPIC_RAW = os.getenv("KAFKA_TOPIC_RAW", "openlibrary.search.raw")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "flink-openlibrary")
KAFKA_STARTING_OFFSETS = os.getenv("KAFKA_STARTING_OFFSETS", "earliest")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "book_streaming")
POSTGRES_USER = os.getenv("POSTGRES_USER", "book_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "book_streaming")

# Shared by to-sink-row map output_type (field order = INSERT columns).
SINK_TYPE_INFO = Types.ROW_NAMED(
    ["work_key", "title", "author_name", "ebook_access", "ingested_at", "payload_hash"],
    [
        Types.STRING(),
        Types.STRING(),
        Types.STRING(),
        Types.STRING(),
        Types.STRING(),
        Types.STRING(),
    ],
)

INSERT_SQL = (
    "INSERT INTO work_events "
    "(work_key, title, author_name, ebook_access, ingested_at, payload_hash) "
    "VALUES (%s, %s, %s, %s, %s::timestamptz, %s) "
    "ON CONFLICT (work_key, payload_hash) DO NOTHING"
)


class DedupeByPayloadHash(FlatMapFunction):
    """
    Per work_key, emit only when payload_hash is new or changed.
    Relies on key_by(work_key) and checkpoints for state durability.
    """

    def open(self, runtime_context: RuntimeContext):
        self._last_hash = runtime_context.get_state(
            ValueStateDescriptor("last_payload_hash", Types.STRING())
        )

    def flat_map(self, row: OpenLibraryRow):
        previous = self._last_hash.value()
        if previous == row.payload_hash:
            return
        self._last_hash.update(row.payload_hash)
        yield row


def row_to_sink_row(row: OpenLibraryRow) -> Row:
    """
    Flat record matching work_events insert column order (minus id):
    work_key, title, author_name, ebook_access, ingested_at, payload_hash
    """
    ingested_at = (
        row.ingested_at.isoformat()
        if isinstance(row.ingested_at, datetime)
        else str(row.ingested_at)
    )
    # Nullable TEXT in Postgres; coerce blank strings to SQL NULL.
    author_name = row.author_name
    if author_name is not None and not str(author_name).strip():
        author_name = None

    return Row(
        row.work_key,
        row.title,
        author_name,
        row.ebook_access,
        ingested_at,
        row.payload_hash,
    )


class PostgresWriteMap(MapFunction):
    """
    Batched INSERT via psycopg2.
    """

    def __init__(
        self,
        host: str,
        port: str,
        database: str,
        user: str,
        password: str,
        batch_size: int = 1,
    ):
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        # Default 1 so idle streams still land rows (close() only runs on cancel).
        self._batch_size = max(1, batch_size)
        self._conn = None
        self._cur = None
        self._batch: list[tuple] = []

    def open(self, runtime_context: RuntimeContext):
        self._conn = psycopg2.connect(
            host=self._host,
            port=self._port,
            dbname=self._database,
            user=self._user,
            password=self._password,
        )
        self._conn.autocommit = False
        self._cur = self._conn.cursor()
        self._batch = []

    def map(self, value):
        self._batch.append(
            (
                value[0],
                value[1],
                value[2],
                value[3],
                value[4],
                value[5],
            )
        )
        if len(self._batch) >= self._batch_size:
            self._flush()
        return value

    def _flush(self):
        if not self._batch or self._cur is None or self._conn is None:
            return
        self._cur.executemany(INSERT_SQL, self._batch)
        self._conn.commit()
        self._batch.clear()

    def close(self):
        try:
            self._flush()
        finally:
            if self._cur is not None:
                self._cur.close()
                self._cur = None
            if self._conn is not None:
                self._conn.close()
                self._conn = None


def starting_offsets():
    mode = KAFKA_STARTING_OFFSETS.strip().lower()
    if mode == "latest":
        return KafkaOffsetsInitializer.latest()
    if mode == "earliest":
        return KafkaOffsetsInitializer.earliest()
    raise ValueError(
        f"KAFKA_STARTING_OFFSETS must be 'earliest' or 'latest', got {mode!r}"
    )


def build_kafka_source():
    return (
        KafkaSource.builder()
        .set_bootstrap_servers(KAFKA_BOOTSTRAP_SERVERS)
        .set_topics(KAFKA_TOPIC_RAW)
        .set_group_id(KAFKA_GROUP_ID)
        .set_starting_offsets(starting_offsets())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )


def transform_stream(raw_stream):
    """
    Kafka JSON strings -> OpenLibraryRow -> dedupe by (work_key, payload_hash)
    -> JDBC-shaped rows.
    """
    rows = (
        raw_stream.map(lambda raw: parse_kafka_value(raw))
        .name("parse")
        .filter(lambda row: row is not None)
        .name("drop-bad")
    )
    deduped = (
        rows.key_by(lambda row: row.work_key)
        .flat_map(DedupeByPayloadHash())
        .name("dedupe-by-payload-hash")
    )
    return deduped.map(row_to_sink_row, output_type=SINK_TYPE_INFO).name("to-sink-row")


def build_postgres_writer():
    return PostgresWriteMap(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        batch_size=1,
    )


def openlibrary_to_postgresql():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)
    env.enable_checkpointing(30_000)

    source = build_kafka_source()
    stream = env.from_source(
        source, WatermarkStrategy.no_watermarks(), "openlibrary-kafka"
    )
    sink_rows = transform_stream(stream)

    # Write in map UDF, then discard + print as a no-op Flink sink (required).
    (
        sink_rows.map(build_postgres_writer(), output_type=SINK_TYPE_INFO)
        .name("postgres-write")
        .filter(lambda _: False)
        .name("discard")
        .print()
    )
    env.execute("openlibrary-kafka-to-postgresql")


if __name__ == "__main__":
    openlibrary_to_postgresql()
