"""Poll Open Library Search and publish one Kafka message per document."""
import json
import logging
import time
from datetime import datetime, timezone
from kafka import KafkaProducer
from config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC_RAW,
    OPENLIBRARY_MAX_PAGES_PER_CYCLE,
    POLL_CYCLE_SLEEP_SEC,
)
from openlibrary_client import filter_fulltext_docs, iter_search_pages, num_found

logger = logging.getLogger(__name__)

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
    acks="all",
    retries=5,
    request_timeout_ms=50_000,
)


def _kafka_key(doc: dict) -> bytes | None:
    work_key = doc.get("key")
    if not work_key:
        return None
    return str(work_key).encode("utf-8")

def poll_loop() -> None:
    """
    Outer loop: bounded pages per cycle, then sleep.
    Inner: each Search API page -> filter docs -> one message per doc; flush after each page.
    """
    while True:
        cycle_sent = 0
        for page in iter_search_pages(
            max_pages=OPENLIBRARY_MAX_PAGES_PER_CYCLE,
        ):
            raw_docs = page.get("docs") or []
            docs = filter_fulltext_docs(raw_docs)
            page_sent = 0
            for doc in docs:
                payload = {
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "doc": doc,
                }
                key = _kafka_key(doc)
                if key is not None:
                    producer.send(
                        KAFKA_TOPIC_RAW,
                        key=key,
                        value=payload,
                    )
                else:
                    producer.send(KAFKA_TOPIC_RAW, value=payload)
                page_sent += 1
            producer.flush()
            cycle_sent += page_sent
            logger.info(
                "kafka page published: start=%s numFound=%s raw_docs=%s filtered=%s sent=%s topic=%s",
                page.get("start"),
                num_found(page),
                len(raw_docs),
                len(docs),
                page_sent,
                KAFKA_TOPIC_RAW,
            )

        logger.info(
            "poll cycle finished: total_messages=%s max_pages=%s; sleeping %.1fs",
            cycle_sent,
            OPENLIBRARY_MAX_PAGES_PER_CYCLE,
            POLL_CYCLE_SLEEP_SEC,
        )
        time.sleep(POLL_CYCLE_SLEEP_SEC)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        poll_loop()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down gracefully.")
        producer.flush()
        producer.close()
    except Exception:
        logger.exception("Unhandled exception in poll loop")
        producer.flush()
        producer.close()
        raise
