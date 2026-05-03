"""Application entry point — app setup, middleware, and router registration."""
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import state
from config import (
    TELLER_ACCESS_TOKENS, SPREADSHEET_ID, CREDENTIALS_FILE, TELLER_ENVIRONMENT,
)

# Patterns used in tests / docs that should never be real production tokens.
_FAKE_TOKEN_RE = re.compile(r"^tok_(abc|one|two|test|fake|dummy)", re.IGNORECASE)
from routers import (
    accounts, advisor, alerts, balances, bills, budgets, credit_health, dashboard,
    goals, insights, layout, profile, sheets, tools,
)
from routers import teller as teller_router
from routers import transactions

# Re-export singletons so existing test imports (``from main import ...``) keep working.
stored_transactions = state.stored_transactions
_balances_cache     = state._balances_cache
teller              = state.teller

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not SPREADSHEET_ID:
        logger.warning("SPREADSHEET_ID not configured — Google Sheets export will not work")
    if not TELLER_ACCESS_TOKENS:
        logger.warning("TELLER_API_KEY not configured — Teller sync will not work")
    if not CREDENTIALS_FILE.exists():
        logger.warning(
            f"credentials.json not found at {CREDENTIALS_FILE} — Google Sheets export will fail"
        )
    # Surface stale/fake tokens so zombie "Connection Error" accounts in the
    # Accounts modal are easy to diagnose.  Non-destructive — use
    # `py backend/scripts/prune_tokens.py` to clean them out.
    fakes = [t for t in TELLER_ACCESS_TOKENS if _FAKE_TOKEN_RE.match(t)]
    if fakes:
        logger.warning(
            f"TELLER_API_KEY contains {len(fakes)} token(s) matching test patterns "
            "(tok_abc…, tok_one, tok_two, tok_test…).  Run "
            "`py backend/scripts/prune_tokens.py` to remove them."
        )

    # Phase 6: catch up on any ``conversation_turns`` rows whose embeddings
    # weren't written (Ollama was down, prior crash, migration from legacy
    # json_stores conversations, etc.). No-op when everything is current.
    try:
        from embeddings import embed_pending_turns, embed_pending_transactions
        count = await embed_pending_turns()
        if count:
            logger.info(f"[startup] Backfilled {count} conversation-turn embeddings")
        txn_count = await embed_pending_transactions()
        if txn_count:
            logger.info(f"[startup] Backfilled {txn_count} transaction embeddings")
    except Exception as e:
        logger.warning(f"[startup] Embedding backfill skipped: {e}")

    yield


app = FastAPI(title="Bank Statement API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transactions.router, prefix="/api")
app.include_router(accounts.router,     prefix="/api")
app.include_router(teller_router.router, prefix="/api")
app.include_router(balances.router,     prefix="/api")
app.include_router(sheets.router,       prefix="/api")
app.include_router(tools.router,        prefix="/api")
app.include_router(insights.router,     prefix="/api")
app.include_router(dashboard.router,    prefix="/api")
app.include_router(advisor.router,      prefix="/api")
app.include_router(budgets.router,      prefix="/api")
app.include_router(goals.router,        prefix="/api")
app.include_router(profile.router,      prefix="/api")
app.include_router(layout.router,       prefix="/api")
app.include_router(alerts.router,       prefix="/api")
app.include_router(bills.router,        prefix="/api")
app.include_router(credit_health.router, prefix="/api")


@app.get("/")
async def root():
    return {"message": "Bank Statement API is running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "environment": TELLER_ENVIRONMENT}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
