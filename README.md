# Alerts for Availability of Books

## Project Overview:

This pipeline turns periodic [Open Library Search API](https://openlibrary.org/dev/docs/api/search) polling results into Postgres-backed metrics so Grafana can alert when a book becomes fully available, which is when `ebook_access` goes from unknown/false (values: `no_ebook`, `unclassified`, `printdisabled`, `borrowable`) to true (value: `public`).

### Full Pipeline Steps:

1. Producer calls the Search API on a schedule (pagination), constrained to well-known works that people care about. Each hit is serialized as JSON and published to an Apache Kafka topic (raw ingest).
2. Flink consumes that topic, parses payloads into typed fields, filters to the desired subset, and uses a join to Postgres in order to emit newly readable events (availability of text was updated).
3. Flink sinks meaningful rows into Postgres so Grafana can query the most recent activity.
4. Grafana connects to Postgres with a read-only user, runs SQL queries, and uses alert rules to notify when a book becomes readable or when the pipeline stalls.

## Technology Stack (Prerequisites to Run Project):

- Python 3.12+
- Docker / Docker Compose (Kafka, Flink, Postgres, Grafana)

### Host libraries (`requirements.txt` — producer + unit tests)

- `python-dotenv`: Loads repo-root `.env` into the producer process
- `requests`: HTTP client for the Open Library Search API
- `kafka-python`: Publishes search hits to the Kafka raw topic
- `pytest`: Runs parse/hash unit tests under `pyflink/jobs/`

### Flink image libraries (`pyflink/requirements.txt` — installed in Docker only)

- `apache-flink`: PyFlink APIs for the Kafka -> transform -> Postgres job
- `apache-flink-libraries`: Matching PyFlink native/helper libs for Flink 1.19.1
- `psycopg2-binary`: PostgreSQL driver used by the Flink job’s write path 

## Steps for Project Setup:

1. Install/create project dependencies if applicable (Python)

2. Clone this repository:
```
git clone https://github.com/lmwalk8/book-availability-streaming.git
cd book-availability-streaming
```

3. Create and activate a Python virtual environment:
```
python3 -m venv book_avail_project_env
source book_avail_project_env/bin/activate (Linux/macOS) OR book_avail_project_env\Scripts\activate.bat (Windows)
```

4. Install all required dependencies:
```
pip install -r requirements.txt
```

5. Set up required environment variables:

Create `.env` in the project directory. Copy from `.env.example` and fill in secrets.

## Guide to Run the Project

1. Bring up needed docker containers:
```
docker compose up -d --build
```

2. Confirm PostgreSQL table exists in docker:
```
docker compose exec postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM work_events;"'
```

3. Ensure Kafka topic is created:
```
docker compose exec kafka kafka-topics --create \
  --bootstrap-server kafka:29092 \
  --topic openlibrary.search.raw \
  --partitions 3 \
  --replication-factor 1 \
  --if-not-exists
```

4. Poll producer and wait for **sent > 0**
```
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
python producer/poll_loop.py
```

5. Submit the Flink job:
```
docker compose exec flink-jobmanager \
  flink run -d -py /opt/flink/usrlib/jobs/openlibrary_to_postgresql.py
```
[Flink UI](http://localhost:8081) -> check job is running, not failed.

6. Verify rows landed in PostgreSQL:
```
docker compose exec postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT count(*) AS n FROM work_events;
SELECT work_key, title, ebook_access, ingested_at, left(payload_hash, 12) AS hash_prefix
FROM work_events
ORDER BY ingested_at DESC
LIMIT 10;
"'
```
Confirm all rows have ebook_access = public

7. Grafana Steps:
TBD
