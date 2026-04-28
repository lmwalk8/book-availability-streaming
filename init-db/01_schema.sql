-- 1. Create ingestion_poller table
-- Ingestion resume point (one row per poller job)
CREATE TABLE IF NOT EXISTS ingestion_poller (
    job_name VARCHAR(100) PRIMARY KEY,
    page INT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Create work_events table
-- Append-only events for Grafana time-range queries and dedupe via payload_hash
CREATE TABLE IF NOT EXISTS work_events (
    id BIGSERIAL PRIMARY KEY,
    work_key TEXT NOT NULL,
    title TEXT NOT NULL,
    author_name TEXT,
    has_fulltext BOOLEAN NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_hash CHAR(64) NOT NULL,
    CONSTRAINT work_events_has_fulltext_check CHECK (has_fulltext = true)
);

-- Avoid storing identical snapshots repeatedly
CREATE UNIQUE INDEX IF NOT EXISTS work_events_work_key_payload_hash_uidx
    ON work_events (work_key, payload_hash);

CREATE INDEX IF NOT EXISTS work_events_ingested_at_idx ON work_events (ingested_at DESC);
CREATE INDEX IF NOT EXISTS work_events_work_key_ingested_at_idx ON work_events (work_key, ingested_at DESC);
