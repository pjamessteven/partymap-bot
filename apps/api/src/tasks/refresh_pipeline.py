"""Celery tasks for refresh pipeline.

This pipeline:
1. Finds unconfirmed EventDates in PartyMap (within 120 days)
2. Refreshes each with research agent
3. Queues changes for human approval
4. Cancels events still unconfirmed 30 days out
"""

import logging
from datetime import datetime

from celery import shared_task

from src.config import get_settings
from src.core.database import AsyncSessionLocal
from src.core.job_activity import JobActivityLogger
from src.core.job_tracker import JobTracker, JobType
from src.core.models import RefreshApproval
from src.utils.utc_now import utc_now

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def refresh_unconfirmed_dates_task(self, days_ahead: int = 120):
    """
    Main task to find and refresh unconfirmed EventDates.

    Runs weekly. Finds EventDates with:
    - date_unconfirmed=true
    - start date within 120 days
    - Not already being processed

    For each, spawns a child task to refresh.
    """
    import asyncio

    async def run():
        settings = get_settings()
        from src.partymap.client import PartyMapClient

        async with PartyMapClient(settings) as client:
            # Get unconfirmed dates from PartyMap
            unconfirmed = await client.get_unconfirmed_event_dates(
                days_ahead=120,
                limit=100,
            )

            if not unconfirmed:
                logger.info("No unconfirmed EventDates found within 120 days")
                return {"processed": 0, "queued": 0}

            # Check which are 30 days out (need cancellation)
            to_cancel = []
            to_refresh = []

            for event_date in unconfirmed:
                start = event_date.get("start")
                if not start:
                    continue

                try:
                    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    days_until = (start_dt - utc_now()).days

                    if days_until <= 30:
                        # Too close, should be cancelled
                        to_cancel.append(event_date)
                    else:
                        to_refresh.append(event_date)
                except (ValueError, TypeError):
                    continue

            # Cancel events 30 days out
            for event_date in to_cancel:
                await client.mark_event_date_cancelled(
                    event_date["id"],
                    reason="Date not confirmed within 30 days of event",
                )
                await JobActivityLogger.log_activity(
                    job_type="refresh",
                    activity_type="cancelled",
                    message=f"Cancelled unconfirmed EventDate {event_date.get('id')}",
                    details={"event_date_id": event_date.get("id")},
                )

            # Queue refresh tasks
            queued = 0
            for event_date in to_refresh:
                # Get parent event info
                event_id = event_date.get("event_id")
                if not event_id:
                    continue

                event = await client.get_event(event_id)
                if not event:
                    continue

                # Spawn refresh task
                refresh_festival_date_task.delay(
                    event_id=event_id,
                    event_date_id=event_date["id"],
                    event_name=event.get("name", "Unknown"),
                )
                queued += 1

            return {
                "processed": len(unconfirmed),
                "cancelled": len(to_cancel),
                "queued_for_refresh": queued,
            }

    return asyncio.run(run())


