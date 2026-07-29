"""
Kafka -> parse -> stateful dedupe -> sink-shaped tuples -> print.
"""
import os
from datetime import datetime

from pyflink.common import SimpleStringSchema, Types, WatermarkStrategy
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaOffsetsInitializer, KafkaSource
from pyflink.datastream.functions import FlatMapFunction, MapFunction, RuntimeContext
from pyflink.datastream.state import ValueStateDescriptor

from openlibrary_row import OpenLibraryRow
from parse_kafka import parse_kafka_value

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
KAFKA_TOPIC_RAW = os.getenv("KAFKA_TOPIC_RAW", "openlibrary.search.raw")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "flink-openlibrary-c2")
KAFKA_STARTING_OFFSETS = os.getenv("KAFKA_STARTING_OFFSETS", "earliest")


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

def row_to_sink_tuple(row: OpenLibraryRow) -> tuple:
    """
    Flat record matching work_events insert column order (minus id):
    work_key, title, author_name, ebook_access, ingested_at, payload_hash
    """
    ingested = row.ingested_at
    if isinstance(ingested, datetime):
        ingested_at = ingested.isoformat()
    else:
        ingested_at = str(ingested)
    return (
        row.work_key,
        row.title,
        row.author_name,
        row.ebook_access,
        ingested_at,
        row.payload_hash,
    )

class ToSinkTuple(MapFunction):
    def map(self, row: OpenLibraryRow):
        return row_to_sink_tuple(row)

def transform_stream(raw_stream):
    """
    Kafka JSON strings -> OpenLibraryRow -> dedupe by (work_key, payload_hash)
    -> JDBC-shaped tuples.
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
    return deduped.map(ToSinkTuple()).name("to-sink-tuple")

def openlibrary_to_postgresql():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)
    env.enable_checkpointing(30_000)

    source = build_kafka_source()
    stream = env.from_source(
        source, WatermarkStrategy.no_watermarks(), "openlibrary-kafka"
    )
    sink_rows = transform_stream(stream)
    sink_rows.print()
    env.execute("openlibrary-kafka-parse-print")

if __name__ == "__main__":
    openlibrary_to_postgresql()
