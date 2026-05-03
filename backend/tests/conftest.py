"""Pytest fixtures.

Tests run against a dedicated Postgres database ``expense_hub_test`` on the
same ``db`` service used by docker-compose. The bootstrap below runs before
any app module is imported — it creates the test database if missing and
applies all Alembic migrations so the schema matches the dev DB.

To run the suite:
    docker compose run --rm backend pytest
    # or, from the host when port 15432 is exposed:
    DATABASE_URL=postgresql+asyncpg://expense:expense_dev@localhost:15432/expense_hub_test pytest
"""
# ---------------------------------------------------------------------------
# IMPORTANT: point every subsequent import at the test DB BEFORE any app code
# (``state``, ``main``, ``db.base``) loads — those modules capture
# ``DATABASE_URL`` at import time via ``config.py``.
# ---------------------------------------------------------------------------
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

# FORCE-OVERRIDE (not setdefault) — docker-compose hardcodes DATABASE_URL to
# the dev DB `expense_hub` in the backend service env, which would otherwise
# cause pytest's autouse `clear_storage` fixture to TRUNCATE the dev DB on
# every test. We always pin tests to `expense_hub_test` regardless of what
# the caller's environment says.
_TEST_DATABASE_URL = "postgresql+asyncpg://expense:expense_dev@db:5432/expense_hub_test"
os.environ["DATABASE_URL"] = _TEST_DATABASE_URL

# Sanity guard: refuse to run if anything later mutates DATABASE_URL away
# from the test DB. The TRUNCATE fixture below is destructive and must NEVER
# touch a non-test database.
_REQUIRED_TEST_DB_NAME = "expense_hub_test"


def _assert_safe_test_db() -> None:
    """Abort the suite if DATABASE_URL doesn't point at the test database."""
    url = os.environ.get("DATABASE_URL", "")
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    db_name = (parsed.path or "").lstrip("/")
    if db_name != _REQUIRED_TEST_DB_NAME:
        raise RuntimeError(
            f"REFUSING TO RUN: DATABASE_URL points at {db_name!r}, not "
            f"{_REQUIRED_TEST_DB_NAME!r}. The TRUNCATE fixture would wipe "
            f"that database. Aborting to protect your data."
        )


def _bootstrap_test_database() -> None:
    """Create the test DB if missing and run ``alembic upgrade head``.

    Idempotent — safe to call on every pytest session. The first run creates
    the database; subsequent runs find it already present and only verify
    that migrations are current.
    """
    import psycopg2

    test_url = os.environ["DATABASE_URL"]
    parsed = urlparse(test_url.replace("postgresql+asyncpg://", "postgresql://"))
    db_name = (parsed.path or "").lstrip("/")
    if not db_name:
        raise RuntimeError(f"DATABASE_URL has no database path: {test_url}")

    admin = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        dbname="postgres",
    )
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{db_name}"')
                # pgvector must be enabled per-database (the init.sql only runs
                # for the default db on first cluster boot).
                vector_conn = psycopg2.connect(
                    host=parsed.hostname,
                    port=parsed.port or 5432,
                    user=parsed.username,
                    password=parsed.password,
                    dbname=db_name,
                )
                vector_conn.autocommit = True
                with vector_conn.cursor() as v_cur:
                    v_cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                vector_conn.close()
    finally:
        admin.close()

    backend_dir = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=str(backend_dir),
        env={**os.environ},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise RuntimeError(
            f"alembic upgrade failed ({result.returncode}) — see output above"
        )


_assert_safe_test_db()
_bootstrap_test_database()

# ---------------------------------------------------------------------------
# Now safe to import app code.
# ---------------------------------------------------------------------------
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import state  # noqa: E402
from db.base import sync_engine  # noqa: E402
from main import app  # noqa: E402