@shared_task(bind=True, max_retries=2)
def refresh_festival_date_task(
    self,
    event_id: int,
    event_date_id: int,
    event_name: str,
):
    """
    Refresh a single EventDate.

    Runs the refresh agent to:
    1. Verify/correct dates
    2. Find missing lineup
    3. Update descriptions
    4. Find ticket info

    Creates a RefreshApproval record for human review.
    """
    import asyncio

    async def run():
        settings = get_settings()
        from src.agents.refresh.graph import get_refresh_graph
        from src.agents.streaming import get_broadcaster
        from src.partymap.client import PartyMapClient
        from src.services.browser_service import BrowserService
        from src.services.exa_client import ExaClient
        from src.services.llm_client import LLMClient

        # Track job
        await JobTracker.start_job(
            JobType.REFRESH,
            self.request.id,
            metadata={"event_id": event_id, "event_date_id": event_date_id},
        )

        browser = BrowserService(settings)
        llm = LLMClient(settings)
        exa = ExaClient(settings)
        broadcaster = await get_broadcaster()

        try:
            await browser.start()

            async with PartyMapClient(settings) as client:
                # Get current data
                event = await client.get_event(event_id)
                if not event:
                    raise ValueError(f"Event {event_id} not found")

                event_date = None
                for ed in event.get("event_dates", []):
                    if ed.get("id") == event_date_id:
                        event_date = ed
                        break

                if not event_date:
                    raise ValueError(f"EventDate {event_date_id} not found")

                # Run refresh agent
                from src.agents.refresh.state import RefreshState

                graph = get_refresh_graph()
                initial_state = RefreshState(
                    event_id=event_id,
                    event_date_id=event_date_id,
                    event_name=event_name,
                    current_event_data=event,
                    current_event_date=event_date,
                )

                config = {
                    "configurable": {"thread_id": f"refresh_{event_date_id}"},
                    "browser": browser,
                    "llm": llm,
                    "exa": exa,
                    "settings": settings,
                    "writer": lambda data: asyncio.create_task(
                        broadcaster.broadcast(f"refresh_{event_date_id}", data)
                    ),
                }

                final_state = None
                async for event_data in graph.astream(
                    initial_state,
                    config=config,
                    stream_mode=["updates", "values"],
                ):
                    final_state = event_data

                # Create approval record
                async with AsyncSessionLocal() as db:
                    approval = RefreshApproval(
                        event_id=event_id,
                        event_date_id=event_date_id,
                        event_name=event_name,
                        current_data={
                            "event": event,
                            "event_date": event_date,
                        },
                        proposed_changes={
                            "event": final_state.get("proposed_event_changes", {}),
                            "event_date": final_state.get("proposed_date_changes", {}),
                        },
                        change_summary=final_state.get("change_summary", []),
                        research_confidence=max(
                            final_state.get("date_confidence", 0),
                            final_state.get("lineup_confidence", 0),
                        ),
                        research_sources=[final_state.get("official_url", "")],
                        status="auto_approved" if final_state.get("should_auto_approve") else "pending",
                    )
                    db.add(approval)
                    await db.commit()

                    # Log activity
                    await JobActivityLogger.log_activity(
                        job_type="refresh",
                        activity_type="completed",
                        message=f"Refresh completed for {event_name}",
                        details={
                            "approval_id": str(approval.id),
                            "changes": final_state.get("change_summary", []),
                            "auto_approved": final_state.get("should_auto_approve"),
                        },
                    )

                await JobTracker.complete_job(JobType.REFRESH, {
                    "approval_id": str(approval.id),
                    "auto_approved": final_state.get("should_auto_approve"),
                })

                return {
                    "event_id": event_id,
                    "event_date_id": event_date_id,
                    "approval_id": str(approval.id),
                    "changes": final_state.get("change_summary", []),
                }

        except Exception as e:
            logger.error(f"Refresh failed for {event_name}: {e}")
            await JobTracker.fail_job(JobType.REFRESH, str(e))
            raise self.retry(exc=e, countdown=60)

        finally:
            await browser.close()
            await llm.close()
            await exa.close()

    return asyncio.run(run())


@shared_task
def apply_approved_refresh_task(approval_id: str):
    """
    Apply an approved refresh to PartyMap.

    Called when human approves changes.
    """
    import asyncio

    async def run():
        settings = get_settings()
        from src.partymap.client import PartyMapClient

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(RefreshApproval).where(RefreshApproval.id == approval_id)
            )
            approval = result.scalar_one_or_none()

            if not approval:
                raise ValueError(f"Approval {approval_id} not found")

            if approval.status != "approved":
                raise ValueError(f"Approval {approval_id} is not approved")

            async with PartyMapClient(settings) as client:
                # Apply event changes
                if approval.proposed_changes.get("event"):
                    event_changes = approval.proposed_changes["event"]
                    # Convert dict to FestivalData if needed
                    if isinstance(event_changes, dict):
                        from src.core.schemas import FestivalData
                        try:
                            festival_data = FestivalData(**event_changes)
                        except Exception:
                            # Partial data - build FestivalData with minimal required fields
                            extra_fields = {}
                            for k, v in event_changes.items():
                                if k not in ("name", "description", "full_description", "event_dates"):
                                    extra_fields[k] = v
                            festival_data = FestivalData(
                                name=event_changes.get("name", approval.event_name or "Unknown"),
                                description=event_changes.get("description", ""),
                                full_description=event_changes.get("full_description", ""),
                                event_dates=[],
                                **extra_fields
                            )
                    else:
                        festival_data = event_changes
                    await client.update_event_by_id(
                        approval.event_id,
                        festival_data,
                        message="Updated via refresh pipeline",
                    )

                # Apply event_date changes
                if approval.proposed_changes.get("event_date"):
                    await client.update_event_date(
                        approval.event_date_id,
                        approval.proposed_changes["event_date"],
                        message="Date confirmed via refresh pipeline",
                    )

                # Mark as applied
                approval.status = "applied"
                await db.commit()

                await JobActivityLogger.log_activity(
                    job_type="refresh",
                    activity_type="applied",
                    message=f"Applied approved changes for {approval.event_name}",
                    details={"approval_id": approval_id},
                )

            return {"success": True, "event_name": approval.event_name}

    return asyncio.run(run())
