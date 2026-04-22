"""Goabase API source adapter for psytrance festivals."""

import logging
from typing import List

import httpx

from src.config import Settings
from src.core.schemas import DiscoveredFestival, ResearchedFestival
from src.partymap.mappers import GoabaseMapper
from src.research.lineup_extractor import LineupExtractor
from src.sources.base import SourceInterface

logger = logging.getLogger(__name__)


class GoabaseSource(SourceInterface):
    """Source adapter for Goabase API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.goabase_base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)
        self.lineup_extractor = LineupExtractor(settings)
        self.mapper = GoabaseMapper()

    @property
    def name(self) -> str:
        return "goabase"

    async def health_check(self) -> bool:
        """Check if Goabase API is available."""
        try:
            response = await self.client.get(f"{self.base_url}json/")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Goabase health check failed: {e}")
            return False

    async def discover(self) -> List[DiscoveredFestival]:
        """
        Fetch list of events from Goabase API.

        Returns:
            List of discovered festivals
        """
        logger.info("Discovering festivals from Goabase...")

        try:
            response = await self.client.get(f"{self.base_url}json/")
            response.raise_for_status()

            data = response.json()
            event_list = data.get("partylist", [])

            discovered = []
            for item in event_list:
                try:
                    mapped = self.mapper.map_event_list_item(item)
                    discovered.append(DiscoveredFestival(**mapped))
                except Exception as e:
                    logger.warning(f"Failed to map Goabase event: {e}")
                    continue

            logger.info(f"Discovered {len(discovered)} festivals from Goabase")
            return discovered

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch Goabase events: {e}")
            raise

    async def research(self, discovered: DiscoveredFestival) -> ResearchedFestival:
        """
        Fetch full details for a Goabase event.

        Uses both JSON and JSON-LD endpoints for comprehensive data.
        """
        if not discovered.source_url:
            raise ValueError("Discovered festival missing source_url")

        logger.debug(f"Researching Goabase event: {discovered.source_url}")

        try:
            # Fetch both formats
            json_response = await self.client.get(discovered.source_url)
            json_response.raise_for_status()

            jsonld_url = discovered.source_url.replace("json", "jsonld")
            jsonld_response = await self.client.get(jsonld_url)
            jsonld_response.raise_for_status()

            json_data = json_response.json()
            jsonld_data = jsonld_response.json()

            # Map to ResearchedFestival
            festival = self.mapper.map_event_details(json_data, jsonld_data)
            festival.discovered_id = discovered.id

            # Extract lineup from image if available and lineup is empty
            if festival.lineup_images and (
                not festival.event_dates or not festival.event_dates[0].lineup
            ):
                logger.info(f"Attempting lineup extraction from image for: {festival.name}")

                for image_url in festival.lineup_images:
                    try:
                        artists = await self.lineup_extractor.extract_lineup(
                            description=festival.full_description,
                            image_url=str(image_url),
                        )

                        if artists and festival.event_dates:
                            festival.event_dates[0].lineup = artists
                            logger.info(
                                f"Extracted {len(artists)} artists from image for: {festival.name}"
                            )
                            break

                    except Exception as e:
                        logger.warning(f"Failed to extract lineup from {image_url}: {e}")
                        continue

            return festival

        except httpx.HTTPError as e:
            logger.error(f"HTTP error researching Goabase event: {e}")
            raise
        except Exception as e:
            logger.error(f"Error researching Goabase event: {e}")
            raise

    async def close(self):
        """Cleanup resources."""
        await self.client.aclose()
        await self.lineup_extractor.close()
