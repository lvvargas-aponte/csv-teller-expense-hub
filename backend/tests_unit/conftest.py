"""Unit-test bootstrap — no Postgres, no Alembic, no real I/O.

Sibling to ``backend/tests/conftest.py``. Kept in a separate top-level
directory so pytest's parent-conftest discovery doesn't apply the integration
fixtures (which TRUNCATE a real database) here.

Run with:
    docker compose run --rm backend pytest tests_unit
    # or, from the host with no DB at all:
    pytest backend/tests_unit
"""
import os
import sys
from pathlib import Path

# Make the backend package importable when pytest is invoked from repo root.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

# A placeholder URL so ``config.DATABASE_URL`` resolves and the SQLAlchemy
# engines can be constructed. We never connect — every store and every repo
# call is intercepted before reaching the engine.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://placeholder/none")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import state  # noqa: E402
from db import accounts_repo_memory  # noqa: E402

# Swap BEFORE importing ``main`` (which wires routers) so the router calls to
# ``get_repo()`` return the InMemoryAccountsRepo from the very first request.
state.configure_for_tests()
accounts_repo_memory.install_for_tests()

from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_state():
    """Wipe in-memory state before AND after every test."""
    state.reset_in_memory_stores()
    accounts_repo_memory.reset()
    yield
    state.reset_in_memory_stores()
    accounts_repo_memory.reset()


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Shared CSV fixtures — match the ones in tests/conftest.py so test files can
# move between the two suites without rewriting their fixture parameters.
# ---------------------------------------------------------------------------

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
