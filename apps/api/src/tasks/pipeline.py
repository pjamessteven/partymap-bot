"""Celery tasks for festival discovery pipeline."""

import logging
from datetime import datetime, timedelta
from src.utils.utc_now import utc_now
from uuid import UUID

from celery import Celery
from sqlalchemy import func, select

from src.config import get_settings
from src.core.database import SessionLocal, sync_engine
from src.core.models import (
    AgentDecision,
    Base,
    CostLog,
    DiscoveryQuery,
    Festival,
    FestivalEventDate,
    FestivalState,
    StateTransition,
)
from src.core.schemas import DiscoveredFestival, EventDateData, ResearchResult, ResearchFailure
from src.agents.discovery import DiscoveryAgent
from src.partymap.client import PartyMapClient
from src.dashboard.settings_router import is_setting_enabled_sync

logger = logging.getLogger(__name__)

# Create Celery app
settings = get_settings()
celery_app = Celery(
    "partymap_bot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_prefetch_multiplier=1,
)

# Task routes
celery_app.conf.task_routes = {
    "src.tasks.pipeline.discovery_pipeline": {"queue": "discovery"},
    "src.tasks.pipeline.research_pipeline": {"queue": "research"},
    "src.tasks.pipeline.sync_pipeline": {"queue": "sync"},
}


def _log_state_transition(
    session, festival_id: UUID, from_state: str, to_state: str, reason: str = ""
):
    """Log a state transition."""
    transition = StateTransition(
        festival_id=festival_id,
        from_state=from_state,
        to_state=to_state,
        reason=reason,
    )
    session.add(transition)


def _save_agent_decisions(session, festival_id: UUID, decisions: list, agent_type: str):
    """Save agent decisions to database."""
    for d in decisions:
        # Handle both dict and Pydantic model
        if hasattr(d, "dict"):
            # Pydantic model - convert to dict
            data = d.dict()
        elif hasattr(d, "model_dump"):
            # Pydantic v2 model
            data = d.model_dump()
        else:
            # Already a dict
            data = d

        decision = AgentDecision(
            festival_id=festival_id,
            agent_type=agent_type,
            step_number=data.get("step_number", 0),
            thought=data.get("thought", ""),
            action=data.get("action", ""),
            action_input=data.get("action_input", {}),
            observation=data.get("observation", ""),
            next_step=data.get("next_step", ""),
            confidence=data.get("confidence", 0.0),
            cost_cents=data.get("cost_cents", 0),
        )
        session.add(decision)


def _save_cost_log(
    session,
    festival_id: UUID,
    agent_type: str,
    service: str,
    cost_cents: int,
    description: str = "",
):
    """Save cost log entry."""
    cost_log = CostLog(
        festival_id=festival_id,
        agent_type=agent_type,
        service=service,
        cost_cents=cost_cents,
        description=description,
    )
    session.add(cost_log)


@celery_app.task(bind=True, max_retries=3)
def discovery_pipeline(self, manual_query: str = None):
    """
    Run discovery agent.

    Creates festivals in DISCOVERED state.
    Queues each for deduplication check.
    """
    import asyncio

    async def _discover_async():
        """Async part: call discovery agent."""
        agent = DiscoveryAgent(settings)
        try:
            return await agent.discover(manual_query=manual_query)
        finally:
            await agent.close()

    session = SessionLocal()
    try:
        # Run async discovery
        discovered = asyncio.run(_discover_async())

        # Save each discovered festival (sync)
        for d in discovered:
            # Check if already exists by source_url
            existing = session.execute(
                select(Festival).where(Festival.source_url == d.source_url)
            ).scalar_one_or_none()

            if existing:
                logger.info(f"Skipping duplicate source_url: {d.source_url}")
                continue

            festival = Festival(
                name=d.name or "Unknown",
                source=d.source,
                source_id=d.source_id,
                source_url=d.source_url,
                state=FestivalState.DISCOVERED,
                discovered_data=d.discovered_data,
                discovery_cost_cents=0,  # Will track per-query instead
            )
            session.add(festival)
            session.flush()

            # Log state transition
            _log_state_transition(
                session, festival.id, "", FestivalState.DISCOVERED, "Discovery complete"
            )

            session.commit()

            # Queue for deduplication
            deduplication_check.delay(str(festival.id))

        logger.info(f"Discovery complete: {len(discovered)} festivals found")

    except Exception as e:
        session.rollback()
        logger.error(f"Discovery failed: {e}")
        raise self.retry(exc=e, countdown=60)
    finally:
        session.close()


