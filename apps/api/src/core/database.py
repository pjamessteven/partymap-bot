"""Database configuration and session management."""

from typing import AsyncGenerator, Generator

import redis
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings
from src.core.models import Base

settings = get_settings()

# Create Redis client for job tracking
redis_client = redis.from_url(settings.redis_url, decode_responses=True)

# Create async engine (for FastAPI)
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# Create sync engine for Celery tasks
# Convert asyncpg URL to psycopg2 URL
_sync_database_url = settings.database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
sync_engine = create_engine(
    _sync_database_url,
    echo=settings.debug,
    future=True,
)

# Create sync session factory for Celery
SessionLocal = sessionmaker(
    sync_engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for FastAPI."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_db() -> Generator[Session, None, None]:
    """Get sync database session for Celery tasks."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db() -> None:
    """Drop all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def get_sync_connection_string() -> str:
    """Get sync database connection string for LangGraph checkpointer."""
    return settings.database_url.replace("postgresql+asyncpg", "postgresql")
