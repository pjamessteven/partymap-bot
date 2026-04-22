"""Dedicated Goabase sync pipeline - skips research, goes direct to PartyMap."""

import asyncio
import logging
import time
from datetime import datetime
from typing import List, Optional

from celery import Celery
from sqlalchemy import select

from src.config import get_settings
from src.core.database import SessionLocal
from src.core.job_tracker import JobTracker, JobType
from src.core.models import Festival, FestivalState
from src.core.schemas import DuplicateCheckResult, EventDateData, FestivalData
from src.partymap.client import PartyMapClient
from src.services.goabase_client import GoabaseClient
from src.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

settings = get_settings()
celery_app = Celery(
    "partymap_bot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

REQUEST_DELAY = 0.5  # seconds between Goabase requests


@celery_app.task(bind=True, max_retries=3)
def goabase_sync_pipeline(self):
    """
    Sync ALL Goabase events directly to PartyMap.

    Flow:
    1. Fetch all party URLs from Goabase
    2. For each party:
       - Fetch full details
       - Skip if past event
       - Check if exists in PartyMap by URL
       - Compare modified dates
       - Create new or update existing
       - Extract lineup via LLM if needed
    3. Add 0.5s delay between requests
    """
    session = SessionLocal()
    stats = {
        "total": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "past": 0,
    }

    try:
        # Mark job as started
        JobTracker.start_job(JobType.GOABASE_SYNC, self.request.id)

        async def _sync():
            goabase = GoabaseClient(settings)
            partymap = PartyMapClient(settings)
            llm = LLMClient(settings)

            logger.info(
                f"Using PartyMap API: {settings.effective_partymap_base_url} (dev_mode={settings.dev_mode})"
            )

            if settings.dev_mode:
                logger.warning("DEV MODE: Make sure PartyMap server is running on the host machine")
                logger.warning(
                    "If using Docker, update DEV_PARTYMAP_BASE_URL in .env to: http://host.docker.internal:5000/api"
                )

            try:
                # Fetch all party URLs
                logger.info("Fetching Goabase party list...")
                parties = await goabase.get_party_list()
                stats["total"] = len(parties)
                logger.info(f"Found {len(parties)} parties in Goabase")

                for i, party in enumerate(parties, 1):
                    try:
                        logger.info(f"Processing {i}/{len(parties)}: {party.name}")

                        # Fetch full details
                        festival_data = await goabase.get_party_details(party.url)
                        if not festival_data:
                            logger.warning(f"Failed to fetch details for {party.url}")
                            stats["failed"] += 1
                            continue

                        # Check if past event (use first event date)
                        if festival_data.event_dates:
                            start_date = festival_data.event_dates[0].start
                            if start_date and start_date < datetime.now(
                                start_date.tzinfo if start_date.tzinfo else None
                            ):
                                logger.info(f"Skipping past event: {festival_data.name}")
                                stats["past"] += 1
                                continue

                        # Get goabase modified timestamp from discovered_data
                        goabase_modified = (
                            festival_data.discovered_data.get("goabase_modified")
                            if festival_data.discovered_data
                            else None
                        )

                        # STAGE 1: Check by source_url in our DB
                        existing_festival = session.execute(
                            select(Festival).where(Festival.source_url == festival_data.source_url)
                        ).scalar_one_or_none()

                        # If we have a recent FAILED record, check PartyMap directly to see if it was created
                        if existing_festival and existing_festival.state == FestivalState.FAILED:
                            # Try to find it in PartyMap by URL
                            try:
                                potential_event = await partymap.get_event_by_url(
                                    festival_data.source_url
                                )
                                if potential_event:
                                    # It was created! Update our record
                                    logger.info(
                                        f"Found previously failed event was actually created: {festival_data.name}"
                                    )
                                    existing_festival.state = FestivalState.SYNCED
                                    existing_festival.partymap_event_id = potential_event.get("id")
                                    session.commit()
                                    stats["skipped"] += 1
                                    continue
                            except Exception as e:
                                logger.debug(f"Could not verify failed event: {e}")

                        existing_event = None
                        if existing_festival and existing_festival.partymap_event_id:
                            # We have a PartyMap ID stored - verify it still exists
                            try:
                                existing_event = await partymap.get_event(
                                    existing_festival.partymap_event_id
                                )
                            except Exception as e:
                                logger.warning(
                                    f"Stored PartyMap ID {existing_festival.partymap_event_id} not found: {e}"
                                )
                                existing_event = None

                        # STAGE 2: Check by clean_name in our DB (catches re-imports with different URLs)
                        if not existing_event and not existing_festival:
                            clean_name = festival_data.clean_name
                            if clean_name:
                                # Search for festivals with same clean_name
                                similar_festivals = (
                                    session.execute(
                                        select(Festival)
                                        .where(
                                            (Festival.clean_name == clean_name)
                                            | (Festival.name.ilike(f"%{clean_name}%"))
                                        )
                                        .where(Festival.partymap_event_id.is_not(None))
                                    )
                                    .scalars()
                                    .all()
                                )

                                if similar_festivals:
                                    # Found potential match - use the first one with PartyMap ID
                                    for similar in similar_festivals:
                                        if similar.partymap_event_id:
                                            try:
                                                existing_event = await partymap.get_event(
                                                    similar.partymap_event_id
                                                )
                                                if existing_event:
                                                    logger.info(
                                                        f"Found existing event by clean_name '{clean_name}': {existing_event.get('name')} (ID: {similar.partymap_event_id})"
                                                    )
                                                    existing_festival = similar
                                                    break
                                            except Exception as e:
                                                logger.warning(
                                                    f"Could not verify PartyMap event {similar.partymap_event_id}: {e}"
                                                )
                                                continue

                        # STAGE 3: Fallback - search PartyMap by URL
                        if not existing_event:
                            try:
                                existing_event = await partymap.get_event_by_url(
                                    festival_data.source_url
                                )
                            except Exception as e:
                                logger.error(f"Failed to check PartyMap for existing event: {e}")
                                stats["failed"] += 1
                                continue

                        if existing_event:
                            # Check if needs update
                            existing_modified = existing_event.get(
                                "updated_at"
                            ) or existing_event.get("goabase_modified")

                            should_update = False
                            if goabase_modified and existing_modified:
                                try:
                                    from dateutil import parser

                                    existing_dt = (
                                        parser.parse(existing_modified)
                                        if isinstance(existing_modified, str)
                                        else existing_modified
                                    )
                                    goabase_dt = (
                                        parser.parse(goabase_modified)
                                        if isinstance(goabase_modified, str)
                                        else goabase_modified
                                    )
                                    if goabase_dt > existing_dt:
                                        should_update = True
                                except Exception as e:
                                    logger.warning(f"Failed to parse dates for comparison: {e}")
                                    should_update = True  # Update if we can't compare
                            else:
                                should_update = True  # Update if no modification date

                            if should_update:
                                event_id = existing_event.get("id")
                                logger.info(
                                    f"Updating existing event: {existing_event.get('name')} (#{event_id})"
                                )

                                # Extract lineup if needed
                                festival_data = await _extract_lineup_if_needed(llm, festival_data)

                                # Update event
                                await partymap.update_event_by_id(event_id, festival_data)

                                # Store/update in our DB (update existing or create new record)
                                _store_festival(
                                    session,
                                    festival_data,
                                    goabase_modified,
                                    event_id,
                                    FestivalState.SYNCED,
                                )
                                stats["updated"] += 1
                            else:
                                logger.info(f"No updates needed for: {festival_data.name}")
                                stats["skipped"] += 1
                        else:
                            # Create new event - but first double-check we don't have it in our DB
                            # (this catches cases where PartyMap search failed but we have the record)
                            if existing_festival and existing_festival.partymap_event_id:
                                logger.info(
                                    f"Event already exists in our DB (ID: {existing_festival.partymap_event_id}), skipping: {festival_data.name}"
                                )
                                stats["skipped"] += 1
                                continue

                            logger.info(f"Creating new event: {festival_data.name}")

                            try:
                                # Extract lineup if needed
                                festival_data = await _extract_lineup_if_needed(llm, festival_data)

                                # Create via PartyMap
                                duplicate_check = DuplicateCheckResult(is_duplicate=False)
                                result = await partymap.sync_festival(
                                    festival_data, duplicate_check
                                )

                                # Store in our DB
                                event_id = result.get("event_id")
                                if event_id:
                                    _store_festival(
                                        session,
                                        festival_data,
                                        goabase_modified,
                                        event_id,
                                        FestivalState.SYNCED,
                                    )
                                    stats["created"] += 1
                                else:
                                    # PartyMap may have created event but returned error
                                    # Try multiple search methods to find it
                                    await asyncio.sleep(2)  # Give DB more time to commit

                                    found_event = None

                                    # Try 1: Search by source_url
                                    try:
                                        found_event = await partymap.get_event_by_url(
                                            festival_data.source_url
                                        )
                                    except Exception as e:
                                        logger.warning(f"URL search failed: {e}")

                                    # Try 2: Search by clean_name
                                    if not found_event and festival_data.clean_name:
                                        try:
                                            events = await partymap.search_events(
                                                festival_data.clean_name, limit=5
                                            )
                                            for event in events:
                                                # Check if it's a good match
                                                if (
                                                    festival_data.clean_name.lower()
                                                    in event.get("name", "").lower()
                                                ):
                                                    found_event = event
                                                    logger.info(
                                                        f"Found event by clean_name: {event.get('name')}"
                                                    )
                                                    break
                                        except Exception as e:
                                            logger.warning(f"Clean name search failed: {e}")

                                    # Try 3: Search by raw name
                                    if not found_event:
                                        try:
                                            events = await partymap.search_events(
                                                festival_data.name, limit=5
                                            )
                                            for event in events:
                                                if (
                                                    festival_data.name.lower()
                                                    in event.get("name", "").lower()
                                                ):
                                                    found_event = event
                                                    logger.info(
                                                        f"Found event by raw name: {event.get('name')}"
                                                    )
                                                    break
                                        except Exception as e:
                                            logger.warning(f"Raw name search failed: {e}")

                                    if found_event:
                                        event_id = found_event.get("id")
                                        _store_festival(
                                            session,
                                            festival_data,
                                            goabase_modified,
                                            event_id,
                                            FestivalState.SYNCED,
                                        )
                                        stats["created"] += 1
                                        logger.info(
                                            f"Event was created despite error: {festival_data.name} (ID: {event_id})"
                                        )
                                    else:
                                        # Store as failed but mark for retry
                                        # This prevents duplicate creation on next run
                                        _store_festival(
                                            session,
                                            festival_data,
                                            goabase_modified,
                                            None,  # No event ID yet
                                            FestivalState.FAILED,
                                        )
                                        logger.warning(
                                            f"Could not verify event creation for: {festival_data.name}. Stored as FAILED."
                                        )
                                        stats["failed"] += 1
                            except Exception as e:
                                logger.error(f"Failed to create event in PartyMap: {e}")
                                stats["failed"] += 1
                                continue

                        # Delay between requests
                        if i < len(parties):
                            time.sleep(REQUEST_DELAY)

                    except Exception as e:
                        logger.error(f"Error processing party {party.name}: {e}")
                        stats["failed"] += 1
                        continue

            finally:
                await goabase.close()
                await partymap.close()
                await llm.close()

        asyncio.run(_sync())

        logger.info(f"Goabase sync complete: {stats}")
        JobTracker.complete_job(JobType.GOABASE_SYNC, stats)
        return stats

    except Exception as e:
        logger.error(f"Goabase sync failed: {e}")
        JobTracker.fail_job(JobType.GOABASE_SYNC, str(e))
        raise self.retry(exc=e, countdown=300)
    finally:
        session.close()


async def _extract_lineup_if_needed(llm: LLMClient, festival_data: FestivalData) -> FestivalData:
    """
    Extract lineup via LLM if not explicitly provided by Goabase.

    Goabase sometimes puts lineup only in description or images.
    """
    # Check if we already have lineup from performers field
    has_lineup = False
    for event_date in festival_data.event_dates:
        if event_date.lineup and len(event_date.lineup) > 0:
            has_lineup = True
            break

    if has_lineup:
        return festival_data

    # No explicit lineup - need to extract from description
    logger.info(f"Extracting lineup via LLM for: {festival_data.name}")

    # Use full description for extraction
    description = festival_data.full_description or festival_data.description or ""

    if not description or len(description) < 10:
        logger.warning(f"No description available for lineup extraction: {festival_data.name}")
        return festival_data

    try:
        # Extract lineup using LLM
        lineup = await llm.extract_lineup(description)

        if lineup and len(lineup) > 0:
            logger.info(f"Extracted {len(lineup)} artists via LLM for: {festival_data.name}")

            # Add lineup to all event dates
            for event_date in festival_data.event_dates:
                event_date.lineup = lineup
        else:
            logger.info(f"No lineup found in description for: {festival_data.name}")

    except Exception as e:
        logger.error(f"Failed to extract lineup via LLM: {e}")

    return festival_data


def _store_festival(
    session,
    festival_data: FestivalData,
    goabase_modified: Optional[str],
    partymap_event_id: Optional[int],
    state: FestivalState,
):
    """Store/update festival record in our DB."""
    from src.utils.name_cleaner import clean_event_name, store_name_mapping_db

    # Ensure clean_name is set
    clean_name = festival_data.clean_name
    if not clean_name and festival_data.name:
        clean_name = clean_event_name(festival_data.name)

    # Store the name mapping in database for learning
    if festival_data.name and clean_name:
        store_name_mapping_db(
            session, raw_name=festival_data.name, clean_name=clean_name, source="goabase"
        )

    # Check if we already have this festival
    existing = session.execute(
        select(Festival).where(Festival.source_url == festival_data.source_url)
    ).scalar_one_or_none()

    if existing:
        # Update existing
        existing.state = state
        existing.partymap_event_id = partymap_event_id
        existing.research_data = festival_data.model_dump()
        existing.clean_name = clean_name
        existing.raw_name = festival_data.raw_name or festival_data.name
        if goabase_modified:
            existing.discovered_data = {
                **(existing.discovered_data or {}),
                "goabase_modified": goabase_modified,
            }
    else:
        # Create new
        festival = Festival(
            name=festival_data.name,
            clean_name=clean_name,
            raw_name=festival_data.raw_name or festival_data.name,
            source="goabase",
            source_id=None,  # Will be set if we fetch party list details
            source_url=festival_data.source_url,
            state=state,
            discovered_data={
                "goabase_modified": goabase_modified,
            }
            if goabase_modified
            else {},
            research_data=festival_data.model_dump(),
            partymap_event_id=partymap_event_id,
        )
        session.add(festival)

    session.commit()