@celery_app.task(bind=True, max_retries=3)
def deduplication_check(self, festival_id: str):
    """
    Check for duplicates BEFORE research.

    If duplicate: Skip or mark for update
    If new: Queue for research (if auto_process enabled)

    In manual mode (auto_process=false), festivals stay in their current state
    and must be manually triggered via the API.
    """
    import asyncio

    session = SessionLocal()
    try:
        festival = session.get(Festival, UUID(festival_id))
        if not festival:
            logger.error(f"Festival not found: {festival_id}")
            return

        # Skip if already past deduplication
        if festival.state != FestivalState.DISCOVERED:
            return

        # Check if auto_process is enabled
        from src.dashboard.settings_router import is_auto_process_enabled_sync

        auto_process = is_auto_process_enabled_sync(session)

        async def _check_duplicate():
            client = PartyMapClient(settings)
            location = (
                festival.discovered_data.get("location", "") if festival.discovered_data else ""
            )
            result = await client.check_duplicate(
                name=festival.name, source_url=festival.source_url, location=location
            )
            await client.close()
            return result

        result = asyncio.run(_check_duplicate())

        if result.is_duplicate:
            festival.is_duplicate = True
            festival.existing_event_id = result.existing_event_id
            festival.is_new_event_date = result.is_new_event_date
            festival.date_confirmed = result.date_confirmed

            if result.is_new_event_date:
                # New date for existing - still need to research
                festival.state = FestivalState.RESEARCHING
                _log_state_transition(
                    session,
                    festival.id,
                    FestivalState.DISCOVERED,
                    FestivalState.RESEARCHING,
                    "New EventDate for existing series",
                )
                session.commit()

                # Only auto-queue if auto_process is enabled
                if auto_process:
                    research_pipeline.delay(festival_id)
                    logger.info(f"Auto-queued research for new event date: {festival.name}")
                else:
                    logger.info(f"Manual mode: {festival.name} ready for research (new event date)")

            elif not result.date_confirmed:
                # Needs update
                festival.state = FestivalState.RESEARCHING
                _log_state_transition(
                    session,
                    festival.id,
                    FestivalState.DISCOVERED,
                    FestivalState.RESEARCHING,
                    "Existing event needs update",
                )
                session.commit()

                # Only auto-queue if auto_process AND auto_research_on_discover are enabled
                if auto_process:
                    # Check if auto_research_on_discover is enabled
                    if is_setting_enabled_sync(session, "auto_research_on_discover"):
                        research_pipeline.delay(festival_id)
                        logger.info(f"Auto-queued research for update: {festival.name}")
                    else:
                        logger.info(f"Auto-research disabled, festival ready for manual research: {festival.name}")
                else:
                    logger.info(f"Manual mode: {festival.name} ready for research (needs update)")

            else:
                # Up to date, skip
                festival.state = FestivalState.SYNCED
                _log_state_transition(
                    session,
                    festival.id,
                    FestivalState.DISCOVERED,
                    FestivalState.SYNCED,
                    "Already up to date",
                )
                session.commit()

        else:
            # New festival - queue for research
            festival.state = FestivalState.RESEARCHING
            _log_state_transition(
                session,
                festival.id,
                FestivalState.DISCOVERED,
                FestivalState.RESEARCHING,
                "New festival, proceeding to research",
            )
            session.commit()

            # Only auto-queue if auto_process AND auto_research_on_discover are enabled
            if auto_process:
                # Check if auto_research_on_discover is enabled
                if is_setting_enabled_sync(session, "auto_research_on_discover"):
                    research_pipeline.delay(festival_id)
                    logger.info(f"Auto-queued research for new festival: {festival.name}")
                else:
                    logger.info(f"Auto-research disabled, festival ready for manual research: {festival.name}")
            else:
                logger.info(f"Manual mode: {festival.name} ready for research (new festival)")

    except Exception as e:
        session.rollback()
        logger.error(f"Deduplication failed for {festival_id}: {e}")
        raise self.retry(exc=e, countdown=60)
    finally:
        session.close()


