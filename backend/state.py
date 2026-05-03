"""Shared application singletons — stores, teller client, and constants.

Routers import this module (``import state``) and access attributes as
``state.teller``, ``state.stored_transactions``, etc.  Using module-level
attribute access (rather than ``from state import X``) ensures that
test patches applied to ``state.X`` are visible inside routers.
"""
import logging
import os
import sys
from typing import Any, MutableMapping

from config import (
    TELLER_ACCESS_TOKENS,
    TELLER_CERT_PATH,
    TELLER_KEY_PATH,
)
from store import PgStore
from teller import TellerClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TELLER_MAX_TX_COUNT  = 500          # Hard cap on transactions fetched per account per sync
PAYOFF_MAX_MONTHS    = 600          # ~50 years; prevents infinite loops in the simulation
OLLAMA_TIMEOUT_SEC   = 120.0        # HTTP timeout when calling the local Ollama server
# Default model for one-shot analytical prompts (insights summary, payoff advice).
# qwen2.5:14b-instruct is the recommended default on moderate GPUs — strong at numeric
# reasoning and instruction-following.  Override with OLLAMA_MODEL env var.
# Alternatives: qwen2.5:7b-instruct, llama3.1:8b-instruct, llama3.2:3b (low-spec fallback).
OLLAMA_MODEL         = os.getenv("OLLAMA_MODEL", "qwen2.5:14b-instruct")
# Chat model — may differ from the one-shot model (e.g. smaller/faster for interactive turns).
# Defaults to the same model; override with OLLAMA_CHAT_MODEL env var.
OLLAMA_CHAT_MODEL    = os.getenv("OLLAMA_CHAT_MODEL", OLLAMA_MODEL)
# Embedding model for RAG — must produce the vector dimension matching the
# `conversation_turn_embeddings.embedding` column (768 in Alembic 0001).
# `nomic-embed-text` is the community default at 768 dims.
OLLAMA_EMBED_MODEL   = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
# host.docker.internal resolves to the Docker host on Docker Desktop (Windows/Mac).
# Override with OLLAMA_HOST env var if running Ollama on a different machine.
OLLAMA_BASE_URL      = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
CSV_UPLOAD_MAX_BYTES = 10 * 1024 * 1024   # 10 MB — reject absurdly large uploads early
ADVISOR_MAX_HISTORY  = 20           # Max chat turns sent to LLM (older turns trimmed from context)

# Forecast weights for a simple 3-month weighted average (most-recent month = highest weight)
_FORECAST_WEIGHTS = (0.5, 0.3, 0.2)

# ---------------------------------------------------------------------------
# mTLS certificate setup
# ---------------------------------------------------------------------------

_teller_cert = None
if TELLER_CERT_PATH and TELLER_KEY_PATH:
    if os.path.exists(TELLER_CERT_PATH) and os.path.exists(TELLER_KEY_PATH):
        _teller_cert = (TELLER_CERT_PATH, TELLER_KEY_PATH)
        logger.info(f"[Teller] mTLS certificates loaded: {TELLER_CERT_PATH}")
    else:
        logger.warning("[Teller] cert paths set but files not found — running without mTLS")
else:
    logger.info("[Teller] No certificates configured (sandbox mode or not required)")

# ---------------------------------------------------------------------------
# Persistent Postgres-backed stores
# ---------------------------------------------------------------------------
# Each ``PgStore`` maps its ``store_name`` to rows in the ``json_stores`` table
# (see Alembic 0002). The ``MutableMapping`` facade preserves the dict-shaped
# call-sites the routers were written against.

_transactions_store    = PgStore("transactions",    "transactions")
_manual_accounts_store = PgStore("manual_accounts", "manual-accounts")
_balances_cache_store  = PgStore("balances_cache",  "balances-cache")
_conversations_store   = PgStore("conversations",   "advisor-conversations")
_budgets_store         = PgStore("budgets",         "budgets")
_goals_store           = PgStore("goals",           "goals")
_account_details_store = PgStore("account_details", "account-details")


