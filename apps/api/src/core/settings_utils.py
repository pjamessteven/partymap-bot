"""Settings utility functions for synchronous and async access."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import SystemSettings


async def get_setting_value(db: AsyncSession, key: str, default=None):
    """Get a setting value (async version).

    Args:
        db: Async SQLAlchemy session
        key: Setting key
        default: Default value if setting not found

    Returns:
        Setting value or default
    """
    try:
        result = await db.execute(
            select(SystemSettings).where(SystemSettings.key == key)
        )
        setting = result.scalar_one_or_none()
        return setting.value if setting else default
    except Exception:
        return default


async def update_setting(db: AsyncSession, key: str, value: str) -> SystemSettings:
    """Update a setting value (async version).

    Args:
        db: Async SQLAlchemy session
        key: Setting key
        value: New value

    Returns:
        Updated setting
    """
    result = await db.execute(
        select(SystemSettings).where(SystemSettings.key == key)
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = value
    else:
        setting = SystemSettings(key=key, value=value)
        db.add(setting)

    await db.commit()
    return setting


def is_setting_enabled_sync(session, key: str, default: bool = False) -> bool:
    """Check if a boolean setting is enabled (synchronous version).

    Args:
        session: SQLAlchemy session
        key: Setting key
        default: Default value if setting not found

    Returns:
        True if setting exists and value is "true", False otherwise
    """
    try:
        result = session.execute(
            select(SystemSettings).where(SystemSettings.key == key)
        )
        setting = result.scalar_one_or_none()
        if setting and setting.value:
            return setting.value.lower() == "true"
        return default
    except Exception:
        return default


def is_auto_process_enabled_sync(session) -> bool:
    """Check if auto_process is enabled.

    Args:
        session: SQLAlchemy session

    Returns:
        True if auto_process is enabled
    """
    return is_setting_enabled_sync(session, "auto_process_enabled", default=False)


def get_setting_value_sync(session, key: str, default=None):
    """Get a setting value.

    Args:
        session: SQLAlchemy session
        key: Setting key
        default: Default value if setting not found

    Returns:
        Setting value or default
    """
    try:
        result = session.execute(
            select(SystemSettings).where(SystemSettings.key == key)
        )
        setting = result.scalar_one_or_none()
        return setting.value if setting else default
    except Exception:
        return default