@celery_app.task(bind=True, max_retries=3)
def research_pipeline(self, festival_id: str):
    """
    Run research agent.

    All-or-nothing: Must get all required fields or fail.
    """
    import asyncio

    session = SessionLocal()
    try:
        festival = session.get(Festival, UUID(festival_id))
        if not festival:
            logger.error(f"Festival not found: {festival_id}")
            return

        # Check if recently researched
        if festival.state == FestivalState.RESEARCHED:
            if festival.updated_at and festival.updated_at > utc_now() - timedelta(days=7):
                logger.info(f"Recently researched, skipping: {festival.name}")
                
                # Only auto-sync if auto_sync_on_research_success setting is enabled
                from src.dashboard.settings_router import is_setting_enabled_sync
                
                if is_setting_enabled_sync(session, "auto_sync_on_research_success"):
                    sync_pipeline.delay(festival_id)
                    logger.info(f"Auto-sync queued for recently researched festival: {festival.name}")
                else:
                    logger.info(f"Auto-sync disabled, recently researched festival ready for manual sync: {festival.name}")
                return

        # Check daily budget
        today_cost = (
            session.execute(
                select(func.sum(CostLog.cost_cents)).where(
                    CostLog.created_at >= utc_now().date()
                )
            ).scalar()
            or 0
        )

        if today_cost > settings.max_cost_per_day:
            logger.warning("Daily budget exceeded, retrying tomorrow")
            raise self.retry(countdown=86400)

        async def _research_async():
            """Run research using LangGraph agent."""
            from src.agents.research.graph import get_research_graph
            from src.agents.research.state import ResearchState
            from src.services.browser_service import BrowserService
            from src.services.llm_client import LLMClient
            from src.services.exa_client import ExaClient
            from src.services.musicbrainz_client import MusicBrainzClient
            from src.agents.research.cost_tracker import CostTracker
            
            # Get budget from settings
            from src.dashboard.settings_router import get_setting_value_sync
            budget_cents = get_setting_value_sync(session, "research_budget_cents", default=50)
            
            # Initialize services
            browser = BrowserService(settings)
            llm = LLMClient(settings)
            exa = ExaClient(settings)
            musicbrainz = MusicBrainzClient(settings)
            
            try:
                await browser.start()
                
                # Create graph
                graph = get_research_graph()
                
                # Create initial state
                thread_id = f"research_pipeline_{festival_id}"
                initial_state = ResearchState(
                    festival_name=festival.name,
                    source_url=festival.source_url,
                    discovered_data=festival.discovered_data,
                    budget_cents=budget_cents,
                )
                
                # Run graph
                config = {
                    "configurable": {"thread_id": thread_id},
                    "browser": browser,
                    "llm": llm,
                    "exa": exa,
                    "musicbrainz": musicbrainz,
                    "settings": settings,
                }
                
                result_state = await graph.ainvoke(initial_state, config=config)
                
                # Convert result state to ResearchResult
                final_result = result_state.get("final_result")
                cost_tracker_data = result_state.get("cost_tracker", {})
                total_cost = result_state.get("total_cost_cents", 0)
                budget_exceeded = result_state.get("budget_exceeded", False)
                error = result_state.get("error")
                
                if final_result:
                    # Successful research
                    from src.core.schemas import FestivalData
                    festival_data = FestivalData(**final_result)
                    
                    return ResearchResult(
                        success=True,
                        festival_data=festival_data,
                        collected_data=result_state.get("collected_data", {}),
                        cost_cents=total_cost,
                        iterations=result_state.get("iteration", 0),
                        budget_exceeded=budget_exceeded,
                    )
                elif budget_exceeded:
                    # Budget exceeded - return partial data
                    return ResearchResult(
                        success=False,
                        failure=ResearchFailure(
                            reason="budget_exceeded",
                            message=f"Research stopped: Budget exceeded ({total_cost}c / {budget_cents}c)",
                            completeness_score=0.5,  # Estimate
                            missing_fields=result_state.get("missing_fields", ["unknown"]),
                        ),
                        collected_data=result_state.get("collected_data", {}),
                        cost_cents=total_cost,
                        iterations=result_state.get("iteration", 0),
                        budget_exceeded=True,
                    )
                else:
                    # Other failure
                    return ResearchResult(
                        success=False,
                        failure=ResearchFailure(
                            reason="research_failed",
                            message=error or "Research did not complete successfully",
                            completeness_score=0.0,
                            missing_fields=result_state.get("missing_fields", ["unknown"]),
                        ),
                        collected_data=result_state.get("collected_data", {}),
                        cost_cents=total_cost,
                        iterations=result_state.get("iteration", 0),
                    )
                    
            finally:
                await browser.close()
                await llm.close()
                await exa.close()
                await musicbrainz.close()

        result = asyncio.run(_research_async())
        
        # Handle research result
        if result.success and result.festival_data:
            # Successful research with complete data
            festival_data = result.festival_data
            
            # Save structured research result
            festival.research_data = result.model_dump()
            festival.research_cost_cents = result.cost_cents
            festival.state = FestivalState.RESEARCHED
            festival.failure_reason = None
            festival.failure_message = None
            festival.research_completeness_score = 1.0

            _log_state_transition(
                session,
                festival.id,
                FestivalState.RESEARCHING,
                FestivalState.RESEARCHED,
                "Research complete - all required fields found",
            )

            # Save agent decisions (if available from LangGraph)
            if hasattr(result, 'decisions') and result.decisions:
                _save_agent_decisions(session, festival.id, result.decisions, "research")

            # Save cost log
            _save_cost_log(
                session,
                festival.id,
                "research",
                "openrouter",
                result.cost_cents,
                f"Research for {festival.name}",
            )

            # Create FestivalEventDate records
            for event_date_data in festival_data.event_dates:
                event_date = FestivalEventDate(
                    festival_id=festival.id,
                    start_date=event_date_data.start,
                    end_date=event_date_data.end,
                    location_description=event_date_data.location_description,
                    location_country=event_date_data.location_country,
                    location_lat=event_date_data.location_lat,
                    location_lng=event_date_data.location_lng,
                    lineup=event_date_data.lineup,
                    ticket_url=str(event_date_data.ticket_url) if event_date_data.ticket_url else None,
                    tickets=[t.model_dump() for t in event_date_data.tickets]
                    if event_date_data.tickets
                    else [],
                    expected_size=event_date_data.expected_size,
                    source_url=event_date_data.source_url,
                )
                session.add(event_date)

            session.commit()

            # Queue for sync only if auto_sync_on_research_success is enabled
            from src.dashboard.settings_router import is_setting_enabled_sync
            
            if is_setting_enabled_sync(session, "auto_sync_on_research_success"):
                sync_pipeline.delay(festival_id)
                logger.info(f"Auto-sync queued for researched festival: {festival.name}")
            else:
                logger.info(f"Auto-sync disabled, festival ready for manual sync: {festival.name}")
            
        elif result.failure:
            # Research failed with structured failure
            failure = result.failure
            
            # Save structured failure result
            festival.research_data = result.model_dump()
            festival.research_cost_cents = result.cost_cents
            festival.failure_reason = failure.reason
            festival.failure_message = failure.message
            festival.research_completeness_score = failure.completeness_score
            
            # Determine state based on completeness
            if failure.completeness_score > 0:
                festival.state = FestivalState.RESEARCHED_PARTIAL
                state_msg = f"Research partial ({failure.completeness_score*100:.0f}% complete): {failure.message}"
            else:
                festival.state = FestivalState.FAILED
                state_msg = f"Research failed: {failure.message}"
                festival.retry_count += 1
                
                # Check max retries
                if festival.retry_count >= settings.max_retries:
                    festival.purge_after = utc_now() + timedelta(
                        days=settings.failed_festival_retention_days
                    )

            _log_state_transition(
                session,
                festival.id,
                FestivalState.RESEARCHING,
                festival.state,
                state_msg,
            )

            # Save agent decisions (if available from LangGraph)
            if hasattr(result, 'decisions') and result.decisions:
                _save_agent_decisions(session, festival.id, result.decisions, "research")

            # Save cost log
            _save_cost_log(
                session,
                festival.id,
                "research",
                "openrouter",
                result.cost_cents,
                f"Research failed: {failure.reason} - {failure.message}",
            )

            session.commit()
            
        else:
            # Unexpected result format
            logger.error(f"Unexpected research result format for {festival_id}")
            festival.state = FestivalState.FAILED
            festival.last_error = "Unexpected research result format"
            festival.failure_reason = "unknown"
            festival.failure_message = "Unexpected research result format"
            session.commit()

    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error researching {festival_id}: {e}")
        
        # Update festival with failure information
        festival.state = FestivalState.FAILED
        festival.last_error = str(e)
        festival.failure_reason = "unknown"
        festival.failure_message = f"Unexpected error: {str(e)}"
        festival.research_completeness_score = 0.0
        festival.retry_count += 1
        
        # Check max retries
        if festival.retry_count >= settings.max_retries:
            festival.purge_after = utc_now() + timedelta(
                days=settings.failed_festival_retention_days
            )
        
        session.commit()
        raise self.retry(exc=e, countdown=60)

    finally:
        session.close()


