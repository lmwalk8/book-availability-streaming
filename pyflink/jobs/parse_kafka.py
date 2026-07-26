"""Parse Kafka JSON values from the Open Library producer into OpenLibraryRow."""
import json
import logging
from datetime import datetime, timezone
from typing import Any

from constants import (
    DOC_AUTHOR_NAME,
    DOC_EBOOK_ACCESS,
    DOC_KEY,
    DOC_TITLE,
    EBOOK_ACCESS_PUBLIC,
    ENVELOPE_DOC,
    ENVELOPE_FETCHED_AT,
    FALLBACK_TITLE,
)
from hash_payload import hash_payload
from openlibrary_row import OpenLibraryRow

logger = logging.getLogger(__name__)


def _normalize_author_name(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        parts = [str(p).strip() for p in raw if p is not None and str(p).strip()]
        return ", ".join(parts) if parts else None
    text = str(raw).strip()
    return text or None

def _parse_fetched_at(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def parse_kafka_value(raw: bytes | str) -> OpenLibraryRow | None:
    """
    Turn one Kafka message value into a work_events-ready row.

    Returns None for malformed / non-public payloads (drop policy for Flink).
    """
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("skipping non-utf8 kafka value")
            return None
    else:
        text = raw

    try:
        envelope = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("skipping invalid json kafka value")
        return None

    if not isinstance(envelope, dict):
        logger.warning("skipping non-object kafka value")
        return None

    if ENVELOPE_FETCHED_AT not in envelope or ENVELOPE_DOC not in envelope:
        logger.warning("skipping envelope missing fetched_at/doc")
        return None

    doc = envelope[ENVELOPE_DOC]
    if not isinstance(doc, dict):
        logger.warning("skipping envelope where doc is not an object")
        return None

    work_key = doc.get(DOC_KEY)
    if work_key is None or not str(work_key).strip():
        logger.warning("skipping doc without key")
        return None
    work_key = str(work_key).strip()

    title_raw = doc.get(DOC_TITLE)
    if title_raw is None or not str(title_raw).strip():
        title = FALLBACK_TITLE
    else:
        title = str(title_raw).strip()

    ebook_access = doc.get(DOC_EBOOK_ACCESS)
    if ebook_access != EBOOK_ACCESS_PUBLIC:
        logger.debug("skipping non-public ebook_access=%s key=%s", ebook_access, work_key)
        return None

    ingested_at = _parse_fetched_at(envelope[ENVELOPE_FETCHED_AT])
    if ingested_at is None:
        logger.warning("skipping invalid fetched_at for key=%s", work_key)
        return None

    return OpenLibraryRow(
        work_key=work_key,
        title=title,
        author_name=_normalize_author_name(doc.get(DOC_AUTHOR_NAME)),
        ebook_access=EBOOK_ACCESS_PUBLIC,
        ingested_at=ingested_at,
        payload_hash=hash_payload(doc),
    )
