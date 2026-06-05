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

# Teller.io
TELLER_APP_ID: str | None = os.getenv("TELLER_APP_ID")
_raw_teller_key: str = os.getenv("TELLER_API_KEY", "")
TELLER_ACCESS_TOKENS: list[str] = [t.strip() for t in _raw_teller_key.split(",") if t.strip()]
TELLER_ENVIRONMENT: str = os.getenv("TELLER_ENVIRONMENT", "development")
TELLER_CERT_PATH: str | None = _resolve_path(os.getenv("TELLER_CERT_PATH"))
TELLER_KEY_PATH: str | None = _resolve_path(os.getenv("TELLER_KEY_PATH"))

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

# Person names for shared-expense splits
PERSON_1_NAME: str = os.getenv("PERSON_1_NAME", "Person 1")
PERSON_2_NAME: str = os.getenv("PERSON_2_NAME", "Person 2")

# Error verbosity — True in local dev (default), False in production
DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

# Database — Postgres + pgvector. Defaults target the `db` service in docker-compose.
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://expense:expense_dev@db:5432/expense_hub",
)

# Fin agent harness — when enabled, the advisor router runs a tool-use loop
# instead of stuffing the full snapshot into a single chat call. Default off
# until eval coverage proves the agent path matches or beats the baseline.
ADVISOR_AGENT_MODE: bool = os.getenv("ADVISOR_AGENT_MODE", "false").lower() == "true"
ADVISOR_AGENT_MAX_ITERS: int = int(os.getenv("ADVISOR_AGENT_MAX_ITERS", "6"))

# Caps the number of confirmed user facts injected into the agent's
# system prompt each turn. Higher = Fin remembers more without needing
# `recall_about_user`; lower = leaner prompt and faster turns.
ADVISOR_MEMORY_INJECT_LIMIT: int = int(os.getenv("ADVISOR_MEMORY_INJECT_LIMIT", "30"))
