"""Pytest fixtures.

Tests run against a dedicated Postgres database ``financial_freedom_test`` on the
same ``db`` service used by docker-compose. The bootstrap below runs before
any app module is imported — it creates the test database if missing and
applies all Alembic migrations so the schema matches the dev DB.

To run the suite:
    docker compose run --rm backend pytest tests
    # or, from the host when port 15432 is exposed:
    DATABASE_URL=postgresql+asyncpg://finfree:finfree_dev@localhost:15432/financial_freedom_test pytest tests

Name the directory explicitly. This suite and ``tests_unit`` cannot share
a pytest process: both conftests force-override DATABASE_URL at import
time (this one to ``financial_freedom_test``, the other to a placeholder no-DB
URL) and ``db.base`` binds its engine to whichever loaded last. A bare
``pytest`` collects both, and the TRUNCATE guard below then aborts every
test in this suite.
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
# the dev DB `financial_freedom` in the backend service env, which would otherwise
# cause pytest's autouse `clear_storage` fixture to TRUNCATE the dev DB on
# every test. We always pin tests to `financial_freedom_test` regardless of what
# the caller's environment says.
_TEST_DATABASE_URL = "postgresql+asyncpg://finfree:finfree_dev@db:5432/financial_freedom_test"
os.environ["DATABASE_URL"] = _TEST_DATABASE_URL

# Sanity guard: refuse to run if anything later mutates DATABASE_URL away
# from the test DB. The TRUNCATE fixture below is destructive and must NEVER
# touch a non-test database.
_REQUIRED_TEST_DB_NAME = "financial_freedom_test"


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
    "subscription_reviews",
    "merchant_aliases",
    "digests",
    "user_fact_embeddings",
    "user_facts",
    "advisor_turn_feedback",
    "advisor_style_profile",
    "fact_reflection_state",
    "scheduled_tasks",
    "sync_corrections",
    "sync_runs",
    "sync_row_state",
    "period_settlements",
    "peers",
    "peer_shared_transactions",
    "instance_identity",
    "conversation_turn_embeddings",
    "conversation_turns",
    "conversations",
    "transaction_embeddings",
    "document_chunks",
    "documents",
    "seed_custom",
    "seed_removed_defaults",
    "allowlist_hosts",
    "user_profile",
    "category_rules",
    "categories",
    "account_details",
    "goals",
    "budgets",
    "holding_cost_overrides",
    "holdings",
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
    # categories is truncated for isolation like everything else, but it is a
    # seeded vocabulary rather than per-test data: analytics reads roles off
    # these rows to decide what counts as a bill, so every test starts from
    # the same known set instead of an empty one.
    import categories_service

    categories_service.reset_caches()
    categories_service.ensure_seeded()


@pytest.fixture(autouse=True)
def clear_storage():
    """Reset the database before AND after every test."""
    _reset_all_stores()
    yield
    _reset_all_stores()


@pytest.fixture(autouse=True)
def _block_env_and_token_leaks(monkeypatch):
    """Keep tests from writing fake access URLs to the real .env.

    The SimpleFIN claim route calls `_env_add_simplefin_url` which writes to
    the repo's .env file. This fixture neutralises that side-effect for ALL
    tests and snapshots SIMPLEFIN_ACCESS_URLS so in-memory mutations don't
    bleed across test files.
    """
    import helpers
    import routers.simplefin as simplefin_router

    monkeypatch.setattr(helpers,          "_env_add_simplefin_url",    lambda _u: None)
    monkeypatch.setattr(helpers,          "_env_remove_simplefin_url", lambda _u: None)
    monkeypatch.setattr(simplefin_router, "_env_add_simplefin_url",    lambda _u: None)
    monkeypatch.setattr(simplefin_router, "_env_remove_simplefin_url", lambda _u: None)

    original_urls = list(state.SIMPLEFIN_ACCESS_URLS)
    yield
    state.SIMPLEFIN_ACCESS_URLS[:] = original_urls


@pytest.fixture(autouse=True)
def _block_google_sheets(monkeypatch):
    """Keep tests off the real spreadsheet.

    ``build_gateway`` is the single door to Google, and several routes now walk
    through it on their own — marking a period ready or paid publishes a footer
    immediately. With real credentials in the environment those routes would
    write to the household's live sheet, which holds years of settled records.
    Every test gets a refusal instead; a test that wants gateway behaviour
    passes its own ``InMemoryGateway``.
    """
    from sheet_sync import service

    def _refuse(*_a, **_kw):
        raise service.SyncDisabled("Sheet access is disabled in tests.")

    monkeypatch.setattr(service, "build_gateway", _refuse)


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
