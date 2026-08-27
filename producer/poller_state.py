"""Read/write Open Library poll resume page in Postgres ingestion_poller."""
from __future__ import annotations

import logging

import psycopg2
from config import (
    INGESTION_POLLER_JOB_NAME,
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)

logger = logging.getLogger(__name__)

DEFAULT_JOB_NAME = INGESTION_POLLER_JOB_NAME


def _connect():
    if not POSTGRES_DB or not POSTGRES_USER or POSTGRES_PASSWORD is None:
        raise RuntimeError(
            "POSTGRES_DB, POSTGRES_USER, and POSTGRES_PASSWORD must be set"
        )
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )

def get_next_page(job_name: str = DEFAULT_JOB_NAME) -> int:
    """
    Return the next Search API page to fetch (1-based).
    Inserts a row at page=1 if this job has never run.
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT page FROM ingestion_poller WHERE job_name = %s",
                (job_name,),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    """
                    INSERT INTO ingestion_poller (job_name, page, updated_at)
                    VALUES (%s, 1, now())
                    ON CONFLICT (job_name) DO NOTHING
                    """,
                    (job_name,),
                )
                logger.info("ingestion_poller: initialized job=%s page=1", job_name)
                return 1
            page = int(row[0])
            logger.info("ingestion_poller: resume job=%s next_page=%s", job_name, page)
            return max(1, page)


def set_next_page(job_name: str, page: int) -> None:
    """Persist the next page to fetch after a successful publish."""
    if page < 1:
        raise ValueError(f"page must be >= 1, got {page}")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ingestion_poller (job_name, page, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (job_name) DO UPDATE
                SET page = EXCLUDED.page,
                    updated_at = now()
                """,
                (job_name, page),
            )
    logger.info("ingestion_poller: saved job=%s next_page=%s", job_name, page)
