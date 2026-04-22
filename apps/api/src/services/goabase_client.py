"""Goabase API client for psytrance festivals."""

import html
import logging
import re
from typing import List, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import Settings
from src.core.schemas import DiscoveredFestival, EventDateData, FestivalData

logger = logging.getLogger(__name__)


class GoabaseParty:
    """Raw party data from Goabase."""

    def __init__(self, party_id: str, name: str, url: str):
        self.party_id = party_id
        self.name = name
        self.url = url


class GoabaseClient:
    """
    Client for Goabase API.

    Base URL: https://www.goabase.net/api/party/
    Provides psytrance festival data.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.goabase_base_url or "https://www.goabase.net/api/party/"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def get_party_list(self) -> List[GoabaseParty]:
        """Fetch list of all parties from Goabase."""
        try:
            response = await self.client.get(f"{self.base_url}json/")
            response.raise_for_status()

            data = response.json()
            party_list = data.get("partylist", [])

            parties = []
            for item in party_list:
                try:
                    party = GoabaseParty(
                        party_id=str(item.get("id", "")),
                        name=item.get("name", ""),
                        url=item.get("urlPartyJson", ""),
                    )
                    if party.url:
                        parties.append(party)
                except Exception as e:
                    logger.warning(f"Failed to parse party list item: {e}")
                    continue

            logger.info(f"Goabase returned {len(parties)} parties")
            return parties

        except Exception as e:
            logger.error(f"Failed to fetch Goabase party list: {e}")
            raise

    async def get_party_details(self, party_url: str) -> Optional[FestivalData]:
        """Fetch detailed info for a party."""
        try:
            # Fetch JSON endpoint
            json_response = await self.client.get(party_url)
            json_response.raise_for_status()
            json_data = json_response.json()

            # Fetch JSON-LD endpoint
            jsonld_url = party_url.replace("json", "jsonld")
            jsonld_response = await self.client.get(jsonld_url)
            jsonld_response.raise_for_status()
            jsonld_data = jsonld_response.json()

            return self._parse_party_data(json_data, jsonld_data, party_url)

        except Exception as e:
            logger.error(f"Failed to fetch party details for {party_url}: {e}")
            return None

    def _parse_party_data(
        self, json_data: dict, jsonld_data: dict, source_url: str
    ) -> FestivalData:
        """Parse Goabase JSON/JSON-LD into FestivalData."""

        # Extract from JSON-LD (richer data)
        name = html.unescape(jsonld_data.get("name", ""))
        description = html.unescape(jsonld_data.get("description", ""))

        # Get performers/lineup
        performers = jsonld_data.get("performers", "")
        if performers and performers.lower() != "tba":
            lineup = self._parse_lineup(performers)
        else:
            lineup = []

        # Get dates
        start_date = self._parse_datetime(jsonld_data.get("startDate"))
        end_date = self._parse_datetime(jsonld_data.get("endDate"))

        # Get location
        location_data = jsonld_data.get("location", {})
        location_desc = self._build_location_description(location_data)

        # Get image/logo
        image_data = jsonld_data.get("image", {})
        logo_url = self._extract_image_url(image_data)

        # Get event URL
        event_url = jsonld_data.get("url", "")

        # Get modification date from JSON data (not JSON-LD)
        party_data = json_data.get("party", {})
        goabase_modified = party_data.get("dateModified")

        # Build tags
        tags = ["goabase", "psytrance"]
        name_type = jsonld_data.get("nameType")
        if name_type:
            tags.append(name_type.lower())

        # Extract hashtags from description
        tags.extend(self._extract_hashtags(description))

        # Create EventDate
        event_date = EventDateData(
            start=start_date,
            end=end_date,
            location_description=location_desc,
            lineup=lineup,
            source_url=event_url or source_url,
        )

        # Generate clean_name for deduplication
        from src.utils.name_cleaner import clean_event_name

        clean_name = clean_event_name(name)

        # Create FestivalData with discovered_data containing goabase_modified
        return FestivalData(
            name=name,
            clean_name=clean_name,
            raw_name=name,
            description=self._create_summary(description, lineup),
            full_description=self._build_full_description(description, performers),
            website_url=event_url,
            logo_url=logo_url,
            tags=list(set(tags)),
            event_dates=[event_date],
            source="goabase",
            source_url=source_url,
            discovered_data={
                "goabase_modified": goabase_modified,
            }
            if goabase_modified
            else {},
        )

    def _parse_lineup(self, performers: str) -> List[str]:
        """Parse performers string into artist list."""
        if not performers or performers.lower() == "tba":
            return []

        artists = re.split(r"[,;\n]", performers)
        cleaned = []
        for artist in artists:
            name = artist.strip()
            name = html.unescape(name)
            if len(name) > 1:
                cleaned.append(name.title())

        seen = set()
        return [a for a in cleaned if not (a in seen or seen.add(a))]

    def _parse_datetime(self, dt_string: Optional[str]):
        """Parse ISO datetime string."""
        if not dt_string:
            return None

        try:
            from dateutil import parser

            return parser.parse(dt_string.replace("Z", "+00:00"))
        except Exception as e:
            logger.warning(f"Failed to parse datetime {dt_string}: {e}")
            return None

    def _build_location_description(self, location: dict) -> str:
        """Build location description from location data."""
        parts = []

        if name := location.get("name"):
            parts.append(name)

        if address := location.get("address", {}):
            address_parts = [
                address.get("streetAddress", ""),
                address.get("addressLocality", ""),
                address.get("addressCountry", ""),
            ]
            parts.append(", ".join(filter(bool, address_parts)))

        return ", ".join(filter(bool, parts))

    def _extract_image_url(self, image) -> Optional[str]:
        """Extract image URL from image data."""
        if isinstance(image, list) and image:
            image = image[0]
        if isinstance(image, dict):
            return image.get("url") or image.get("thumbnailUrl")
        return None

    def _extract_hashtags(self, text: str) -> List[str]:
        """Extract hashtags from text."""
        return re.findall(r"(?<=#)\w+", text)

    def _create_summary(self, description: str, lineup: List[str]) -> str:
        """Create short summary from description."""
        if not description or description.lower() in ["coming", "", "tba"]:
            if lineup:
                return f"Lineup: {', '.join(lineup[:5])}..."
            return "Psytrance festival"

        summary = description[:297]
        if len(description) > 297:
            summary += "..."
        return summary

    def _build_full_description(self, description: str, performers: str) -> str:
        """Build full description with lineup."""
        desc = html.unescape(description or "")
        perf = html.unescape(performers or "")

        if not desc or desc.lower() in ["coming", "", "tba"]:
            return perf or "Description coming soon..."

        if perf and perf.lower() != "tba":
            return f"{desc}\n\nLineup:\n{perf}"

        return desc

    def parse_to_discovered(self, parties: List[GoabaseParty]) -> List[DiscoveredFestival]:
        """Parse GoabaseParty list into DiscoveredFestival objects."""
        discovered = []

        for party in parties:
            try:
                festival = DiscoveredFestival(
                    source="goabase",
                    source_id=party.party_id,
                    source_url=party.url,
                    name=party.name,
                    discovered_data={
                        "party_id": party.party_id,
                        "name": party.name,
                    },
                )
                discovered.append(festival)
            except Exception as e:
                logger.warning(f"Failed to parse party {party.party_id}: {e}")
                continue

        return discovered
