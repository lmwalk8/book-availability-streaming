"""
Unit tests for parse + hash payload.

Run from pyflink/jobs:

    pytest test_parse_hash.py -q

Or from repo root:

    pytest pyflink/jobs/test_parse_hash.py -q
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `pytest pyflink/jobs/test_parse_hash.py` from repo root.
_JOBS_DIR = Path(__file__).resolve().parent
if str(_JOBS_DIR) not in sys.path:
    sys.path.insert(0, str(_JOBS_DIR))

from constants import EBOOK_ACCESS_PUBLIC, FALLBACK_TITLE, PAYLOAD_HASH_LENGTH
from hash_payload import hash_payload
from openlibrary_row import OpenLibraryRow
from parse_kafka import parse_kafka_value


def _sample_envelope(**doc_overrides) -> dict:
    doc = {
        "key": "/works/OL82567W",
        "title": "The Great Gatsby",
        "author_name": ["F. Scott Fitzgerald"],
        "ebook_access": "public",
        "has_fulltext": True,
    }
    doc.update(doc_overrides)
    return {
        "fetched_at": "2026-07-26T23:00:00+00:00",
        "doc": doc,
    }

def test_hash_payload_is_stable_and_length_64():
    doc = _sample_envelope()["doc"]
    h1 = hash_payload(doc)
    h2 = hash_payload(dict(reversed(list(doc.items()))))  # different insert order
    assert h1 == h2
    assert len(h1) == PAYLOAD_HASH_LENGTH
    assert all(c in "0123456789abcdef" for c in h1)

def test_hash_changes_when_doc_field_changes():
    doc_a = _sample_envelope()["doc"]
    doc_b = {**doc_a, "title": "The Great Gatsby (annotated)"}
    assert hash_payload(doc_a) != hash_payload(doc_b)

def test_parse_kafka_value_happy_path():
    envelope = _sample_envelope()
    raw = json.dumps(envelope)
    row = parse_kafka_value(raw)

    assert row is not None
    assert isinstance(row, OpenLibraryRow)
    assert row.work_key == "/works/OL82567W"
    assert row.title == "The Great Gatsby"
    assert row.author_name == "F. Scott Fitzgerald"
    assert row.ebook_access == EBOOK_ACCESS_PUBLIC
    assert row.ingested_at == datetime(2026, 7, 26, 23, 0, 0, tzinfo=timezone.utc)
    assert row.payload_hash == hash_payload(envelope["doc"])

def test_parse_kafka_value_accepts_bytes():
    raw = json.dumps(_sample_envelope()).encode("utf-8")
    row = parse_kafka_value(raw)
    assert row is not None
    assert row.work_key == "/works/OL82567W"

def test_parse_kafka_value_accepts_fetched_at_as_datetime():
    envelope = _sample_envelope()
    envelope["fetched_at"] = "2026-07-26T23:00:00Z"
    row = parse_kafka_value(json.dumps(envelope))
    assert row is not None
    assert row.ingested_at == datetime(2026, 7, 26, 23, 0, 0, tzinfo=timezone.utc) 

def test_parse_kafka_value_accepts_author_name_as_string():
    envelope = _sample_envelope(author_name="F. Scott Fitzgerald")
    row = parse_kafka_value(json.dumps(envelope))
    assert row is not None
    assert row.author_name == "F. Scott Fitzgerald"

def test_parse_joins_author_list():
    envelope = _sample_envelope(author_name=["A", "B"])
    row = parse_kafka_value(json.dumps(envelope))
    assert row is not None
    assert row.author_name == "A, B"

def test_parse_missing_title_uses_fallback():
    envelope = _sample_envelope(title="")
    row = parse_kafka_value(json.dumps(envelope))
    assert row is not None
    assert row.title == FALLBACK_TITLE

def test_parse_drops_non_public_ebook_access():
    envelope = _sample_envelope(ebook_access="borrowable")
    assert parse_kafka_value(json.dumps(envelope)) is None

def test_parse_drops_missing_key():
    envelope = _sample_envelope()
    del envelope["doc"]["key"]
    assert parse_kafka_value(json.dumps(envelope)) is None

def test_parse_drops_invalid_json():
    assert parse_kafka_value("{not-json") is None

def test_parse_drops_missing_envelope_keys():
    assert parse_kafka_value(json.dumps({"doc": {"key": "/works/OL1W"}})) is None
