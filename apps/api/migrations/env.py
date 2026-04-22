"""Alembic environment configuration."""

import asyncio
import os
import sys
from logging.config import fileConfig

# Add src to path BEFORE any other imports
# We need the parent directory in path so 'src' is recognized as a package
sys.path.insert(0, '/app')  # Docker path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))  # Local path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import models after path setup - do this lazily to catch errors
def get_target_metadata():
    """Get metadata with proper error handling."""
    try:
        from src.core.models import Base
        return Base.metadata
    except ImportError as e:
        print(f"ERROR importing src.core.models: {e}")
        print(f"Python path: {sys.path}")
        raise

def get_database_url():
    """Get database URL from settings."""
    try:
        from src.config import get_settings
        settings = get_settings()
        url = settings.database_url
        print(f"Database URL: {url[:50]}...")  # Debug log
        return url
    except Exception as e:
        print(f"ERROR getting database URL: {e}")
        import traceback
        traceback.print_exc()
        raise

# Set the database URL in alembic config
db_url = get_database_url()
print(f"Setting alembic URL...")
config.set_main_option("sqlalchemy.url", db_url)
print(f"Alembic URL set successfully")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=get_target_metadata(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=get_target_metadata())

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    url = config.get_main_option("sqlalchemy.url")
    print(f"Creating engine with URL: {url[:50]}...")
    connectable = create_async_engine(
        url,
        poolclass=pool.NullPool,
    )
    print(f"Engine created successfully")

    async with connectable.connect() as connection:
        print(f"Running migrations...")
        await connection.run_sync(do_run_migrations)
        print(f"Migrations complete")

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
