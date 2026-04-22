"""Discovery Agent for finding festivals using Exa search with PartyMap deduplication."""

import logging
from typing import Dict, List, Optional

from src.config import Settings
from src.core.database import AsyncSessionLocal
from src.core.models import DiscoveryQuery, Festival, FestivalState
from src.core.schemas import DiscoveredFestival
from src.services.exa_client import ExaClient
from src.services.llm_client import LLMClient
from src.partymap.client import PartyMapClient
from src.agents.deduplication import DeduplicationAgent

logger = logging.getLogger(__name__)


class DiscoveryAgent:
    """
    Agent for discovering festivals from Exa search with integrated PartyMap deduplication.

    Features:
    - Rotates through discovery queries
    - Uses Exa for general search
    - Checks PartyMap for duplicates using LLM
    - Sets appropriate workflow (new vs update)
    - Cost tracking
    - Decision logging
    """

    MAX_COST_CENTS = 200  # $2.00 per run
    QUERIES_PER_RUN = 3

    def __init__(self, settings: Settings):
        self.settings = settings
        self.decisions: List[Dict] = []
        self.cost_cents = 0
        self.exa: Optional[ExaClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.exa = ExaClient(self.settings)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.exa:
            await self.exa.close()

    async def discover(self, manual_query: Optional[str] = None) -> List[DiscoveredFestival]:
        """
        Main discovery method using Exa search.

        If manual_query provided, uses that.
        Otherwise, gets next queries from rotation.
        """
        self.decisions = []
        self.cost_cents = 0

        # Initialize client if not using context manager
        if not self.exa:
            self.exa = ExaClient(self.settings)

        if manual_query:
            queries = [manual_query]
            self._log_decision(
                thought="Manual discovery triggered",
                action="use_manual_query",
                observation=f"Using custom query: {manual_query}",
                next_step="search",
                confidence=1.0,
            )
        else:
            queries = await self._get_next_queries()
            self._log_decision(
                thought="Automatic discovery from rotation",
                action="get_next_queries",
                observation=f"Retrieved {len(queries)} queries from rotation",
                next_step="search_each",
                confidence=1.0,
            )

        all_festivals: List[DiscoveredFestival] = []

        # Process queries with Exa
        for query in queries:
            # Skip goabase queries (handled by separate sync)
            if "goabase" in query.lower() or "psytrance" in query.lower():
                logger.info(f"Skipping goabase query (handled by separate sync): {query}")
                continue
                
            festivals = await self._search_exa(query)
            all_festivals.extend(festivals)

            # Track cost
            self.cost_cents += 10  # $0.10 per Exa search

        # Deduplicate by URL
        all_festivals = self._deduplicate_by_url(all_festivals)

        self._log_decision(
            thought="Discovery complete",
            action="complete",
            observation=f"Found {len(all_festivals)} unique festivals from {len(queries)} queries",
            next_step="done",
            confidence=1.0,
        )

        return all_festivals

    async def discover_with_deduplication(
        self, 
        manual_query: Optional[str] = None,
        enable_deduplication: bool = True
    ) -> List[DiscoveredFestival]:
        """
        Enhanced discovery with integrated PartyMap deduplication.
        
        This method:
        1. Discovers festivals from Exa search
        2. Checks each festival against PartyMap for duplicates
        3. Uses LLM to determine if update is needed
        4. Sets appropriate state and metadata
        
        :param manual_query: Optional manual query string
        :param enable_deduplication: Whether to check PartyMap for duplicates
        :return: List of DiscoveredFestival with deduplication metadata
        """
        # Step 1: Standard discovery
        festivals = await self.discover(manual_query)
        
        if not enable_deduplication:
            logger.info("Deduplication disabled, skipping PartyMap checks")
            # Mark all as new
            for festival in festivals:
                festival.state = FestivalState.NEEDS_RESEARCH_NEW
                festival.workflow_type = "new"
            return festivals
        
        # Step 2: Initialize deduplication agent
        llm = LLMClient(self.settings)
        partymap = PartyMapClient(self.settings)
        dedup_agent = DeduplicationAgent(self.settings, llm, partymap)
        
        try:
            # Step 3: Check each festival for duplicates
            logger.info(f"Checking {len(festivals)} festivals for PartyMap duplicates...")
            
            for idx, festival in enumerate(festivals):
                try:
                    # Check for duplicate
                    result = await dedup_agent.check_duplicate(
                        discovered_name=festival.name,
                        discovered_location=festival.location or "",
                        discovered_dates=festival.raw_data.get("dates") if festival.raw_data else None,
                        discovered_description=festival.raw_data.get("description") if festival.raw_data else None,
                        clean_name=festival.clean_name
                    )
                    
                    # Set metadata based on deduplication result
                    if result.is_duplicate and result.confidence > 0.7:
                        # This is a duplicate - mark for update
                        festival.partymap_event_id = result.event_id
                        festival.state = FestivalState.NEEDS_RESEARCH_UPDATE
                        festival.workflow_type = "update"
                        festival.update_required = True
                        festival.update_reasons = result.update_reasons
                        festival.existing_event_data = result.event_data
                        
                        self._log_decision(
                            thought=f"Festival '{festival.name}' is duplicate of PartyMap event {result.event_id}",
                            action="mark_for_update",
                            observation=f"Confidence: {result.confidence:.2f}, Reasons: {result.update_reasons}",
                            next_step="queue_for_update_research",
                            confidence=result.confidence
                        )
                        
                        logger.info(f"Duplicate found: {festival.name} -> Event {result.event_id} "
                                   f"(update reasons: {result.update_reasons})")
                    else:
                        # This is new - mark for full research
                        festival.state = FestivalState.NEEDS_RESEARCH_NEW
                        festival.workflow_type = "new"
                        
                        self._log_decision(
                            thought=f"Festival '{festival.name}' is new (not in PartyMap)",
                            action="mark_for_new_research",
                            observation=f"Confidence: {result.confidence:.2f}, Reasoning: {result.reasoning}",
                            next_step="queue_for_full_research",
                            confidence=1.0
                        )
                        
                        logger.info(f"New festival: {festival.name}")
                    
                    # Track deduplication cost (~$0.05 per check)
                    self.cost_cents += 5
                    
                except Exception as e:
                    logger.error(f"Deduplication check failed for {festival.name}: {e}")
                    # Default to new research on error
                    festival.state = FestivalState.NEEDS_RESEARCH_NEW
                    festival.workflow_type = "new"
            
            # Summary
            new_count = sum(1 for f in festivals if f.workflow_type == "new")
            update_count = sum(1 for f in festivals if f.workflow_type == "update")
            logger.info(f"Deduplication complete: {new_count} new, {update_count} updates")
            
        finally:
            await llm.close()
            await partymap.close()
        
        return festivals

    async def _get_next_queries(self) -> List[str]:
        """Get next queries from rotation."""
        async with AsyncSessionLocal() as session:
            # Get active queries, ordered by last_used
            result = await session.execute(
                DiscoveryQuery.__table__.select()
                .where(DiscoveryQuery.is_active == True)
                .order_by(DiscoveryQuery.last_used.asc())
                .limit(self.QUERIES_PER_RUN)
            )
            queries = result.scalars().all()

            if not queries:
                # Fallback to default queries
                return [
                    "music festival 2026",
                    "electronic music festival 2026",
                    "outdoor music festival 2026",
                ]

            # Update last_used timestamp
            for query in queries:
                query.last_used = datetime.utcnow()

            await session.commit()

            return [q.query_text for q in queries]

    async def _search_exa(self, query: str) -> List[DiscoveredFestival]:
        """Search for festivals using Exa."""
        self._log_decision(
            thought=f"Searching Exa for: {query}",
            action="search_exa",
            observation=f"Query: {query}",
            next_step="parse_results",
            confidence=1.0,
        )

        try:
            results = await self.exa.search_festivals(query, num_results=10)

            festivals = []
            for result in results:
                try:
                    festivals.append(
                        DiscoveredFestival(
                            source="exa",
                            source_id=result.url.replace("https://", "").replace("http://", "").replace("/", "_")[:255],
                            source_url=result.url,
                            name=result.title,
                            raw_data=result.model_dump(),
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to map Exa result: {e}")
                    continue

            self._log_decision(
                thought=f"Exa returned {len(festivals)} results",
                action="parse_complete",
                observation=f"Mapped {len(festivals)} festivals from Exa results",
                next_step="continue",
                confidence=1.0,
            )

            return festivals

        except Exception as e:
            logger.error(f"Exa search failed: {e}")
            return []

    def _deduplicate_by_url(self, festivals: List[DiscoveredFestival]) -> List[DiscoveredFestival]:
        """Remove duplicates by source_url."""
        seen_urls = set()
        unique = []

        for f in festivals:
            if f.source_url and f.source_url in seen_urls:
                continue
            if f.source_url:
                seen_urls.add(f.source_url)
            unique.append(f)

        self._log_decision(
            thought=f"Deduplicating {len(festivals)} festivals",
            action="deduplicate",
            observation=f"Removed {len(festivals) - len(unique)} duplicates, {len(unique)} unique",
            next_step="done",
            confidence=1.0,
        )

        return unique

    def _filter_non_festivals(
        self, festivals: List[DiscoveredFestival]
    ) -> List[DiscoveredFestival]:
        """
        Filter out items that are clearly not festivals.

        Filters:
        - Just a city name + year (e.g., "Miami 2026", "Tokyo 2025")
        - Single generic words + year (e.g., "Party 2026", "Event 2025")
        - Just numbers (e.g., "2026")
        """
        import re

        # Patterns that indicate non-festival
        city_only_pattern = re.compile(r"^[A-Za-z\s]+\s+20\d{2}$")  # "Miami 2026"
        generic_event_pattern = re.compile(
            r"^(party|event|festival|gathering)\s+20\d{2}$", re.I
        )  # "Party 2026"
        year_only_pattern = re.compile(r"^20\d{2}$")  # Just "2026"

        filtered = []
        removed_count = 0

        for f in festivals:
            name = f.name or ""

            # Skip if name is empty
            if not name:
                removed_count += 1
                continue

            # Check patterns
            is_city_only = city_only_pattern.match(name) and len(name.split()) <= 3
            is_generic = generic_event_pattern.match(name)
            is_year_only = year_only_pattern.match(name)

            if is_city_only or is_generic or is_year_only:
                logger.warning(f"Filtering out likely non-festival: '{name}'")
                removed_count += 1
                continue

            filtered.append(f)

        if removed_count > 0:
            self._log_decision(
                thought=f"Filtered {removed_count} likely non-festivals",
                action="filter",
                observation=f"Removed {removed_count} items, kept {len(filtered)}",
                next_step="continue",
                confidence=0.8,
            )

        return filtered

    def _log_decision(
        self, thought: str, action: str, observation: str, next_step: str, confidence: float
    ):
        """Log an agent decision."""
        self.decisions.append(
            {
                "agent_type": "discovery",
                "step_number": len(self.decisions) + 1,
                "thought": thought,
                "action": action,
                "observation": observation,
                "next_step": next_step,
                "confidence": confidence,
                "cost_cents": 0,
            }
        )


from datetime import datetime
