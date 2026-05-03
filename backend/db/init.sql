-- Mounted at /docker-entrypoint-initdb.d/init.sql on the Postgres container.
-- Runs once, on first container boot against an empty data directory.
-- Alembic migrations also call CREATE EXTENSION IF NOT EXISTS vector, but
-- doing it here makes `docker compose up db` usable standalone (e.g. for
-- psql exploration before the backend has run its migrations).
CREATE EXTENSION IF NOT EXISTS vector;
