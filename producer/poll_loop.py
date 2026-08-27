"""Poll Open Library Search and publish one Kafka message per document."""
import json
import logging
import time
from datetime import datetime, timezone
from kafka import KafkaProducer
from config import (
    INGESTION_POLLER_JOB_NAME,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC_RAW,
    OPENLIBRARY_MAX_PAGES_PER_CYCLE,
    OPENLIBRARY_PAGE_SIZE,
    POLL_CYCLE_SLEEP_SEC,
)
from openlibrary_client import filter_fulltext_docs, iter_search_pages, num_found
from poller_state import get_next_page, set_next_page

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


def _past_end(page_payload: dict, page_num: int) -> bool:
    """True when this page is empty or past numFound."""
    docs = page_payload.get("docs") or []
    if not docs:
        return True
    total = num_found(page_payload)
    if total is None:
        return False
    # Open Library start is 0-based offset of first doc on this page.
    start = page_payload.get("start")
    if start is not None:
        return int(start) >= total
    return (page_num - 1) * OPENLIBRARY_PAGE_SIZE >= total


def poll_loop() -> None:
    """
    Outer loop: resume from ingestion_poller page, fetch up to N pages, then sleep.
    After each successful Kafka flush, advance the cursor (wrap to 1 at end of results).
    """
    while True:
        start_page = get_next_page(INGESTION_POLLER_JOB_NAME)
        cycle_sent = 0
        pages_done = 0

        for page_num, page in iter_search_pages(
            start_page=start_page,
            max_pages=OPENLIBRARY_MAX_PAGES_PER_CYCLE,
        ):
            if _past_end(page, page_num):
                logger.info(
                    "reached end of results at page=%s start=%s numFound=%s; wrapping to page 1",
                    page_num,
                    page.get("start"),
                    num_found(page),
                )
                set_next_page(INGESTION_POLLER_JOB_NAME, 1)
                break

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
            pages_done += 1

            # Persist next page only after this page was published.
            set_next_page(INGESTION_POLLER_JOB_NAME, page_num + 1)

            logger.info(
                "kafka page published: page=%s start=%s numFound=%s raw_docs=%s filtered=%s sent=%s topic=%s next_page=%s",
                page_num,
                page.get("start"),
                num_found(page),
                len(raw_docs),
                len(docs),
                page_sent,
                KAFKA_TOPIC_RAW,
                page_num + 1,
            )

        logger.info(
            "poll cycle finished: start_page=%s pages_done=%s total_messages=%s max_pages=%s; sleeping %.1fs",
            start_page,
            pages_done,
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
