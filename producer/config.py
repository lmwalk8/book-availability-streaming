import os
from pathlib import Path
from dotenv import load_dotenv

# Load repo-root .env regardless of current working directory.
_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env")

OPENLIBRARY_BASE_URL = os.getenv(
    "OPENLIBRARY_BASE_URL", "https://openlibrary.org/search.json"
)
OPENLIBRARY_QUERY = os.getenv("OPENLIBRARY_QUERY", "ebook_access:public")
OPENLIBRARY_DEFAULT_FIELDS = os.getenv(
    "OPENLIBRARY_DEFAULT_FIELDS",
    "key,title,author_name,has_fulltext,ebook_access",
)
OPENLIBRARY_PAGE_SIZE = int(os.getenv("OPENLIBRARY_PAGE_SIZE", "100"))
OPENLIBRARY_USER_AGENT = os.getenv(
    "OPENLIBRARY_USER_AGENT",
    "book-availability-streaming/0.1 (+https://github.com/lmwalk8/book-availability-streaming)",
)
OPENLIBRARY_REQUEST_TIMEOUT = float(os.getenv("OPENLIBRARY_REQUEST_TIMEOUT", "30"))
OPENLIBRARY_MAX_RETRIES = int(os.getenv("OPENLIBRARY_MAX_RETRIES", "4"))
OPENLIBRARY_RETRY_BACKOFF_SEC = float(
    os.getenv("OPENLIBRARY_RETRY_BACKOFF_SEC", "1.5")
)
OPENLIBRARY_SLEEP_BETWEEN_REQUESTS_SEC = float(
    os.getenv("OPENLIBRARY_SLEEP_BETWEEN_REQUESTS_SEC", "0.5")
)
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_RAW = os.getenv("KAFKA_TOPIC_RAW", "openlibrary.search.raw")
POLL_CYCLE_SLEEP_SEC = float(os.getenv("POLL_CYCLE_SLEEP_SEC", "60"))
OPENLIBRARY_MAX_PAGES_PER_CYCLE = int(
    os.getenv("OPENLIBRARY_MAX_PAGES_PER_CYCLE", "10")
)
