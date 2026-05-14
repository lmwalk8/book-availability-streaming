"""Open Library Search API client: HTTP contract, validation, paging."""
from __future__ import annotations
import json
import logging
import time
from typing import Any, Iterator
import requests
from config import (
    OPENLIBRARY_BASE_URL,
    OPENLIBRARY_DEFAULT_FIELDS,
    OPENLIBRARY_MAX_RETRIES,
    OPENLIBRARY_PAGE_SIZE,
    OPENLIBRARY_QUERY,
    OPENLIBRARY_REQUEST_TIMEOUT,
    OPENLIBRARY_RETRY_BACKOFF_SEC,
    OPENLIBRARY_SLEEP_BETWEEN_REQUESTS_SEC,
    OPENLIBRARY_USER_AGENT,
)

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": OPENLIBRARY_USER_AGENT})


def build_search_params(*, page: int = 1, limit: int | None = None) -> dict[str, Any]:
    """Query params for GET OPENLIBRARY_BASE_URL (see Search API docs)."""
    lim = OPENLIBRARY_PAGE_SIZE if limit is None else int(limit)
    return {
        "q": OPENLIBRARY_QUERY,
        "fields": OPENLIBRARY_DEFAULT_FIELDS,
        "page": page,
        "limit": lim,
    }

def num_found(data: dict[str, Any]) -> int | None:
    """Open Library uses camelCase numFound; some responses may differ."""
    if "numFound" in data:
        return int(data["numFound"])
    if "num_found" in data:
        return int(data["num_found"])
    return None

def validate_search_response(data: Any) -> dict[str, Any]:
    """Ensure JSON has the shape we rely on before consuming docs."""
    if not isinstance(data, dict):
        raise ValueError("search response must be a JSON object")
    if "docs" not in data:
        raise ValueError("search response missing 'docs'")
    if not isinstance(data["docs"], list):
        raise ValueError("'docs' must be a list")
    return data

def filter_fulltext_docs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only rows indexed as full-text available."""
    kept: list[dict[str, Any]] = []
    for doc in docs:
        if doc.get("ebook_access") == "public":
            kept.append(doc)
        else:
            logger.debug("skipping doc without ebook_access=public: %s", doc.get("key"))
    dropped = len(docs) - len(kept)
    if dropped:
        logger.warning("filtered %s docs without ebook_access=public", dropped)
    return kept

def fetch_search_page(*, page: int = 1, limit: int | None = None) -> dict[str, Any]:
    """GET search.json with q, fields, pagination; retries on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(1, OPENLIBRARY_MAX_RETRIES + 1):
        wait = OPENLIBRARY_RETRY_BACKOFF_SEC * (2 ** (attempt - 1))
        try:
            resp = _SESSION.get(
                OPENLIBRARY_BASE_URL,
                params=build_search_params(page=page, limit=limit),
                timeout=OPENLIBRARY_REQUEST_TIMEOUT,
            )
        except requests.RequestException as e:
            last_exc = e
            logger.warning(
                "Open Library transport error page=%s attempt=%s/%s: %s; sleeping %.1fs",
                page,
                attempt,
                OPENLIBRARY_MAX_RETRIES,
                e,
                wait,
            )
            if attempt == OPENLIBRARY_MAX_RETRIES:
                break
            time.sleep(wait)
            continue

        if resp.status_code in (429, 500, 502, 503, 504):
            last_exc = requests.HTTPError(
                f"{resp.status_code} for url: {resp.url}",
                response=resp,
            )
            logger.warning(
                "Open Library HTTP %s page=%s attempt=%s/%s; sleeping %.1fs",
                resp.status_code,
                page,
                attempt,
                OPENLIBRARY_MAX_RETRIES,
                wait,
            )
            if attempt == OPENLIBRARY_MAX_RETRIES:
                break
            time.sleep(wait)
            continue

        try:
            resp.raise_for_status()
            return validate_search_response(resp.json())
        except (requests.HTTPError, ValueError, json.JSONDecodeError) as e:
            last_exc = e
            logger.warning(
                "Open Library response error page=%s attempt=%s/%s: %s; sleeping %.1fs",
                page,
                attempt,
                OPENLIBRARY_MAX_RETRIES,
                e,
                wait,
            )
            if attempt == OPENLIBRARY_MAX_RETRIES:
                break
            time.sleep(wait)

    raise RuntimeError(
        f"Open Library request failed after {OPENLIBRARY_MAX_RETRIES} attempts (page={page})"
    ) from last_exc

def iter_search_pages(
    *,
    max_pages: int,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Yield validated search JSON per page, sleeping between requests when configured.
    """
    for page in range(1, max_pages + 1):
        if page > 1 and OPENLIBRARY_SLEEP_BETWEEN_REQUESTS_SEC > 0:
            time.sleep(OPENLIBRARY_SLEEP_BETWEEN_REQUESTS_SEC)
        yield fetch_search_page(page=page, limit=limit)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    payload = fetch_search_page(page=1, limit=3)
    raw_docs = payload["docs"]
    docs = filter_fulltext_docs(raw_docs)
    summary = {
        "base_url": OPENLIBRARY_BASE_URL,
        "numFound": num_found(payload),
        "start": payload.get("start"),
        "raw_doc_count": len(raw_docs),
        "fulltext_doc_count": len(docs),
        "sample_keys": list(docs[0].keys()) if docs else [],
    }
    print(json.dumps(summary, indent=2))
