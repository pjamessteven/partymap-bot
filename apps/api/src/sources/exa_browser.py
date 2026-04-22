"""Exa search + LangGraph agent source for festival discovery."""

import logging
from typing import List

from src.config import Settings
from src.core.schemas import DiscoveredFestival, EventDateData, ResearchedFestival
from src.research.exa_client import ExaClient
from src.sources.base import SourceInterface

logger = logging.getLogger(__name__)


class ExaBrowserSource(SourceInterface):
    """
    Source adapter using Exa search + LangGraph research agent.

    Flow:
    1. Search for festivals using Exa API
    2. Research each result using LangGraph agent
    3. Extract structured data
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.exa = ExaClient(settings)

    @property
    def name(self) -> str:
        return "exa_browser"

    async def health_check(self) -> bool:
        """Check if Exa API is available."""
        try:
            results = await self.exa.search_festivals("test", num_results=1)
            return True
        except Exception as e:
            logger.error(f"Exa health check failed: {e}")
            return False

    async def discover(
        self,
        query: str = "music festival 2026",
        num_results: int = 10,
    ) -> List[DiscoveredFestival]:
        """
        Discover festivals using Exa search.

        Args:
            query: Search query (e.g., "music festival 2026 Europe")
            num_results: Number of results to fetch

        Returns:
            List of discovered festivals
        """
        logger.info(f"Discovering festivals via Exa: {query}")

        results = await self.exa.search_festivals(query, num_results=num_results)

        discovered = []
        for result in results:
            try:
                # Use URL as source_id
                source_id = (
                    result.url.replace("https://", "").replace("http://", "").replace("/", "_")
                )

                discovered.append(
                    DiscoveredFestival(
                        source="exa_browser",
                        source_id=source_id[:255],  # Limit length
                        source_url=result.url,
                        name=result.title,
                        raw_data=result.model_dump(),
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to map Exa result: {e}")
                continue

        logger.info(f"Discovered {len(discovered)} festivals from Exa")
        return discovered

    async def research(self, discovered: DiscoveredFestival) -> ResearchedFestival:
        """
        Research a festival using LangGraph agent.

        Uses LangGraph with DeepSeek to navigate the site and extract data.
        """
        if not discovered.source_url:
            raise ValueError("Discovered festival missing source_url")

        logger.info(f"Researching via LangGraph: {discovered.source_url}")

        # Use LangGraph research agent
        from src.agents.research.graph import get_research_graph
        from src.agents.research.state import ResearchState
        from src.partymap.client import PartyMapClient
        from src.services.browser_service import BrowserService
        from src.services.exa_client import ExaClient
        from src.services.llm_client import LLMClient
        from src.services.musicbrainz_client import MusicBrainzClient

        # Initialize services
        browser = BrowserService(self.settings)
        llm = LLMClient(self.settings)
        exa = ExaClient(self.settings)
        musicbrainz = MusicBrainzClient(self.settings)
        partymap = PartyMapClient(self.settings)

        try:
            await browser.start()

            # Create graph
            graph = get_research_graph()

            # Create initial state
            thread_id = f"exa_browser_{discovered.source_id}"
            initial_state = ResearchState(
                festival_name=discovered.name,
                source_url=discovered.source_url,
                discovered_data=discovered.raw_data,
                budget_cents=50,  # Default budget
            )

            # Run graph
            config = {
                "configurable": {"thread_id": thread_id},
                "browser": browser,
                "llm": llm,
                "exa": exa,
                "musicbrainz": musicbrainz,
                "partymap": partymap,
                "settings": self.settings,
            }

            result_state = await graph.ainvoke(initial_state, config=config)

            # Extract result
            final_result = result_state.get("final_result")
            if final_result:
                # Map to ResearchedFestival
                festival = self._map_festival_data(final_result, discovered)
                logger.info(f"Successfully researched: {festival.name}")
                return festival
            else:
                raise ValueError("Research did not return valid festival data")

        finally:
            await browser.close()
            await llm.close()
            await exa.close()
            await musicbrainz.close()
            await partymap.close()

    def _map_festival_data(
        self, festival_data: dict, discovered: DiscoveredFestival
    ) -> ResearchedFestival:
        """Map LangGraph festival data to ResearchedFestival."""
        from src.core.schemas import FestivalData

        # Parse the festival data
        if isinstance(festival_data, dict):
            festival_data = FestivalData(**festival_data)

        # Map event dates
        event_dates = []
        for ed in festival_data.event_dates:
            event_dates.append(
                EventDateData(
                    start=ed.start,
                    end=ed.end,
                    location_description=ed.location_description,
                    location_country=ed.location_country,
                    location_lat=ed.location_lat,
                    location_lng=ed.location_lng,
                    lineup=ed.lineup,
                    ticket_url=str(ed.ticket_url) if ed.ticket_url else None,
                    expected_size=ed.expected_size or getattr(ed, 'size', None),
                    source_url=ed.source_url,
                )
            )

        return ResearchedFestival(
            discovered_id=discovered.id,
            name=festival_data.name,
            description=festival_data.description,
            full_description=festival_data.full_description,
            website_url=str(festival_data.website_url) if festival_data.website_url else discovered.source_url,
            location_description=event_dates[0].location_description if event_dates else None,
            logo_url=str(festival_data.logo_url) if festival_data.logo_url else None,
            media_items=[{"url": str(m.url), "caption": m.caption} for m in festival_data.media_items] if festival_data.media_items else [],
            lineup_images=getattr(festival_data.event_dates[0], 'lineup_images', []) if festival_data.event_dates else [],
            tags=festival_data.tags,
            event_dates=event_dates,
            source="exa_browser",
            source_url=discovered.source_url,
            research_metadata={"langgraph_result": festival_data.model_dump()},
        )

    async def search_and_research(
        self,
        query: str,
        num_results: int = 5,
    ) -> List[ResearchedFestival]:
        """
        Convenience method: search and research in one call.

        Returns fully researched festivals directly.
        """
        discovered = await self.discover(query, num_results)

        researched = []
        for d in discovered:
            try:
                r = await self.research(d)
                researched.append(r)
            except Exception as e:
                logger.error(f"Failed to research {d.source_url}: {e}")
                continue

        return researched

    async def close(self):
        """Cleanup resources."""
        await self.exa.close()
