"""Typed row matching work_events columns (minus id)."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OpenLibraryRow:
    work_key: str
    title: str
    author_name: str | None
    ebook_access: str
    ingested_at: datetime
    payload_hash: str
