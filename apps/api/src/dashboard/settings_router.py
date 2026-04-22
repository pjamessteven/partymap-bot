"""System settings API routes.

This module provides endpoints for managing global system settings,
including the auto_process toggle that controls whether festivals
are automatically processed through the pipeline or require manual action.

All settings are stored in the database and persist across restarts.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.database import get_db
from src.core.models import SystemSettings
from src.core.schemas import (
    AutoProcessSetting,
    SettingCategory,
    SettingValueType,
    SettingsListResponse,
    SystemSettingResponse,
    SystemSettingUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


# Helper functions


def _parse_setting_value(setting: SystemSettings) -> Any:
    """Parse a setting value based on its type.

    Args:
        setting: The SystemSettings database model instance

    Returns:
        The parsed value in its proper Python type
    """
    if setting.value_type == "boolean":
        return setting.value.lower() == "true"
    elif setting.value_type == "integer":
        return int(setting.value)
    elif setting.value_type == "float":
        return float(setting.value)
    elif setting.value_type == "json":
        return json.loads(setting.value)
    else:  # string
        return setting.value


def _validate_and_stringify_value(value: Any, expected_type: str) -> str:
    """Validate a value matches the expected type and convert to string for storage.

    Args:
        value: The value to validate and convert
        expected_type: The expected value_type from the database

    Returns:
        String representation of the value for storage

    Raises:
        ValueError: If the value doesn't match the expected type
    """
    if expected_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"Expected boolean, got {type(value).__name__}")
        return "true" if value else "false"

    elif expected_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"Expected integer, got {type(value).__name__}")
        return str(value)

    elif expected_type == "float":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"Expected float, got {type(value).__name__}")
        return str(float(value))

    elif expected_type == "json":
        if isinstance(value, str):
            # Validate it's valid JSON
            json.loads(value)
            return value
        return json.dumps(value)

    else:  # string
        return str(value)


def _setting_to_response(setting: SystemSettings) -> SystemSettingResponse:
    """Convert a SystemSettings model to a response schema.

    Args:
        setting: The database model instance

    Returns:
        SystemSettingResponse with properly parsed value
    """
    return SystemSettingResponse(
        id=setting.id,
        key=setting.key,
        value=_parse_setting_value(setting),
        value_type=SettingValueType(setting.value_type),
        description=setting.description,
        editable=setting.editable,
        category=SettingCategory(setting.category),
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )


async def _get_setting_by_key(db: AsyncSession, key: str) -> Optional[SystemSettings]:
    """Get a setting by its key.

    Args:
        db: Database session
        key: Setting key

    Returns:
        SystemSettings or None if not found
    """
    result = await db.execute(select(SystemSettings).where(SystemSettings.key == key))
    return result.scalar_one_or_none()


async def _get_setting_value(db: AsyncSession, key: str, default: Any = None) -> Any:
    """Get a setting value by key, returning default if not found.

    Args:
        db: Database session
        key: Setting key
        default: Default value if setting not found

    Returns:
        Parsed setting value or default
    """
    setting = await _get_setting_by_key(db, key)
    if setting is None:
        return default
    return _parse_setting_value(setting)


# API Endpoints


@router.get(
    "",
    response_model=SettingsListResponse,
    summary="List all system settings",
    description="""
    Get all system settings grouped by category.

    Returns all configurable settings including:
    - **auto_process**: Whether festivals are automatically processed
    - **max_cost_per_day**: Daily cost budget in cents
    - **research_auto_retry**: Whether to auto-retry failed research

    Settings are grouped by category for easier UI rendering.
    """,
    response_description="All system settings organized by category",
)
async def list_settings(
    category: Optional[SettingCategory] = Query(
        None,
        description="Filter settings by category",
        examples=["pipeline", "cost"],
    ),
    db: AsyncSession = Depends(get_db),
) -> SettingsListResponse:
    """List all system settings, optionally filtered by category."""
    query = select(SystemSettings)

    if category:
        query = query.where(SystemSettings.category == category.value)

    query = query.order_by(SystemSettings.category, SystemSettings.key)

    result = await db.execute(query)
    settings = result.scalars().all()

    setting_responses = [_setting_to_response(s) for s in settings]

    # Group by category
    by_category: Dict[str, List[SystemSettingResponse]] = {}
    for setting in setting_responses:
        cat = setting.category.value
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(setting)

    return SettingsListResponse(
        settings=setting_responses,
        by_category=by_category,
    )


@router.get(
    "/{key}",
    response_model=SystemSettingResponse,
    summary="Get a specific setting",
    description="""
    Get a single setting by its key.

    The value is returned in its proper type (boolean, integer, etc.)
    based on the value_type field.
    """,
    response_description="The requested setting with parsed value",
)
async def get_setting(
    key: str,
    db: AsyncSession = Depends(get_db),
) -> SystemSettingResponse:
    """Get a specific setting by key.

    Args:
        key: Setting key (e.g., 'auto_process', 'max_cost_per_day')
        db: Database session

    Returns:
        The requested setting with parsed value
    """
    setting = await _get_setting_by_key(db, key)

    if not setting:
        raise HTTPException(
            status_code=404,
            detail=f"Setting not found: {key}",
        )

    return _setting_to_response(setting)


@router.put(
    "/{key}",
    response_model=SystemSettingResponse,
    summary="Update a setting",
    description="""
    Update the value of a system setting.

    The value must match the setting's expected type:
    - **boolean**: true or false
    - **integer**: Whole numbers
    - **float**: Decimal numbers
    - **string**: Any text
    - **json**: Valid JSON object/array

    Only editable settings can be modified. Attempting to modify
    a read-only setting will return a 400 error.
    """,
    response_description="The updated setting with new value",
)
async def update_setting(
    key: str,
    update: SystemSettingUpdate,
    db: AsyncSession = Depends(get_db),
) -> SystemSettingResponse:
    """Update a system setting value.

    Args:
        key: The setting key to update
        update: Contains the new value
        db: Database session

    Returns:
        Updated setting response

    Raises:
        HTTPException: 404 if setting not found, 400 if not editable or invalid value
    """
    setting = await _get_setting_by_key(db, key)

    if not setting:
        raise HTTPException(
            status_code=404,
            detail=f"Setting not found: {key}",
        )

    if not setting.editable:
        raise HTTPException(
            status_code=400,
            detail=f"Setting '{key}' is read-only and cannot be modified",
        )

    # Validate dependent settings logic
    # Cannot enable auto_research_on_discover or auto_sync_on_research_success 
    # when auto_process is disabled
    if key in ["auto_research_on_discover", "auto_sync_on_research_success"]:
        if update.value is True:  # Trying to enable
            auto_process_setting = await _get_setting_by_key(db, "auto_process")
            if auto_process_setting and auto_process_setting.value.lower() != "true":
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot enable '{key}' because auto_process is disabled. Enable auto_process first.",
                )
    
    # When disabling auto_process, we should also disable dependent settings
    # But we'll warn instead of auto-disabling to be explicit
    if key == "auto_process" and update.value is False:
        # Check if dependent settings are enabled
        dependent_enabled = []
        for dep_key in ["auto_research_on_discover", "auto_sync_on_research_success"]:
            dep_setting = await _get_setting_by_key(db, dep_key)
            if dep_setting and dep_setting.value.lower() == "true":
                dependent_enabled.append(dep_key)
        
        if dependent_enabled:
            # We'll allow it but warn in response
            # In practice, the auto-process enable/disable endpoints handle this properly
            # This is just for direct setting updates
            logger.warning(f"Disabling auto_process while dependent settings are enabled: {dependent_enabled}")

    # Validate and convert value
    try:
        string_value = _validate_and_stringify_value(update.value, setting.value_type)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid value for type '{setting.value_type}': {str(e)}",
        )

    # Update setting
    setting.value = string_value
    await db.commit()
    await db.refresh(setting)

    logger.info(f"Updated setting '{key}' to: {string_value}")

    return _setting_to_response(setting)


@router.get(
    "/auto-process/status",
    response_model=AutoProcessSetting,
    summary="Get auto-process status",
    description="""
    Get the current status of the auto_process setting.

    This is a convenience endpoint for the commonly accessed auto_process setting.
    When auto_process is **enabled**, festivals automatically flow through the pipeline:
    DISCOVERED → deduplication → research → sync

    When **disabled**, festivals remain in their current state until manually triggered
    via the manual action endpoints.
    """,
    response_description="Current auto-process configuration",
)
async def get_auto_process_status(
    db: AsyncSession = Depends(get_db),
) -> AutoProcessSetting:
    """Get the auto_process setting value."""
    enabled = await _get_setting_value(db, "auto_process", default=False)

    return AutoProcessSetting(
        enabled=bool(enabled),
    )


@router.put(
    "/auto-process/enable",
    response_model=AutoProcessSetting,
    summary="Enable auto-process",
    description="""
    Enable automatic festival processing.

    When enabled, festivals discovered by the discovery agent will automatically:
    1. Run deduplication check
    2. Queue for research (if needed)
    3. Sync to PartyMap (when research complete)

    This is the default production mode.
    """,
)
async def enable_auto_process(
    db: AsyncSession = Depends(get_db),
) -> AutoProcessSetting:
    """Enable automatic festival processing."""
    setting = await _get_setting_by_key(db, "auto_process")

    if not setting:
        raise HTTPException(
            status_code=404,
            detail="auto_process setting not found",
        )

    setting.value = "true"
    
    # Also enable dependent settings when master is enabled
    dependent_settings = ["auto_research_on_discover", "auto_sync_on_research_success"]
    for dep_key in dependent_settings:
        dep_setting = await _get_setting_by_key(db, dep_key)
        if dep_setting and dep_setting.editable:
            dep_setting.value = "true"
            logger.info(f"Enabled dependent setting: {dep_key}")
    
    await db.commit()

    logger.info("Auto-process enabled with dependent settings")

    return AutoProcessSetting(
        enabled=True,
        description="Auto-process enabled. All dependent pipeline settings (research, sync) are also enabled.",
    )


@router.put(
    "/auto-process/disable",
    response_model=AutoProcessSetting,
    summary="Disable auto-process",
    description="""
    Disable automatic festival processing (manual mode).

    When disabled, festivals will stay in their current state after discovery:
    - New festivals remain in **DISCOVERED** state
    - You must manually trigger deduplication, research, and sync
      using the individual festival action endpoints

    This is useful for testing and debugging individual pipeline stages.
    """,
)
async def disable_auto_process(
    db: AsyncSession = Depends(get_db),
) -> AutoProcessSetting:
    """Disable automatic festival processing (enable manual mode)."""
    setting = await _get_setting_by_key(db, "auto_process")

    if not setting:
        raise HTTPException(
            status_code=404,
            detail="auto_process setting not found",
        )

    setting.value = "false"
    
    # Also disable dependent settings when master is disabled
    dependent_settings = ["auto_research_on_discover", "auto_sync_on_research_success"]
    for dep_key in dependent_settings:
        dep_setting = await _get_setting_by_key(db, dep_key)
        if dep_setting and dep_setting.editable:
            dep_setting.value = "false"
            logger.info(f"Disabled dependent setting: {dep_key}")
    
    await db.commit()

    logger.info("Auto-process disabled (manual mode) with dependent settings")

    return AutoProcessSetting(
        enabled=False,
        description="Manual mode enabled. Auto-research and auto-sync are disabled. Festivals will not auto-process. Use individual festival action endpoints to trigger pipeline stages.",
    )


# Public helper for other modules


async def is_auto_process_enabled(db: AsyncSession) -> bool:
    """Check if auto_process is currently enabled.

    This is a convenience function for use in async pipeline tasks.

    Args:
        db: Database session

    Returns:
        True if auto_process is enabled, False otherwise
    """
    return await _get_setting_value(db, "auto_process", default=False)


def is_auto_process_enabled_sync(session) -> bool:
    """Synchronous version for use in Celery tasks.

    This is a convenience function for use in synchronous Celery tasks.

    Args:
        session: SQLAlchemy session (from SessionLocal in pipeline tasks)

    Returns:
        True if auto_process is enabled, False otherwise
    """
    from sqlalchemy import select
    from src.core.models import SystemSettings

    result = session.execute(select(SystemSettings).where(SystemSettings.key == "auto_process"))
    setting = result.scalar_one_or_none()

    if not setting:
        return False

    return setting.value.lower() == "true"


def is_setting_enabled_sync(session, key: str) -> bool:
    """Generic synchronous setting checker for use in Celery tasks.

    This is a convenience function for use in synchronous Celery tasks.

    Args:
        session: SQLAlchemy session (from SessionLocal in pipeline tasks)
        key: Setting key to check

    Returns:
        True if setting is enabled (value is "true"), False otherwise
    """
    from sqlalchemy import select
    from src.core.models import SystemSettings

    result = session.execute(select(SystemSettings).where(SystemSettings.key == key))
    setting = result.scalar_one_or_none()

    if not setting:
        return False

    # For dependent settings (auto_research_on_discover, auto_sync_on_research_success),
    # also check if auto_process is enabled
    if key in ["auto_research_on_discover", "auto_sync_on_research_success"]:
        # Check if auto_process is enabled first
        auto_process_enabled = is_auto_process_enabled_sync(session)
        if not auto_process_enabled:
            return False
    
    return setting.value.lower() == "true"
