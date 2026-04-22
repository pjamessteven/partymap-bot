"""Goabase sync module - simple URL-based deduplication with modified_date tracking.

This module handles syncing festivals from Goabase API to PartyMap using
simple URL matching and modified_date comparison for efficiency.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from src.config import Settings
from src.core.models import Festival, FestivalState
from src.core.schemas import DiscoveredFestival
from src.services.goabase_client import GoabaseClient
from src.core.database import AsyncSessionLocal
from sqlalchemy import select

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
        self._status = SyncStatus(
            is_running=True,
            started_at=datetime.utcnow()
        )
    
    def mark_complete(self):
        """Mark sync as complete."""
        self._status.is_running = False
        self._status.completed_at = datetime.utcnow()
        self._status.stop_requested = False
    
    def update_progress(self, current: int, total: int, operation: str):
        """Update sync progress."""
        self._status.current_operation = f"{operation} ({current}/{total})"


class GoabaseSync:
    """
    Sync festivals from Goabase to PartyMap.
    
    Simple deduplication:
    - URL matching for duplicates
    - modified_date comparison for updates
    - Stores full Goabase payload
    """
    
    def __init__(self, settings: Settings, manager: Optional[GoabaseSyncManager] = None):
        self.settings = settings
        self.goabase: Optional[GoabaseClient] = None
        self.manager = manager or GoabaseSyncManager()
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.goabase = GoabaseClient(self.settings)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.goabase:
            await self.goabase.close()
    
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
        
        try:
            # Step 1: Fetch all parties from Goabase
            status.current_operation = "Fetching from Goabase API"
            parties = await self.goabase.get_all_parties()
            status.total_found = len(parties)
            logger.info(f"Fetched {len(parties)} parties from Goabase")
            
            if status.stop_requested:
                logger.info("Goabase sync stopped after fetch")
                self.manager.mark_complete()
                return self._get_result_dict()
            
            # Step 2: Process each party
            for idx, party in enumerate(parties):
                if status.stop_requested:
                    logger.info(f"Goabase sync stopped at {idx}/{len(parties)}")
                    break
                
                self.manager.update_progress(idx + 1, len(parties), "Processing")
                
                try:
                    await self._process_party(party)
                except Exception as e:
                    logger.error(f"Failed to process Goabase party: {e}")
                    status.error_count += 1
            
            logger.info(
                f"Goabase sync complete: {status.new_count} new, "
                f"{status.update_count} updates, {status.unchanged_count} unchanged, "
                f"{status.error_count} errors"
            )
            
        except Exception as e:
            logger.error(f"Goabase sync failed: {e}")
            status.error_count += 1
        finally:
            self.manager.mark_complete()
        
        return self._get_result_dict()
    
    async def _process_party(self, party: dict) -> None:
        """Process a single Goabase party."""
        status = self.manager.status
        
        # Extract party info
        party_id = party.get("id")
        if not party_id:
            return
        
        url = f"https://www.goabase.net/party/{party_id}"
        name = party.get("name", "")
        modified_date = party.get("modified_date")
        
        # Check if festival exists in our DB
        async with AsyncSessionLocal() as session:
            existing = await self._get_festival_by_url(session, url)
            
            if not existing:
                # NEW festival
                await self._create_new_festival(session, party, url, name, modified_date)
                status.new_count += 1
                logger.info(f"New Goabase festival: {name}")
                
            elif self._needs_update(existing, modified_date):
                # UPDATE needed (modified_date changed)
                await self._mark_for_update(session, existing, party, modified_date)
                status.update_count += 1
                logger.info(f"Goabase update needed: {name}")
                
            else:
                # Unchanged
                status.unchanged_count += 1
    
    async def _get_festival_by_url(self, session, url: str) -> Optional[Festival]:
        """Get festival by source_url."""
        result = await session.execute(
            select(Festival).where(Festival.source_url == url)
        )
        return result.scalar_one_or_none()
    
    def _needs_update(self, existing: Festival, new_modified_date: str) -> bool:
        """Check if festival needs update based on modified_date."""
        if not new_modified_date:
            return False
        
        # Get stored modified_date from discovered_data
        stored_date = existing.discovered_data.get("goabase_modified") if existing.discovered_data else None
        
        if not stored_date:
            # No stored date, assume update needed
            return True
        
        # Compare dates
        return new_modified_date > stored_date
    
    async def _create_new_festival(
        self, 
        session, 
        party: dict, 
        url: str, 
        name: str,
        modified_date: str
    ) -> None:
        """Create new festival from Goabase party."""
        # Build location
        location_parts = []
        if party.get("address"):
            location_parts.append(party["address"])
        if party.get("city"):
            location_parts.append(party["city"])
        if party.get("country"):
            location_parts.append(party["country"])
        location = ", ".join(location_parts) if location_parts else ""
        
        # Store modified_date in discovered_data for future comparison
        party_data = dict(party)
        party_data["goabase_modified"] = modified_date
        
        festival = Festival(
            name=name,
            clean_name=self._clean_name(name),
            source="goabase",
            source_id=str(party.get("id")),
            source_url=url,
            location=location,
            state=FestivalState.NEEDS_RESEARCH_NEW,
            workflow_type="new",
            discovered_data=party_data,
        )
        
        session.add(festival)
        await session.commit()
    
    async def _mark_for_update(
        self, 
        session, 
        existing: Festival, 
        party: dict,
        modified_date: str
    ) -> None:
        """Mark existing festival for update."""
        # Update discovered_data with new data
        party_data = dict(party)
        party_data["goabase_modified"] = modified_date
        
        existing.discovered_data = party_data
        existing.state = FestivalState.NEEDS_RESEARCH_UPDATE
        existing.workflow_type = "update"
        existing.update_required = True
        existing.update_reasons = ["goabase_modified"]
        
        await session.commit()
    
    def _clean_name(self, name: str) -> str:
        """Clean festival name by removing year/edition numbers."""
        import re
        
        # Remove year patterns
        cleaned = re.sub(r'\s+20\d{2}\s*', ' ', name)
        # Remove edition numbers
        cleaned = re.sub(r'\s+(?:edition|vii|viii|ix|x|\d+th)\s*$', '', cleaned, flags=re.I)
        
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