@celery_app.task(bind=True, max_retries=3)
def sync_pipeline(self, festival_id: str):
    """
    Sync festival to PartyMap with pre-flight validation.

    Uses Event/EventDate separation strategy:
    - Event object: General info only
    - EventDate objects: Date-specific info

    Validation:
    - Validates festival data before PartyMap sync
    - Sets state to VALIDATING -> VALIDATION_FAILED or SYNCING -> SYNCED
    - On sync error: classifies error, increments retry, quarantines if max retries reached
    """
    import asyncio

    session = SessionLocal()
    try:
        festival = session.get(Festival, UUID(festival_id))
        if not festival:
            logger.error(f"Festival not found: {festival_id}")
            return

        if not festival.research_data:
            logger.error(f"No research data for {festival_id}")
            return

        # --- Pre-flight Validation ---
        from src.core.schemas import FestivalData, DuplicateCheckResult
        from src.core.validators import PartyMapSyncValidator
        from src.core.error_classification import ErrorContext, ErrorCategory, categorize_error
        from src.services.dead_letter_queue import check_and_quarantine

        festival_data = FestivalData(**festival.research_data)
        validator = PartyMapSyncValidator()
        validation_result = validator.validate(festival_data)

        # Store validation results
        festival.validation_status = validation_result.status
        festival.validation_errors = validation_result.errors
        festival.validation_warnings = validation_result.warnings
        festival.validation_checked_at = utc_now()

        if validation_result.status == "invalid":
            festival.state = FestivalState.VALIDATION_FAILED
            _log_state_transition(
                session,
                festival.id,
                FestivalState.RESEARCHED,
                FestivalState.VALIDATION_FAILED,
                f"Validation failed: {len(validation_result.errors)} errors",
            )
            session.commit()
            logger.warning(
                f"Festival {festival.name} failed validation: "
                f"{len(validation_result.errors)} errors, "
                f"{len(validation_result.warnings)} warnings"
            )
            return

        if validation_result.status == "needs_review":
            festival.state = FestivalState.NEEDS_REVIEW
            _log_state_transition(
                session,
                festival.id,
                FestivalState.RESEARCHED,
                FestivalState.NEEDS_REVIEW,
                f"Validation needs review: {len(validation_result.warnings)} warnings",
            )
            session.commit()
            logger.warning(
                f"Festival {festival.name} needs review: "
                f"{len(validation_result.warnings)} warnings"
            )
            # In auto-process mode, continue to sync anyway
            # In manual mode, stop here and wait for human review
            if not is_setting_enabled_sync(session, "auto_process"):
                return
            # Auto-process: continue to sync with warning logged
            logger.info(f"Auto-process enabled, continuing sync for {festival.name}")

        # Mark as syncing
        old_state = festival.state
        festival.state = FestivalState.SYNCING
        _log_state_transition(
            session,
            festival.id,
            old_state,
            FestivalState.SYNCING,
            "Starting PartyMap sync",
        )
        session.commit()

        async def _sync_async():
            client = PartyMapClient(settings)

            duplicate_check = DuplicateCheckResult(
                is_duplicate=festival.is_duplicate,
                existing_event_id=festival.existing_event_id,
                is_new_event_date=festival.is_new_event_date,
                date_confirmed=festival.date_confirmed,
            )

            # Sync with circuit breaker protection
            result = await client.sync_festival(festival_data, duplicate_check)
            await client.close()
            return result

        result = asyncio.run(_sync_async())

        # Update festival on success
        festival.partymap_event_id = result.get("event_id")
        festival.state = FestivalState.SYNCED
        festival.sync_data = result
        festival.last_error = None
        festival.error_category = None
        festival.error_context = None
        festival.retry_count = 0

        _log_state_transition(
            session,
            festival.id,
            FestivalState.SYNCING,
            FestivalState.SYNCED,
            f"Sync complete: {result.get('action')}",
        )

        session.commit()
        logger.info(f"Synced {festival.name}: {result}")

    except Exception as e:
        session.rollback()

        # Guard against errors before festival was loaded
        if "festival" not in locals() or festival is None:
            logger.error(f"Sync failed before festival could be loaded: {e}")
            session.commit()
            raise

        # --- Enhanced Error Handling ---
        error_category = categorize_error(e, service="partymap")
        error_context = ErrorContext.from_exception(
            e, category=error_category, service="partymap", operation="sync"
        )

        festival.last_error = f"[{error_category.value}] {str(e)}"
        festival.error_category = error_category.value
        festival.error_context = error_context.to_dict()
        festival.retry_count = (festival.retry_count or 0) + 1

        if not festival.first_error_at:
            festival.first_error_at = utc_now()
        festival.last_retry_at = utc_now()

        # Check if we should quarantine
        from src.core.models import FestivalState
        if festival.retry_count >= 5:
            festival.max_retries_reached = True
            festival.state = FestivalState.QUARANTINED
            festival.quarantined_at = utc_now()
            festival.quarantine_reason = f"Max retries reached after {festival.retry_count} attempts: {str(e)}"
            _log_state_transition(
                session,
                festival.id,
                FestivalState.SYNCING,
                FestivalState.QUARANTINED,
                f"Quarantined: {error_category.value} - {str(e)}",
            )
            logger.error(
                f"Festival {festival.name} quarantined after {festival.retry_count} sync failures"
            )
        else:
            # Retryable error: schedule retry with exponential backoff
            if error_category in (ErrorCategory.TRANSIENT, ErrorCategory.EXTERNAL, ErrorCategory.UNKNOWN):
                countdown = min(60 * (2 ** festival.retry_count), 3600)  # 2min, 4min, 8min... cap at 1hr
                logger.warning(
                    f"Sync failed for {festival.name} ({error_category.value}), "
                    f"retrying in {countdown}s (attempt {festival.retry_count}/5)"
                )
                session.commit()
                raise self.retry(exc=e, countdown=countdown)
            else:
                # Non-retryable error: mark as failed
                festival.state = FestivalState.FAILED
                _log_state_transition(
                    session,
                    festival.id,
                    FestivalState.SYNCING,
                    FestivalState.FAILED,
                    f"Sync failed: {error_category.value} - {str(e)}",
                )
                logger.error(
                    f"Sync failed for {festival.name} ({error_category.value}): {e}"
                )

        session.commit()
    finally:
        session.close()