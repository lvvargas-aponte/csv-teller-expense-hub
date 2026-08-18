"""
Central configuration module — reads all environment variables exactly once.
Every other module imports constants from here instead of calling os.getenv() directly.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path= Path(__file__).parent.parent / ".env")

_PROJECT_ROOT = Path(__file__).parent.parent

def _resolve_path(raw: str | None) -> str | None:
    """Resolve a path relative to the project root if it isn't already absolute."""
    if not raw:
        return None
    p = Path(raw)
    return str(p if p.is_absolute() else _PROJECT_ROOT / p)

# SimpleFIN — flat-fee bank/credit-card aggregator (https://www.simplefin.org).
# Each entry is a durable "Access URL" obtained by claiming a one-time Setup
# Token (see routers/simplefin.py). Multiple entries are supported in case
# the user claims more than one SimpleFIN Bridge over time.
_raw_simplefin_urls: str = os.getenv("SIMPLEFIN_ACCESS_URLS", "")
SIMPLEFIN_ACCESS_URLS: list[str] = [u.strip() for u in _raw_simplefin_urls.split(",") if u.strip()]

# SnapTrade — brokerage/crypto holdings aggregation (Robinhood, M1, E-trade, ...)
# Only two credentials per SnapTrade's docs — no sandbox/production switch.
SNAPTRADE_CLIENT_ID: str | None = os.getenv("SNAPTRADE_CLIENT_ID")
SNAPTRADE_CONSUMER_KEY: str | None = os.getenv("SNAPTRADE_CONSUMER_KEY")

# Google Sheets
SPREADSHEET_ID: str | None = os.getenv("SPREADSHEET_ID")
SHEET_NAME: str | None = os.getenv("SHEET_NAME")
# Absolute path relative to this file so it works regardless of the working directory
_credentials_filename: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
CREDENTIALS_FILE: Path = Path(__file__).parent / _credentials_filename

# Person names for shared-expense splits. Both instances MUST set these to
# identical values — the shared Google Sheet's owes columns are named after
# them, so a mismatch makes each instance look for a column the other didn't
# write.
PERSON_1_NAME: str = os.getenv("PERSON_1_NAME", "Person 1")
PERSON_2_NAME: str = os.getenv("PERSON_2_NAME", "Person 2")

# Which of the two person slots THIS instance is. 1 → PERSON_1_NAME and the
# person_1_owes field; 2 → PERSON_2_NAME and person_2_owes. The two instances
# must pick different slots.
_raw_instance_person_slot: str = os.getenv("INSTANCE_PERSON_SLOT", "1")
try:
    INSTANCE_PERSON_SLOT: int = int(_raw_instance_person_slot)
except ValueError:
    raise ValueError(
        f"INSTANCE_PERSON_SLOT must be 1 or 2, got {_raw_instance_person_slot!r}. "
        "One instance sets 1, the other sets 2."
    )
if INSTANCE_PERSON_SLOT not in (1, 2):
    raise ValueError(
        f"INSTANCE_PERSON_SLOT must be 1 or 2, got {INSTANCE_PERSON_SLOT}. "
        "One instance sets 1, the other sets 2."
    )

# Two-way shared-expense sync with the Google Sheet. Default OFF: turning it on
# lets the app write to a spreadsheet holding years of settled financial
# records, so it is an explicit opt-in rather than something a fresh install
# does on its own.
SHEET_SYNC_ENABLED: bool = os.getenv("SHEET_SYNC_ENABLED", "false").lower() == "true"

# Error verbosity — True in local dev (default), False in production
DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

# Database — Postgres + pgvector. Defaults target the `db` service in docker-compose.
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://expense:expense_dev@db:5432/expense_hub",
)

# Fin agent harness — the advisor always runs the tool-use loop.
ADVISOR_AGENT_MAX_ITERS: int = int(os.getenv("ADVISOR_AGENT_MAX_ITERS", "10"))

# Web + market tools for Fin (web_search / fetch_webpage / stock quotes).
# Kill-switch for offline or air-gapped installs — Fin degrades to
# DB-grounded answers when disabled.
ADVISOR_WEB_TOOLS_ENABLED: bool = os.getenv("ADVISOR_WEB_TOOLS_ENABLED", "true").lower() == "true"
WEB_SEARCH_MAX_RESULTS: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
ADVISOR_FETCH_TIMEOUT_SEC: float = float(os.getenv("ADVISOR_FETCH_TIMEOUT_SEC", "20"))
ADVISOR_FETCH_MAX_BYTES: int = int(os.getenv("ADVISOR_FETCH_MAX_BYTES", str(2 * 1024 * 1024)))

# Caps the number of confirmed user facts injected into the agent's
# system prompt each turn. Higher = Fin remembers more without needing
# `recall_about_user`; lower = leaner prompt and faster turns.
ADVISOR_MEMORY_INJECT_LIMIT: int = int(os.getenv("ADVISOR_MEMORY_INJECT_LIMIT", "30"))
