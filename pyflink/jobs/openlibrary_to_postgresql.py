import os
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.common import SimpleStringSchema, WatermarkStrategy
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer
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

def openlibrary_to_postgresql():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)
    env.enable_checkpointing(30_000)

    source = build_kafka_source()

    stream = env.from_source(source, WatermarkStrategy.no_watermarks(), "openlibrary-kafka")
    parsed = stream.map(lambda raw: parse_kafka_value(raw)).name("parse")
    rows = parsed.filter(lambda row: row is not None).name("drop-bad")
    rows.print()
    env.execute("openlibrary-kafka-parse-print")

if __name__ == "__main__":
    openlibrary_to_postgresql()
