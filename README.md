# Alerts for Availability of Books

## Project Overview:

This pipeline turns periodic [Open Library Search API](https://openlibrary.org/dev/docs/api/search) polling results into Postgres-backed metrics so Grafana can alert when a book is newly observed as publicly accessible in the database table. Essentially it will be added as a new entry to the table when `ebook_access` goes from unknown/false (values: `no_ebook`, `unclassified`, `printdisabled`, `borrowable`) to true (value: `public`).

### Full Pipeline Steps:

1. Producer calls the Search API on a schedule (pagination), constrained to well-known works that people care about. Each hit is serialized as JSON and published to an Apache Kafka topic (raw ingest). It resumes from the last page stored in Postgres ingestion_poller (see INGESTION_POLLER_JOB_NAME), so each cycle advances through the catalog instead of re-fetching pages 1–10.
2. Flink consumes that topic, parses payloads into typed fields, filters to the desired subset, and uses a dedupe + sink in Postgres to emit newly readable events (availability of text was updated).
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

4. Confirm producer is publishing and continuously advancing:
```
docker compose logs producer --tail 20
```
```
docker compose exec postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT * FROM ingestion_poller;"'
```
*Note*: Can manually run the producer for debugging if not using the compose producer:
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

Grafana starts with first step: `docker compose up -d --build`. The Postgres datasource and **Book availability ingest** dashboard are provisioned from `grafana/provisioning/` and `grafana/dashboards/book-ingest.json`.

### Open Grafana

- URL: [http://localhost:3000](http://localhost:3000)
- Login: `GF_SECURITY_ADMIN_USER` / `GF_SECURITY_ADMIN_PASSWORD` from `.env`

### Datasource (auto-provisioned)

On startup, Grafana creates a PostgreSQL datasource (`book-streaming-postgres`) using:

| Setting | Value |
|---------|--------|
| Host | `postgres:5432` (inside Docker network) |
| Database | `POSTGRES_DB` |
| User | `GRAFANA_DB_USER` (default `grafana_reader`) |
| Password | `GRAFANA_DB_PASSWORD` |

Verify: **Connections → Data sources → PostgreSQL → Save & test** (should be green).

### Dashboard

The dashboard is **pre-provisioned** from `grafana/dashboards/book-ingest.json` — no manual SQL needed unless you edit panels.

Open **Dashboards → Book availability ingest** (may appear under **General** depending on existing Grafana volume state).

Panels include:

- **Seconds since last ingest** — pipeline freshness (stall alert uses this)
- **Events / distinct works in range** — respects dashboard time picker
- **Events over time** — ingest volume chart
- **Recent works** — latest rows in `work_events`
- **New public works (24h)** — first-time `work_key` sightings (stat + detail table)

After UI edits, re-export to `grafana/dashboards/book-ingest.json`.

### Alerts

Alerts are **not** provisioned — create them in **Alerting → Alert rules** (or from a panel → Alert tab). Use the PostgreSQL datasource.

#### 1. Pipeline stall

**SQL:**

```sql
SELECT
  coalesce(
    extract(epoch FROM (now() - max(ingested_at))),
    999999
  ) AS seconds_since_last
FROM work_events;
```

**Condition:** `seconds_since_last` **IS ABOVE** `900` (15 minutes)

**Evaluate:** every **1m**, for **5m**

#### 2. Data quality

**SQL:**

```sql
SELECT count(*) AS non_public_rows
FROM work_events
WHERE ebook_access <> 'public';
```

**Condition:** `non_public_rows` **IS ABOVE** `0`

**Evaluate:** every **5m**, for **0m**

Should never fire (Postgres `CHECK` enforces `public` only).

#### 3. New public works (optional — dashboard-only recommended)

Skip alerting unless you want notifications; a fresh Postgres volume makes almost every book look “new”. If you add it anyway:

**SQL:**

```sql
SELECT count(*) AS new_works_last_hour
FROM work_events w
WHERE w.ingested_at > now() - interval '1 hour'
  AND NOT EXISTS (
    SELECT 1
    FROM work_events older
    WHERE older.work_key = w.work_key
      AND older.ingested_at < w.ingested_at
  )
  AND EXISTS (
    SELECT 1
    FROM work_events seed
    WHERE seed.ingested_at < now() - interval '24 hours'
  );
```

**Condition:** `new_works_last_hour` **IS ABOVE** `0` (or a higher threshold)

**Evaluate:** every **15m**, for **5m**

The `EXISTS (... 24 hours)` clause avoids alert storms right after a volume wipe.

**Notification delivery:**

1. **Alerting → Contact points** — add email (requires SMTP in `.env` / compose; Gmail uses an [App Password](https://support.google.com/accounts/answer/185833), not your Grafana login password).
2. **Alerting → Notification policies** — set the default policy (or rule override) to your contact point.

**When alerts fire on purpose:** stopping the stack stops new rows and will trigger **stall**. Mute or silence the rule when taking the stack offline.
