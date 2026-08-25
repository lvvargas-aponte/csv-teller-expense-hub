"""Application entry point — app setup, middleware, and router registration."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import state
from config import SPREADSHEET_ID, CREDENTIALS_FILE, SIMPLEFIN_ACCESS_URLS

from routers import (
    accounts, advisor, alerts, balances, bills, budgets,
    credit_health, dashboard, digest, documents, goals, health, identity, insights,
    investments, layout, profile, seeds, sheets, snaptrade,
    subscriptions, sync, tools, user_facts,
)
# Aliased: these routers share a name with a top-level service module.
from routers import category_rules as category_rules_router
from routers import retirement as retirement_router
from routers import simplefin as simplefin_router
from routers import tax as tax_router
from routers import transactions

# Re-export singletons so existing test imports (``from main import ...``) keep working.
stored_transactions = state.stored_transactions
_balances_cache     = state._balances_cache

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
    if not SIMPLEFIN_ACCESS_URLS:
        logger.warning("SIMPLEFIN_ACCESS_URLS not configured — SimpleFIN sync will not work")
    if not CREDENTIALS_FILE.exists():
        logger.warning(
            f"credentials.json not found at {CREDENTIALS_FILE} — Google Sheets export will fail"
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

    # Recurring data syncs (weekly transaction/holdings pulls, etc.) —
    # jobs live in the scheduled_tasks table, managed via Fin's tools.
    scheduler_task = None
    try:
        from scheduler import start_scheduler
        scheduler_task = start_scheduler()
    except Exception as e:
        logger.warning(f"[startup] Scheduler not started: {e}")

    yield

    if scheduler_task is not None:
        scheduler_task.cancel()


app = FastAPI(title="Bank Statement API", version="1.0.0", lifespan=lifespan)

# CRA dev server hosts; production deploys terminate at a reverse proxy and
# don't hit FastAPI directly, so this allowlist intentionally only covers
# local development.
_DEV_FRONTEND_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transactions.router, prefix="/api")
app.include_router(accounts.router,     prefix="/api")
app.include_router(simplefin_router.router, prefix="/api")
app.include_router(balances.router,     prefix="/api")
app.include_router(sheets.router,       prefix="/api")
app.include_router(tools.router,        prefix="/api")
app.include_router(insights.router,     prefix="/api")
app.include_router(dashboard.router,    prefix="/api")
app.include_router(advisor.router,      prefix="/api")
app.include_router(budgets.router,      prefix="/api")
app.include_router(goals.router,        prefix="/api")
app.include_router(profile.router,      prefix="/api")
app.include_router(category_rules_router.router, prefix="/api")
app.include_router(layout.router,       prefix="/api")
app.include_router(alerts.router,       prefix="/api")
app.include_router(bills.router,        prefix="/api")
app.include_router(credit_health.router, prefix="/api")
app.include_router(health.router,       prefix="/api")
app.include_router(documents.router,    prefix="/api")
app.include_router(seeds.router,        prefix="/api")
app.include_router(snaptrade.router,    prefix="/api")
app.include_router(investments.router,  prefix="/api")
app.include_router(user_facts.router,   prefix="/api")
app.include_router(subscriptions.router, prefix="/api")
app.include_router(digest.router,       prefix="/api")
app.include_router(identity.router,      prefix="/api")
app.include_router(sync.router,          prefix="/api")
app.include_router(retirement_router.router, prefix="/api")
app.include_router(tax_router.router, prefix="/api")


# Static help site — built from /docs by mkdocs into /docs/site.
# Mounted at /help so the frontend Help button can open same-origin docs.
_HELP_SITE_DIR = Path(__file__).resolve().parent.parent / "site"
if _HELP_SITE_DIR.is_dir():
    app.mount("/help", StaticFiles(directory=str(_HELP_SITE_DIR), html=True), name="help")
else:
    logger.warning(
        f"Help site not found at {_HELP_SITE_DIR} — run `mkdocs build` in /docs to generate it"
    )


@app.get("/")
async def root() -> dict:
    return {"message": "Bank Statement API is running"}


@app.get("/health")
async def health_check() -> dict:
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
