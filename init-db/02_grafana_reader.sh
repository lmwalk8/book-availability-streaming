#!/usr/bin/env bash
# Creates read-only role for Grafana. Runs on first Postgres init.
# Requires: GRAFANA_DB_PASSWORD (and optionally GRAFANA_DB_USER, default grafana_reader).

set -euo pipefail

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${GRAFANA_DB_PASSWORD:?GRAFANA_DB_PASSWORD is required}"

GRAFANA_DB_USER="${GRAFANA_DB_USER:-grafana_reader}"

escape_sql_literal() {
  printf '%s' "$1" | sed "s/'/''/g"
}

GU_ESC=$(escape_sql_literal "$GRAFANA_DB_USER")
GP_ESC=$(escape_sql_literal "$GRAFANA_DB_PASSWORD")

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
DO \$body\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = '$GU_ESC') THEN
    EXECUTE format('CREATE ROLE %I WITH LOGIN PASSWORD %L', '$GU_ESC', '$GP_ESC');
  END IF;
END;
\$body\$;

GRANT CONNECT ON DATABASE "${POSTGRES_DB}" TO "${GRAFANA_DB_USER}";
GRANT USAGE ON SCHEMA public TO "${GRAFANA_DB_USER}";
GRANT SELECT ON ALL TABLES IN SCHEMA public TO "${GRAFANA_DB_USER}";
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO "${GRAFANA_DB_USER}";

ALTER DEFAULT PRIVILEGES FOR ROLE "${POSTGRES_USER}" IN SCHEMA public GRANT SELECT ON TABLES TO "${GRAFANA_DB_USER}";
ALTER DEFAULT PRIVILEGES FOR ROLE "${POSTGRES_USER}" IN SCHEMA public GRANT SELECT ON SEQUENCES TO "${GRAFANA_DB_USER}";
EOSQL
