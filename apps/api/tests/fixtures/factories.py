"""Factory functions for creating test database objects."""

from datetime import datetime, timedelta
from uuid import uuid4

from src.core.models import Festival, FestivalState, RefreshApproval, PipelineSchedule


_USE_DEFAULT = object()


async def create_festival(
    db_session,
    name="Test Festival",
    source="exa",
    state=FestivalState.DISCOVERED,
    research_data=_USE_DEFAULT,
    **kwargs,
):
    """Create a festival in the test database."""
    if research_data is _USE_DEFAULT:
        research_data = {
            "name": name,
            "description": "A test festival description",
            "full_description": "A full test festival description that is long enough",
            "logo_url": "https://example.com/logo.jpg",
            "website_url": "https://example.com",
            "tags": ["music", "festival"],
            "media_items": [{"url": "https://example.com/photo.jpg", "caption": "Photo"}],
            "event_dates": [
                {
                    "start": datetime(2026, 7, 15, 14, 0, 0).isoformat(),
                    "end": datetime(2026, 7, 17, 23, 0, 0).isoformat(),
                    "location_description": "Berlin, Germany",
                    "location_country": "Germany",
                    "location_lat": 52.5,
                    "location_lng": 13.4,
                    "lineup": ["Artist A", "Artist B"],
                }
            ],
        }
    festival = Festival(
        name=name,
        source=source,
        state=state.value if hasattr(state, "value") else state,
        research_data=research_data,
        **kwargs,
    )
    db_session.add(festival)
    await db_session.commit()
    await db_session.refresh(festival)
    return festival


async def create_quarantined_festival(
    db_session,
    name="Failed Festival",
    error_category="transient",
    retry_count=5,
    **kwargs,
):
    """Create a quarantined festival."""
    return await create_festival(
        db_session,
        name=name,
        state=FestivalState.QUARANTINED.value,
        error_category=error_category,
        retry_count=retry_count,
        max_retries_reached=True,
        quarantined_at=datetime.utcnow(),
        quarantine_reason="Max retries reached",
        first_error_at=datetime.utcnow() - timedelta(days=1),
        last_error=f"[{error_category}] Something failed",
        **kwargs,
    )


async def create_refresh_approval(
    db_session,
    event_id=12345,
    event_date_id=67890,
    event_name="Test Festival",
    status="pending",
    **kwargs,
):
    """Create a refresh approval record."""
    approval = RefreshApproval(
        event_id=event_id,
        event_date_id=event_date_id,
        event_name=event_name,
        status=status,
        change_summary=["Updated dates"],
        research_confidence=0.95,
        current_data={"event": {}, "event_date": {}},
        proposed_changes={"event": {}, "event_date": {}},
        **kwargs,
    )
    db_session.add(approval)
    await db_session.commit()
    await db_session.refresh(approval)
    return approval


async def create_pipeline_schedule(
    db_session,
    task_type="discovery",
    enabled=True,
    hour=2,
    minute=0,
    day_of_week=None,
    **kwargs,
):
    """Create a pipeline schedule."""
    schedule = PipelineSchedule(
        task_type=task_type,
        enabled=enabled,
        hour=hour,
        minute=minute,
        day_of_week=day_of_week,
        **kwargs,
    )
    db_session.add(schedule)
    await db_session.commit()
    await db_session.refresh(schedule)
    return schedule
