"""Contract constants for Kafka to work_events mapping."""
# Top-level keys on each Kafka JSON value from producer/poll_loop.py
ENVELOPE_FETCHED_AT = "fetched_at"
ENVELOPE_DOC = "doc"

# Fields required inside envelope["doc"] for a valid row
DOC_KEY = "key"
DOC_TITLE = "title"
DOC_AUTHOR_NAME = "author_name"
DOC_EBOOK_ACCESS = "ebook_access"

# Matches CHECK (ebook_access = 'public') on work_events
EBOOK_ACCESS_PUBLIC = "public"

# Schema requires title NOT NULL
FALLBACK_TITLE = "(no title)"

PAYLOAD_HASH_LENGTH = 64
