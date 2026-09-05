"""
Central configuration module — reads all environment variables exactly once.
Every other module imports constants from here instead of calling os.getenv() directly.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

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
    "postgresql+asyncpg://finfree:finfree_dev@db:5432/financial_freedom",
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

# --- Retirement projection assumptions -------------------------------------
# All four are long-run planning defaults, not forecasts, and every one of
# them is shown on the projection card and overridable per household. They
# live here so changing the house view is a single edit.

# Nominal expected annual return by stated risk tolerance, before inflation.
# Broadly: a bond-heavy mix, a 60/40 mix, and an equity-heavy mix.
RETIREMENT_RETURN_PCT_BY_RISK: dict = {
    "conservative": 4.0,
    "balanced": 6.0,
    "aggressive": 7.5,
}

# Long-run annual inflation. Subtracted from the nominal return so the
# projection is stated in today's dollars — a nominal figure is a large
# number that reads as wealth and is not.
RETIREMENT_INFLATION_PCT: float = 2.5

# Annual share of the pot a retiree can draw and expect it to last. The
# target pot is the desired annual spend divided by this.
RETIREMENT_WITHDRAWAL_RATE_PCT: float = 4.0

# The optimistic and pessimistic scenarios are the base real return moved by
# this many percentage points in each direction.
RETIREMENT_SCENARIO_SPREAD_PCT: float = 2.0

# When the household hasn't stated a retirement spending level, assume this
# share of what it spends today. Always reported as an estimate, never
# silently substituted.
RETIREMENT_SPEND_SHARE_OF_TODAY: float = 0.80

# --- Portfolio quality ------------------------------------------------------
# A single position worth more than this share of the portfolio is the
# widely used rule of thumb for concentration risk. Applied to individual
# securities only — a broad fund at 20% is not the same exposure.
PORTFOLIO_CONCENTRATION_THRESHOLD_PCT: float = 10.0

# Target equity/bond/cash mix per stated risk tolerance. House defaults, shown
# on the card next to the actual mix; the app never suggests trades to close
# the gap because it cannot see the tax consequences of one.
PORTFOLIO_TARGET_ALLOCATION_BY_RISK: dict = {
    "conservative": {"equity": 30.0, "bond": 60.0, "cash": 10.0},
    "balanced": {"equity": 60.0, "bond": 30.0, "cash": 10.0},
    "aggressive": {"equity": 85.0, "bond": 10.0, "cash": 5.0},
}

# Trailing windows for the "how your current mix would have performed" card,
# and the index it is shown against.
PORTFOLIO_BACKTEST_PERIODS: tuple = ("1mo", "1y", "5y")
PORTFOLIO_BENCHMARK_SYMBOL: str = "SPY"

# Share of the portfolio that must be priceable before a backtest figure is
# shown at all. Below this the number describes a different portfolio than
# the user's, so the card names the unpriceable symbols instead.
PORTFOLIO_BACKTEST_MIN_COVERAGE_PCT: float = 80.0

# A fund charging more than this is worth a second look — index equivalents
# in most categories sit an order of magnitude below it.
PORTFOLIO_HIGH_FEE_PCT: float = 0.50

# --- Contribution limits ----------------------------------------------------
# Keyed by calendar year on purpose. A year absent from this map makes the
# headroom view report itself unavailable and name the missing year; it never
# falls back to the previous year's figure. A silently stale limit tells
# someone they have room they do not have, and the penalty for
# over-contributing is real money.
#
#   2025 — IRS Notice 2024-80, published November 2024.
#   2026 — IRS Notice 2025-67, published November 2025.
#
# ``ira`` pools traditional and Roth IRAs, which share one annual limit.
# ``workplace`` is the elective-deferral limit for 401(k)/403(b)/457(b) plans,
# which is separate from the IRA limit. HSAs are deliberately absent: the
# limit depends on whether the coverage is self-only or family, which nothing
# in this app can see, so HSA contributions are reported without a limit
# rather than measured against a guessed one. SEP and SIMPLE IRAs are absent
# for the same reason — their limits are a function of compensation.
CONTRIBUTION_LIMITS_BY_YEAR: dict = {
    2025: {
        "ira": 7000.0, "ira_catch_up": 1000.0,
        "workplace": 23500.0, "workplace_catch_up": 7500.0,
    },
    2026: {
        "ira": 7500.0, "ira_catch_up": 1100.0,
        "workplace": 24500.0, "workplace_catch_up": 8000.0,
    },
}

# Catch-up contributions are allowed from the calendar year the taxpayer
# turns this age, not from their birthday.
CONTRIBUTION_CATCH_UP_AGE: int = 50
