"""Database initialization script."""

import asyncio

from sqlalchemy import select

from src.config import get_settings
from src.core.database import init_db, AsyncSessionLocal
from src.core.models import DiscoveryQuery, PipelineSchedule, SystemSettings

# Pre-populated discovery queries
DISCOVERY_QUERIES = [
    # Countries
    ("music festivals in Spain 2026 2027", "country"),
    ("music festivals in Germany 2026 2027", "country"),
    ("music festivals in USA 2026 2027", "country"),
    ("music festivals in Brazil 2026 2027", "country"),
    ("music festivals in Australia 2026 2027", "country"),
    ("music festivals in Netherlands 2026 2027", "country"),
    ("music festivals in Portugal 2026 2027", "country"),
    ("music festivals in France 2026 2027", "country"),
    ("music festivals in UK 2026 2027", "country"),
    ("music festivals in Italy 2026 2027", "country"),
    # Cities
    ("music festivals in Berlin 2026 2027", "city"),
    ("music festivals in Amsterdam 2026 2027", "city"),
    ("music festivals in Barcelona 2026 2027", "city"),
    ("music festivals in London 2026 2027", "city"),
    ("music festivals in Los Angeles 2026 2027", "city"),
    ("music festivals in Miami 2026 2027", "city"),
    # Genres
    ("psytrance festivals 2026 2027", "genre"),
    ("techno festivals 2026 2027", "genre"),
    ("hip hop festivals 2026 2027", "genre"),
    ("electronic music festivals 2026 2027", "genre"),
    ("rock festivals 2026 2027", "genre"),
    ("jazz festivals 2026 2027", "genre"),
    ("reggae festivals 2026 2027", "genre"),
    ("indie music festivals 2026 2027", "genre"),
    # Special
    ("goabase festivals 2026 2027", "genre"),
]


async def seed_discovery_queries(session):
    """Seed discovery queries if not already present."""
    for query_text, category in DISCOVERY_QUERIES:
        # Check if exists
        existing = await session.execute(
            select(DiscoveryQuery).where(DiscoveryQuery.query == query_text)
        )
        if existing.scalar_one_or_none():
            print(f"Query already exists: {query_text}")
            continue

        query = DiscoveryQuery(
            query=query_text,
            category=category,
            enabled=True,
        )
        session.add(query)
        print(f"Added query: {query_text}")

    await session.commit()
    print(f"Seeded {len(DISCOVERY_QUERIES)} discovery queries")


# Pre-populated pipeline schedules (all disabled by default)
PIPELINE_SCHEDULES = [
    ("discovery", 2, 0, None),  # Daily at 2:00 AM UTC
    ("goabase_sync", 2, 0, 0),  # Monday at 2:00 AM UTC (0=Monday)
    ("cleanup_failed", 3, 0, None),  # Daily at 3:00 AM UTC
]


async def seed_pipeline_schedules(session):
    """Seed pipeline schedules if not already present."""
    for task_type, hour, minute, day_of_week in PIPELINE_SCHEDULES:
        # Check if exists
        existing = await session.execute(
            select(PipelineSchedule).where(PipelineSchedule.task_type == task_type)
        )
        if existing.scalar_one_or_none():
            print(f"Schedule already exists: {task_type}")
            continue

        schedule = PipelineSchedule(
            task_type=task_type,
            enabled=False,  # All schedules disabled by default
            hour=hour,
            minute=minute,
            day_of_week=day_of_week,
        )
        session.add(schedule)
        print(f"Added schedule: {task_type} (disabled)")

    await session.commit()
    print(f"Seeded {len(PIPELINE_SCHEDULES)} pipeline schedules (all disabled)")


# Pre-populated system settings
SYSTEM_SETTINGS = [
    (
        "auto_process",
        "false",
        "boolean",
        "Master switch for automatic festival processing. When enabled, auto_research_on_discover and auto_sync_on_research_success are also enabled. When disabled, all auto-processing stops.",
        True,
        "pipeline",
    ),
    (
        "auto_research_on_discover",
        "false",
        "boolean",
        "Automatically queue festivals for research after successful deduplication. Requires auto_process to be enabled.",
        True,
        "pipeline",
    ),
    (
        "auto_sync_on_research_success",
        "false",
        "boolean",
        "Automatically queue researched festivals for sync to PartyMap when research is successful. Requires auto_process to be enabled.",
        True,
        "pipeline",
    ),
    (
        "max_cost_per_day",
        "1000",
        "integer",
        "Maximum cost in cents allowed per day for all operations.",
        True,
        "cost",
    ),
    (
        "research_auto_retry",
        "true",
        "boolean",
        "Automatically retry failed research tasks up to max_retries.",
        True,
        "pipeline",
    ),
    # Goabase sync settings
    (
        "goabase_sync_enabled",
        "true",
        "boolean",
        "Enable automatic Goabase sync. When disabled, Goabase sync will not run automatically.",
        True,
        "goabase",
    ),
    (
        "goabase_sync_frequency",
        "weekly",
        "string",
        "Frequency of automatic Goabase sync. Options: daily, weekly, monthly.",
        True,
        "goabase",
    ),
    (
        "goabase_sync_day",
        "sunday",
        "string",
        "Day of week for Goabase sync (when frequency is weekly). Options: monday, tuesday, wednesday, thursday, friday, saturday, sunday.",
        True,
        "goabase",
    ),
    (
        "goabase_sync_hour",
        "2",
        "integer",
        "Hour of day (0-23) for Goabase sync to run.",
        True,
        "goabase",
    ),
]


async def seed_system_settings(session):
    """Seed system settings if not already present."""
    for key, value, value_type, description, editable, category in SYSTEM_SETTINGS:
        # Check if exists
        existing = await session.execute(select(SystemSettings).where(SystemSettings.key == key))
        if existing.scalar_one_or_none():
            print(f"Setting already exists: {key}")
            continue

        setting = SystemSettings(
            key=key,
            value=value,
            value_type=value_type,
            description=description,
            editable=editable,
            category=category,
        )
        session.add(setting)
        print(f"Added setting: {key} = {value}")

    await session.commit()
    print(f"Seeded {len(SYSTEM_SETTINGS)} system settings")


async def main():
    """Initialize database."""
    print("Initializing database...")
    await init_db()
    print("Database tables created!")

    # Seed data
    async with AsyncSessionLocal() as session:
        await seed_discovery_queries(session)
        await seed_pipeline_schedules(session)
        await seed_system_settings(session)

    print("Database initialization complete!")


if __name__ == "__main__":
    asyncio.run(main())
