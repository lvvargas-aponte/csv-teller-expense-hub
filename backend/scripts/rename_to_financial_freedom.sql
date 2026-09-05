-- One-time rename of the legacy database/role to the Financial Freedom names.
-- Only needed for installs created before the rename; a fresh `docker compose up`
-- already provisions financial_freedom / finfree from docker-compose.yaml.
--
-- Run against the `postgres` maintenance database (you cannot rename a database
-- you are connected to), using the OLD role name:
--
--   docker compose up -d db
--   docker compose exec -T db psql -U expense -d postgres \
--       < backend/scripts/rename_to_financial_freedom.sql
--
-- The db container's healthcheck already expects the new names, so it reports
-- unhealthy until this finishes — that is expected, and `exec` still works.
-- Bring the rest of the stack up afterwards.
--
-- If POSTGRES_PASSWORD is set in your .env, replace 'finfree_dev' below with it.

\set ON_ERROR_STOP on

-- Drop live connections; ALTER DATABASE ... RENAME requires none.
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname IN ('expense_hub', 'expense_hub_test')
  AND pid <> pg_backend_pid();

SELECT format('ALTER DATABASE %I RENAME TO %I', 'expense_hub', 'financial_freedom')
WHERE EXISTS (SELECT 1 FROM pg_database WHERE datname = 'expense_hub')
  AND NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'financial_freedom')
\gexec

SELECT format('ALTER DATABASE %I RENAME TO %I', 'expense_hub_test', 'financial_freedom_test')
WHERE EXISTS (SELECT 1 FROM pg_database WHERE datname = 'expense_hub_test')
  AND NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'financial_freedom_test')
\gexec

SELECT format('ALTER ROLE %I RENAME TO %I', 'expense', 'finfree')
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'expense')
  AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finfree')
\gexec

-- Re-set the password explicitly: a role rename clears an MD5-hashed password
-- (SCRAM verifiers survive it, but this makes the outcome the same either way).
ALTER ROLE finfree WITH PASSWORD 'finfree_dev';

\echo 'Rename complete. Current databases and roles:'
SELECT datname FROM pg_database WHERE datname LIKE 'financial_freedom%';
SELECT rolname FROM pg_roles WHERE rolname = 'finfree';