# Every table that accumulates state between tests. TRUNCATE is one round-trip
# vs. seven DELETEs via ``.clear()``, and RESTART IDENTITY resets the serial
# sequences so ``conversation_turns.id`` starts at 1 each test.
_TABLES_TO_TRUNCATE = [
    "json_stores",
    "conversation_turn_embeddings",
    "conversation_turns",
    "conversations",
    "transaction_embeddings",
    "user_profile",
    "account_details",
    "goals",
    "budgets",
    "balance_snapshots",
    "transactions",
    "accounts",
]


def _reset_all_stores() -> None:
    """Wipe every table in one statement.

    Re-checks the DB name on every call as a last-line safety net — if some
    test ever mutates the engine to point elsewhere, we abort instead of
    truncating the wrong database.
    """
    _assert_safe_test_db()
    bound_db = sync_engine.url.database
    if bound_db != _REQUIRED_TEST_DB_NAME:
        raise RuntimeError(
            f"REFUSING TO TRUNCATE: sync_engine is bound to {bound_db!r}, "
            f"not {_REQUIRED_TEST_DB_NAME!r}."
        )
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                f"TRUNCATE {', '.join(_TABLES_TO_TRUNCATE)} RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture(autouse=True)
def clear_storage():
    """Reset the database before AND after every test."""
    _reset_all_stores()
    yield
    _reset_all_stores()


@pytest.fixture(autouse=True)
def _block_env_and_token_leaks(monkeypatch):
    """Keep tests from writing fake tokens to the real .env / token log.

    The Teller register-token route calls `_env_add_token` and `_log_token_event`
    which write to the repo's .env and teller-tokens.log files.  Previously,
    `test_teller_connect.py` tried to patch `helpers.Path` to redirect writes,
    but `_ENV_PATH` is resolved at import time so the patch had no effect —
    fake tokens (tok_abc123, tok_one, tok_two) kept ending up in the real .env.

    This fixture neutralises the side-effects for ALL tests and snapshots
    TELLER_ACCESS_TOKENS so in-memory mutations don't bleed across test files.
    """
    import helpers
    import routers.teller as teller_router

    monkeypatch.setattr(helpers,       "_env_add_token",    lambda _t: None)
    monkeypatch.setattr(helpers,       "_env_remove_token", lambda _t: None)
    monkeypatch.setattr(helpers,       "_log_token_event",  lambda **_kw: None)
    monkeypatch.setattr(teller_router, "_env_add_token",    lambda _t: None)
    monkeypatch.setattr(teller_router, "_env_remove_token", lambda _t: None)
    monkeypatch.setattr(teller_router, "_log_token_event",  lambda **_kw: None)

    original_tokens = list(state.TELLER_ACCESS_TOKENS)
    yield
    state.TELLER_ACCESS_TOKENS[:] = original_tokens


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_discover_csv() -> str:
    return (
        "Trans. Date,Post Date,Description,Amount,Category\n"
        "01/15/2024,01/16/2024,STARBUCKS,-4.50,Restaurants\n"
        "01/16/2024,01/17/2024,AMAZON PRIME,-29.99,Shopping\n"
    )


@pytest.fixture
def sample_barclays_csv() -> str:
    return (
        "Barclays Bank Delaware\n"
        "Account Number: 1234567890123456\n"
        "Account Balance as of 01/31/2024: $1234.56\n"
        "\n"
        "Transaction Date,Description,Category,Amount\n"
        "01/15/2024,WHOLE FOODS,DEBIT,-67.23\n"
        "01/16/2024,NETFLIX,DEBIT,-15.99\n"
    )


@pytest.fixture
def sample_transaction_dict() -> dict:
    return {
        "id": "discover_2024-01-15_-4.5_STARBUCKS",
        "transaction_id": "discover_2024-01-15_-4.5_STARBUCKS",
        "date": "2024-01-15",
        "description": "STARBUCKS",
        "amount": -4.50,
        "source": "discover",
        "is_shared": False,
        "who": None,
        "what": None,
        "person_1_owes": 0.0,
        "person_2_owes": 0.0,
        "notes": "",
    }
