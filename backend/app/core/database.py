"""Database configuration and session management.

Uses SQLAlchemy 2.x async API with SQLite in WAL mode.
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy import event, Engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL.replace("sqlite:", "sqlite+aiosqlite:"),
    echo=settings.DATABASE_ECHO,
    future=True,
    pool_pre_ping=True,
    poolclass=NullPool,  # No connection pooling for SQLite
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Declarative base for ORM models
Base = declarative_base()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session in FastAPI routes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables and enable WAL mode for SQLite.
    
    This will be called on application startup.
    """
    # Enable WAL mode and create tables in one managed async connection.
    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
        await conn.run_sync(Base.metadata.create_all)
        # Keep existing local installations forward-compatible between releases.
        columns = {
            row[1] for row in (await conn.exec_driver_sql("PRAGMA table_info(scan_sessions)")).fetchall()
        }
        additions = {
            "approved": "VARCHAR(10) DEFAULT 'false'",
            "mode": "VARCHAR(20) DEFAULT 'STANDARD'",
            "plan": "JSON DEFAULT '[]'",
            "results": "JSON DEFAULT '[]'",
            "error": "TEXT",
            "started_at": "DATETIME",
            "completed_at": "DATETIME",
        }
        for name, definition in additions.items():
            if name not in columns:
                await conn.exec_driver_sql(f"ALTER TABLE scan_sessions ADD COLUMN {name} {definition}")
        finding_columns = {
            row[1] for row in (await conn.exec_driver_sql("PRAGMA table_info(findings)")).fetchall()
        }
        finding_additions = {
            "tool": "VARCHAR(100) DEFAULT 'qsscope'",
            "stage": "VARCHAR(100) DEFAULT 'UNKNOWN'",
            "file_path": "VARCHAR(2048)",
            "line": "VARCHAR(30)",
            "message": "TEXT DEFAULT ''",
            "fingerprint": "VARCHAR(128) DEFAULT ''",
            "status": "VARCHAR(30) DEFAULT 'OPEN'",
        }
        for name, definition in finding_additions.items():
            if name not in finding_columns:
                await conn.exec_driver_sql(f"ALTER TABLE findings ADD COLUMN {name} {definition}")
        baseline_columns = {
            row[1] for row in (await conn.exec_driver_sql("PRAGMA table_info(baselines)")).fetchall()
        }
        if "fingerprints" not in baseline_columns:
            await conn.exec_driver_sql("ALTER TABLE baselines ADD COLUMN fingerprints JSON DEFAULT '[]'")


async def close_db() -> None:
    """Close database connection on application shutdown."""
    await engine.dispose()
