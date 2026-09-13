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


async def close_db() -> None:
    """Close database connection on application shutdown."""
    await engine.dispose()
