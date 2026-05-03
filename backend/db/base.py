"""SQLAlchemy engines, sessionmakers, and declarative base.

Two engines coexist:

- ``engine`` — async (asyncpg). Used by Phase 6 RAG code and any future
  async repositories.
- ``sync_engine`` — sync (psycopg2). Used by ``backend/store.py::PgStore``
  because routers call ``state.stored_transactions[tid] = ...`` from sync
  call-sites that pre-date async. Also used by conftest's TRUNCATE reset.
"""
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# DATABASE_URL uses ``postgresql+asyncpg://`` for async. Swap the driver
# prefix so the sync engine uses psycopg2 against the same database.
_SYNC_URL = DATABASE_URL.replace("+asyncpg", "+psycopg2")
sync_engine: Engine = create_engine(_SYNC_URL, pool_pre_ping=True, future=True)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session scoped to the request."""
    async with async_session_factory() as session:
        yield session
