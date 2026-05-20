"""
database.py — Async SQLAlchemy engine and session factory for SQL Server.

Provides:
  - engine           : AsyncEngine connected to SQL Server via aioodbc
  - AsyncSessionLocal: async_sessionmaker for creating database sessions
  - Base             : DeclarativeBase all ORM models inherit from
  - init_db()        : Creates all tables on startup (with retry loop)
  - get_db()         : FastAPI dependency that yields an AsyncSession per request
"""

from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Build URL-encoded ODBC connection string for mssql+aioodbc dialect
# ---------------------------------------------------------------------------
# Supports two authentication modes controlled by DB_TRUSTED_CONNECTION:
#
#   Windows Authentication (DB_TRUSTED_CONNECTION=yes):
#     Uses the current Windows user — no username/password required.
#     Typical for local development against a named instance.
#
#   SQL Server Authentication (DB_TRUSTED_CONNECTION not set / "no"):
#     Uses DB_USER + DB_PASSWORD.
#     Typical for Docker Compose / remote servers.
#
# Named instances (e.g. VIVOBOOK\MSSQLSERVER01) must NOT include a port —
# the ODBC driver resolves the port via SQL Server Browser automatically.
# Port is only appended when DB_PORT is explicitly set in the environment.
#
# TrustServerCertificate=yes — silences cert errors for self-signed / local certs.
# Encrypt=yes                — mandatory for ODBC Driver 18 (Driver 17 was opt-in).

_trusted = os.getenv("DB_TRUSTED_CONNECTION", "no").lower() in ("yes", "true", "1")

# Build authentication fragment
if _trusted:
    _auth_part = "Trusted_Connection=yes;"
else:
    _auth_part = (
        f"UID={os.getenv('DB_USER', 'sa')};"
        f"PWD={os.getenv('DB_PASSWORD', '')};"
    )

# Build server fragment — omit port for named instances
_server = os.getenv("DB_SERVER", "mssql")
_port   = os.getenv("DB_PORT", "")
_server_part = f"{_server},{_port}" if _port else _server

_odbc_str = (
    f"Driver={{{os.getenv('DB_DRIVER', 'ODBC Driver 18 for SQL Server')}}};"
    f"Server={_server_part};"
    f"Database={os.getenv('DB_NAME', 'gesture_lock')};"
    + _auth_part
    + "TrustServerCertificate=yes;"
    "Encrypt=yes;"
)

DATABASE_URL = f"mssql+aioodbc:///?odbc_connect={quote_plus(_odbc_str)}"

# expire_on_commit=False — prevents MissingGreenlet errors when accessing
# ORM attributes after an await in an async context
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def init_db() -> None:
    """
    Create all database tables on application startup.

    Retries up to 10 times with 3-second delays to handle the case where
    SQL Server is still initializing (common on first Docker Compose start).
    """
    from models import orm  # noqa: F401 — import models so Base.metadata is populated

    for attempt in range(1, 11):
        try:
            async with engine.begin() as conn:
                # run_sync required because create_all is a synchronous API
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables ready (attempt %d)", attempt)
            return
        except Exception as exc:
            if attempt == 10:
                logger.critical("Database unreachable after 10 attempts: %s", exc)
                raise
            logger.warning(
                "DB not ready (attempt %d/10): %s — retrying in 3 s", attempt, exc
            )
            await asyncio.sleep(3)


async def get_db():
    """
    FastAPI dependency — yields an AsyncSession and closes it after the request.

    Usage in a router:
        async def endpoint(db: AsyncSession = Depends(get_db)): ...
    """
    async with AsyncSessionLocal() as session:
        yield session