def _migrate_reviewed_field() -> None:
    """Backfill the `reviewed` flag on transactions loaded from older data files.

    Before this field existed, a user-marked-Personal txn was indistinguishable
    from an untouched default.  Treat any txn that has ANY user signal
    (is_shared, who, what, notes) as already reviewed — everything else stays
    unreviewed so the "Unreviewed" counter reflects reality on first run.

    With PgStore, ``items()`` returns a snapshot list, so mutating ``t`` in
    place does not persist — we explicitly write each updated row back.
    """
    dirty = 0
    for tid, t in _transactions_store.items():
        if "reviewed" not in t:
            has_signal = bool(
                t.get("is_shared") or t.get("who") or t.get("what") or t.get("notes")
            )
            t["reviewed"] = has_signal
            _transactions_store[tid] = t
            dirty += 1
    if dirty:
        logger.info(f"[migration] Backfilled `reviewed` flag on {dirty} transactions.")


try:
    _migrate_reviewed_field()
except Exception as e:
    # Unit tests import ``state`` before any DB exists; the backfill is
    # idempotent so silently skipping when the connection fails is safe.
    logger.warning(f"[migration] reviewed-field backfill skipped: {e}")

# Live references — routers read/write these dicts directly.
# PgStore is a MutableMapping, so assigning ``.data`` (which returns self)
# keeps the same dict-shaped API as the previous JsonStore-backed dicts.
stored_transactions: MutableMapping[str, Any]  = _transactions_store.data
_manual_accounts:    MutableMapping[str, Any]  = _manual_accounts_store.data
_balances_cache:     MutableMapping[str, Any]  = _balances_cache_store.data
conversations:       MutableMapping[str, Any]  = _conversations_store.data
# Keyed by category (case-preserved); one entry per category cap.
budgets:             MutableMapping[str, Any]  = _budgets_store.data
# Keyed by goal id (goal_<hex>).
goals:               MutableMapping[str, Any]  = _goals_store.data
# Keyed by account_id (Teller or manual).  Side-car for APR / due dates / limits
# because the Teller API doesn't expose these and re-fetches blow away edits to
# the live account object.
account_details:     MutableMapping[str, Any]  = _account_details_store.data

# ---------------------------------------------------------------------------
# TellerClient instance
# ---------------------------------------------------------------------------

teller = TellerClient(
    tokens=TELLER_ACCESS_TOKENS,
    base_url="https://api.teller.io",
    cert=_teller_cert,
    max_tx_count=TELLER_MAX_TX_COUNT,
)


# ---------------------------------------------------------------------------
# Test hooks — swap PgStore for InMemoryStore so unit tests don't need Postgres.
# ---------------------------------------------------------------------------
# Routers do `import state` and access `state.stored_transactions` (etc.) per
# request, so re-binding these module attributes after import is sufficient —
# no router rewrites required.

_STORE_NAMES = (
    ("_transactions_store",    "transactions",    "transactions"),
    ("_manual_accounts_store", "manual_accounts", "manual-accounts"),
    ("_balances_cache_store",  "balances_cache",  "balances-cache"),
    ("_conversations_store",   "conversations",   "advisor-conversations"),
    ("_budgets_store",         "budgets",         "budgets"),
    ("_goals_store",           "goals",           "goals"),
    ("_account_details_store", "account_details", "account-details"),
)

_LIVE_REFS = (
    ("stored_transactions", "_transactions_store"),
    ("_manual_accounts",    "_manual_accounts_store"),
    ("_balances_cache",     "_balances_cache_store"),
    ("conversations",       "_conversations_store"),
    ("budgets",             "_budgets_store"),
    ("goals",               "_goals_store"),
    ("account_details",     "_account_details_store"),
)


def configure_for_tests() -> None:
    """Replace every PgStore singleton with an ``InMemoryStore``.

    Idempotent. Call from a unit-test conftest BEFORE the FastAPI app is
    constructed; routers re-resolve these attributes per request, so the swap
    takes effect on the very next call.
    """
    from store import InMemoryStore

    module = sys.modules[__name__]
    for attr, name, label in _STORE_NAMES:
        setattr(module, attr, InMemoryStore(name, label))
    for live_attr, store_attr in _LIVE_REFS:
        setattr(module, live_attr, getattr(module, store_attr).data)


def reset_in_memory_stores() -> None:
    """Clear every store between unit tests. No-op against PgStore."""
    module = sys.modules[__name__]
    for attr, _name, _label in _STORE_NAMES:
        getattr(module, attr).clear()
