"""Stable SHA-256 hex digest for Open Library doc payloads."""
import hashlib
import json
from typing import Any

from constants import PAYLOAD_HASH_LENGTH


def hash_payload(doc: dict[str, Any]) -> str:
    """
    Hash the Solr ``doc`` only (not ``fetched_at``), so re-polls of the same
    work with the same fields share one payload_hash for ON CONFLICT dedupe.
    """
    canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if len(digest) != PAYLOAD_HASH_LENGTH:
        raise ValueError(f"unexpected hash length {len(digest)}")
    return digest
