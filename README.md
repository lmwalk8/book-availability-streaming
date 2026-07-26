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
    - Libraries Used:
        - `python-dotenv`: 
        - `requests`: 
        - `kafka-python`: 
        - `sqlalchemy`: 
        - `psycopg2-binary`: 
        - `pytest`: 
        - `apache-flink`: 
        - `apache-flink-libraries`: 

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


