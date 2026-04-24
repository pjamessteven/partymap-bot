"""Goabase sync module - DB-only sync with tag enhancement and researched state.

This module handles syncing festivals from Goabase API to PartyMap database using
tag enhancement and setting events directly to RESEARCHED state.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import select

from src.config import Settings, get_settings
from src.core.database import AsyncSessionLocal
from src.core.models import Festival, FestivalState
from src.core.schemas import EventDateData, FestivalData
from src.services.goabase_client import GoabaseClient
from src.services.llm_client import LLMClient
from src.partymap.client import PartyMapClient
from src.utils.utc_now import utc_now

logger = logging.getLogger(__name__)


@dataclass
class SyncStatus:
    """Status of Goabase sync operation."""

    is_running: bool = False
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_found: int = 0
    new_count: int = 0
    update_count: int = 0
    unchanged_count: int = 0
    error_count: int = 0
    current_operation: Optional[str] = None
    stop_requested: bool = False


class GoabaseSyncManager:
    """Manager for Goabase sync operations with status tracking."""

    _instance = None
    _status: SyncStatus = SyncStatus()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def status(self) -> SyncStatus:
        return self._status

    def request_stop(self):
        """Request the sync to stop gracefully."""
        self._status.stop_requested = True
        logger.info("Stop requested for Goabase sync")

    def reset_status(self):
        """Reset status for new sync operation."""
        self._status = SyncStatus(is_running=True, started_at=utc_now())

    def mark_complete(self):
        """Mark sync as complete."""
        self._status.is_running = False
        self._status.completed_at = utc_now()
        self._status.stop_requested = False

    def update_progress(self, current: int, total: int, operation: str):
        """Update sync progress."""
        self._status.current_operation = f"{operation} ({current}/{total})"


class GoabaseSync:
    """
    Sync festivals from Goabase to PartyMap database.

    Features:
    - Fetches party list and detailed party info
    - Enhances tags using LLM with PartyMap tag selection
    - Extracts lineup from description when performers field is empty
    - Sets events directly to RESEARCHED state (bypasses research workflow)
    - Simple URL-based deduplication with modified_date tracking
    - Real-time streaming to UI
    """

    def __init__(
        self,
        settings: Settings,
        manager: Optional[GoabaseSyncManager] = None,
        llm_client: Optional[LLMClient] = None,
        partymap_client: Optional[PartyMapClient] = None,
        writer: Optional[Callable[[dict], None]] = None,
    ):
        self.settings = settings
        self.goabase: Optional[GoabaseClient] = None
        self.manager = manager or GoabaseSyncManager()
        self.llm = llm_client
        self.partymap = partymap_client
        self.writer = writer
        self._available_tags: Optional[List[str]] = None

    def _broadcast(self, event_type: str, data: dict):
        """Broadcast event to writer if available."""
        if self.writer:
            event = {
                "event": event_type,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }
            # Handle both sync and async writers
            try:
                import asyncio
                result = self.writer(event)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as e:
                logger.warning(f"Failed to broadcast goabase event: {e}")

    async def __aenter__(self):
        """Async context manager entry."""
        self.goabase = GoabaseClient(self.settings)
        if not self.llm:
            self.llm = LLMClient(self.settings)
        if not self.partymap:
            self.partymap = PartyMapClient(self.settings)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.goabase:
            await self.goabase.close()
        if self.llm:
            await self.llm.close()
        if self.partymap:
            await self.partymap.close()

    async def _get_available_tags(self) -> List[str]:
        """Get available PartyMap tags (cached)."""
        if self._available_tags is None:
            try:
                tags_response = await self.partymap.get_tags(per_page=150)
                if tags_response and "items" in tags_response:
                    self._available_tags = [item.get("tag", "").lower() for item in tags_response["items"]]
                else:
                    self._available_tags = []
            except Exception as e:
                logger.warning(f"Failed to fetch PartyMap tags: {e}")
                self._available_tags = []
        return self._available_tags

    async def sync_all(self) -> Dict[str, Any]:
        """
        Sync all festivals from Goabase.

        :return: Dict with sync results
        """
        self.manager.reset_status()
        status = self.manager.status

        logger.info("Starting Goabase sync...")

        # Initialize client if not using context manager
        if not self.goabase:
            self.goabase = GoabaseClient(self.settings)
        if not self.llm:
            self.llm = LLMClient(self.settings)
        if not self.partymap:
            self.partymap = PartyMapClient(self.settings)

        try:
            # Step 1: Fetch party list from Goabase
            status.current_operation = "Fetching party list from Goabase API"
            self._broadcast("info", {"message": "Fetching party list from Goabase API..."})
            
            party_list = await self.goabase.get_party_list()
            status.total_found = len(party_list)
            logger.info(f"Fetched {len(party_list)} parties from Goabase")
            
            self._broadcast("info", {"message": f"Found {len(party_list)} parties from Goabase"})

            if status.stop_requested:
                logger.info("Goabase sync stopped after fetch")
                self.manager.mark_complete()
                return self._get_result_dict()

            # Step 2: Process each party
            for idx, party in enumerate(party_list):
                if status.stop_requested:
                    logger.info(f"Goabase sync stopped at {idx}/{len(party_list)}")
                    break

                self.manager.update_progress(idx + 1, len(party_list), f"Processing {party.name}")
                
                # Broadcast progress every 5 items or on first/last
                if idx % 5 == 0 or idx == len(party_list) - 1:
                    self._broadcast("progress", {
                        "current": idx + 1,
                        "total": len(party_list),
                        "percent": int(((idx + 1) / len(party_list)) * 100),
                        "current_party": party.name,
                    })

                try:
                    await self._process_party(party)
                except Exception as e:
                    logger.error(f"Failed to process Goabase party {party.name}: {e}")
                    status.error_count += 1
                    self._broadcast("error", {"message": f"Failed to process {party.name}: {str(e)}"})

            logger.info(
                f"Goabase sync complete: {status.new_count} new, "
                f"{status.update_count} updates, {status.unchanged_count} unchanged, "
                f"{status.error_count} errors"
            )
            
            self._broadcast("complete", {
                "total_found": status.total_found,
                "new_count": status.new_count,
                "update_count": status.update_count,
                "unchanged_count": status.unchanged_count,
                "error_count": status.error_count,
            })

        except Exception as e:
            logger.error(f"Goabase sync failed: {e}")
            status.error_count += 1
            self._broadcast("error", {"message": f"Sync failed: {str(e)}"})
        finally:
            self.manager.mark_complete()

        return self._get_result_dict()

    async def _process_party(self, party) -> None:
        """Process a single Goabase party."""
        status = self.manager.status

        # Fetch detailed party info
        festival_data = await self.goabase.get_party_details(party.url)
        if not festival_data:
            logger.warning(f"Failed to fetch details for party: {party.name}")
            status.error_count += 1
            return

        # Check if festival exists in our DB
        async with AsyncSessionLocal() as session:
            existing = await self._get_festival_by_url(session, festival_data.source_url)

            if not existing:
                # NEW festival - enhance and create
                await self._create_new_festival(session, festival_data)
                status.new_count += 1
                logger.info(f"New Goabase festival: {festival_data.name}")
                self._broadcast("festival_found", {
                    "name": festival_data.name,
                    "source_url": str(festival_data.source_url) if festival_data.source_url else None,
                    "status": "new",
                })

            elif self._needs_update(existing, festival_data):
                # UPDATE needed
                await self._mark_for_update(session, existing, festival_data)
                status.update_count += 1
                logger.info(f"Goabase update needed: {festival_data.name}")
                self._broadcast("festival_found", {
                    "name": festival_data.name,
                    "source_url": str(festival_data.source_url) if festival_data.source_url else None,
                    "status": "update",
                })

            else:
                # Unchanged
                status.unchanged_count += 1

    async def _get_festival_by_url(self, session, url: str) -> Optional[Festival]:
        """Get festival by source_url."""
        result = await session.execute(select(Festival).where(Festival.source_url == url))
        return result.scalar_one_or_none()

    def _needs_update(self, existing: Festival, new_data: FestivalData) -> bool:
        """Check if festival needs update based on modified_date."""
        if not new_data.discovered_data:
            return False

        new_modified = new_data.discovered_data.get("goabase_modified")
        if not new_modified:
            return False

        # Get stored modified_date from discovered_data
        stored_date = (
            existing.discovered_data.get("goabase_modified")
            if existing.discovered_data
            else None
        )

        if not stored_date:
            # No stored date, assume update needed
            return True

        # Compare dates
        return new_modified > stored_date

    async def _enhance_festival_data(self, festival_data: FestivalData) -> FestivalData:
        """Enhance festival data with LLM tag selection and lineup extraction."""
        try:
            # Get available PartyMap tags
            available_tags = await self._get_available_tags()

            # Enhance tags using LLM (always include 'goabase' and 'psytrance')
            base_tags = ["goabase", "psytrance"]

            if available_tags:
                # Use LLM to select relevant tags from PartyMap's available tags
                selected_tags = await self.llm.select_relevant_tags(
                    festival_name=festival_data.name,
                    description=festival_data.description or "",
                    available_tags=available_tags,
                    max_tags=3,  # Leave room for goabase + psytrance
                )
                base_tags.extend(selected_tags)

            # Add any hashtags from the original data that aren't duplicates
            existing_lower = [t.lower() for t in base_tags]
            for tag in festival_data.tags:
                if tag.lower() not in existing_lower and len(base_tags) < 5:
                    base_tags.append(tag)

            # Ensure max 5 tags
            festival_data.tags = base_tags[:5]

            # Extract lineup from description if no lineup exists
            if festival_data.event_dates:
                event_date = festival_data.event_dates[0]
                if not event_date.lineup:
                    # Try to extract lineup from full_description or description
                    text_to_analyze = festival_data.full_description or festival_data.description or ""
                    if text_to_analyze:
                        extracted_lineup = await self.llm.extract_lineup(text_to_analyze)
                        if extracted_lineup:
                            event_date.lineup = extracted_lineup
                            logger.info(
                                f"Extracted {len(extracted_lineup)} artists from description for {festival_data.name}"
                            )

        except Exception as e:
            logger.warning(f"Failed to enhance festival data for {festival_data.name}: {e}")
            # Ensure at least 'goabase' and 'psytrance' tags are present
            if "goabase" not in festival_data.tags:
                festival_data.tags = ["goabase", "psytrance"] + festival_data.tags[:3]

        return festival_data

    async def _create_new_festival(self, session, festival_data: FestivalData) -> None:
        """Create new festival from Goabase with enhancement."""
        # Enhance the festival data with tags and lineup
        festival_data = await self._enhance_festival_data(festival_data)

        # Store discovered_data with goabase_modified
        discovered_data = dict(festival_data.discovered_data or {})
        if festival_data.source_modified:
            discovered_data["goabase_modified"] = festival_data.source_modified.isoformat()

        # Create EventDateData for database storage
        event_dates_data = []
        for ed in festival_data.event_dates:
            event_dates_data.append({
                "start_date": ed.start.isoformat() if ed.start else None,
                "end_date": ed.end.isoformat() if ed.end else None,
                "location": ed.location_description,
                "lineup": ed.lineup,
            })

        discovered_data["event_dates"] = event_dates_data
        discovered_data["tags"] = festival_data.tags
        discovered_data["logo_url"] = str(festival_data.logo_url) if festival_data.logo_url else None
        discovered_data["website_url"] = str(festival_data.website_url) if festival_data.website_url else None

        festival = Festival(
            name=festival_data.name,
            clean_name=festival_data.clean_name or self._clean_name(festival_data.name),
            source="goabase",
            source_id=festival_data.discovered_data.get("party_id") if festival_data.discovered_data else None,
            source_url=str(festival_data.source_url) if festival_data.source_url else None,
            state=FestivalState.RESEARCHED,  # Go directly to RESEARCHED state
            workflow_type="new",
            discovered_data=discovered_data,
            research_completeness_score=0.8,  # Good completeness since we enhanced it
        )

        session.add(festival)
        await session.commit()

    async def _mark_for_update(
        self, session, existing: Festival, festival_data: FestivalData
    ) -> None:
        """Mark existing festival for update."""
        # Update discovered_data with new data
        discovered_data = dict(festival_data.discovered_data or {})
        if festival_data.source_modified:
            discovered_data["goabase_modified"] = festival_data.source_modified.isoformat()

        existing.discovered_data = discovered_data
        existing.state = FestivalState.NEEDS_RESEARCH_UPDATE
        existing.workflow_type = "update"
        existing.update_required = True
        existing.update_reasons = ["goabase_modified"]

        await session.commit()

    def _clean_name(self, name: str) -> str:
        """Clean festival name by removing year/edition numbers."""
        import re

        # Remove year patterns
        cleaned = re.sub(r"\s+20\d{2}\s*", " ", name)
        # Remove edition numbers
        cleaned = re.sub(
            r"\s+(?:edition|vii|viii|ix|x|\d+th)\s*$", "", cleaned, flags=re.I
        )

        return cleaned.strip()

    def _get_result_dict(self) -> Dict[str, Any]:
        """Get sync results as dict."""
        status = self.manager.status
        return {
            "is_running": status.is_running,
            "started_at": status.started_at.isoformat() if status.started_at else None,
            "completed_at": status.completed_at.isoformat() if status.completed_at else None,
            "total_found": status.total_found,
            "new_count": status.new_count,
            "update_count": status.update_count,
            "unchanged_count": status.unchanged_count,
            "error_count": status.error_count,
            "stop_requested": status.stop_requested,
        }


# Singleton manager for global access
sync_manager = GoabaseSyncManager()
