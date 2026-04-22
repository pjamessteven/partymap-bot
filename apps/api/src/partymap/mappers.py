"""Mappers for transforming festival data to PartyMap format."""

from datetime import datetime
from typing import List, Optional

from src.core.schemas import EventDateData, MediaItem, ResearchedFestival, TicketInfo, FestivalData


class FestivalMapper:
    """Map researched festivals to PartyMap API format."""

    @staticmethod
    def to_create_event_request(festival) -> dict:
        """Map to POST /events request body.

        Handles both ResearchedFestival and FestivalData objects.
        """
        # Handle both ResearchedFestival (has .festival_data) and FestivalData directly
        if hasattr(festival, 'festival_data'):
            festival = festival.festival_data

        if not festival.event_dates:
            raise ValueError("Festival must have at least one event date")

        first_date = festival.event_dates[0]

        # Build base payload
        payload = {
            "name": festival.name,
            "description": festival.description or f"{festival.name} music festival",
            "full_description": festival.full_description or "",
            "youtube_url": str(festival.youtube_url) if festival.youtube_url else None,
            "url": str(festival.website_url) if festival.website_url else None,
            "tags": festival.tags[:5] if festival.tags else [],  # Max 5 tags
        }

        # Add logo
        if festival.logo_url:
            payload["logo"] = {"url": str(festival.logo_url)}

        # Add media items (gallery photos with captions)
        if festival.media_items:
            payload["media_items"] = [
                {
                    "url": str(m.url),
                    "caption": m.caption or f"Photo from {festival.source_url or 'festival website'}"
                }
                for m in festival.media_items
            ]

        # Add RRULE if festival is recurring
        if festival.is_recurring and festival.rrule:
            payload["rrule"] = festival.rrule.model_dump()

        # Add first event date data
        payload["date_time"] = {
            "start": first_date.start.isoformat(),
            "end": (first_date.end or first_date.start).isoformat(),
        }
        payload["location"] = {"description": first_date.location_description}

        # Add ticket URL and structured tickets
        if first_date.ticket_url:
            payload["ticket_url"] = str(first_date.ticket_url)

        if first_date.tickets:
            payload["tickets"] = FestivalMapper._map_tickets(first_date.tickets)

        # Add lineup artists
        if first_date.lineup:
            payload["next_event_date_artists"] = [{"name": a} for a in first_date.lineup]

        # Add size (capacity/attendance)
        if first_date.size:
            payload["next_event_date_size"] = first_date.size

        # Add lineup images
        if first_date.lineup_images:
            payload["next_event_date_lineup_images"] = [
                {
                    "url": url,
                    "caption": f"Lineup from {festival.source_url or 'festival website'}"
                }
                for url in first_date.lineup_images
            ]

        return payload

    @staticmethod
    def to_add_event_date_request(event_date) -> dict:
        """Map to POST /api/date/event/{id} request body.

        Handles both EventDate and EventDateData objects.
        """
        payload = {
            "date_time": {
                "start": event_date.start.isoformat(),
                "end": event_date.end.isoformat() if event_date.end else None,
            },
            "location": {"description": event_date.location_description},
        }

        # Handle ticket_url (could be attribute on EventDateData or EventDate)
        ticket_url = getattr(event_date, 'ticket_url', None)
        if ticket_url:
            payload["url"] = str(ticket_url)

        # Handle size (could be 'size' or 'expected_size')
        size = getattr(event_date, 'size', None) or getattr(event_date, 'expected_size', None)
        if size:
            payload["size"] = size

        # Handle lineup (could be 'lineup' list)
        lineup = getattr(event_date, 'lineup', None)
        if lineup:
            payload["artists"] = [{"name": a} for a in lineup]

        # Handle tickets
        tickets = getattr(event_date, 'tickets', None)
        if tickets:
            payload["tickets"] = FestivalMapper._map_tickets(tickets)

        # Handle lineup_images
        lineup_images = getattr(event_date, 'lineup_images', None)
        if lineup_images:
            payload["lineup_images"] = [{"url": url} for url in lineup_images]

        return payload

    @staticmethod
    def to_update_event_request(festival, message: str = "Auto-updated") -> dict:
        """Map to PUT /events/{id} request body.

        CRITICAL: Only updates general Event fields.
        NEVER includes date_time, location, or rrule (would delete future EventDates!).

        Handles both ResearchedFestival and FestivalData objects.
        """
        # Handle both types
        if hasattr(festival, 'festival_data'):
            festival = festival.festival_data

        payload = {"message": message}

        # General Event fields only
        if festival.name:
            payload["name"] = festival.name
        if festival.description:
            payload["description"] = festival.description
        if festival.full_description:
            payload["full_description"] = festival.full_description
        if festival.youtube_url:
            payload["youtube_url"] = str(festival.youtube_url)
        if festival.website_url:
            payload["url"] = str(festival.website_url)
        if festival.tags:
            payload["add_tags"] = festival.tags[:5]  # Max 5 tags
        if festival.logo_url:
            payload["logo"] = {"url": str(festival.logo_url)}
        if festival.media_items:
            payload["media_items"] = [
                {"url": str(m.url), "caption": m.caption or ""}
                for m in festival.media_items
            ]

        # NOTE: We intentionally do NOT include:
        # - date_time (would delete EventDates)
        # - location (would delete EventDates)
        # - rrule (would affect recurrence)

        return payload

    @staticmethod
    def _map_tickets(tickets: List[TicketInfo]) -> List[dict]:
        """Map ticket info to PartyMap format."""
        mapped = []
        for t in tickets:
            ticket_dict = {
                "url": str(t.url) if t.url else None,
                "description": t.description,
                "price_min": float(t.price_min) if t.price_min else None,
                "price_max": float(t.price_max) if t.price_max else None,
                "price_currency_code": t.price_currency_code,
            }
            # Remove None values to keep payload clean
            ticket_dict = {k: v for k, v in ticket_dict.items() if v is not None}
            mapped.append(ticket_dict)
        return mapped


class GoabaseMapper:
    """Map Goabase API data to internal schemas."""

    @staticmethod
    def map_event_list_item(item: dict) -> dict:
        """Map Goabase event list item to discovered festival."""
        return {
            "source": "goabase",
            "source_id": str(item.get("id", "")),
            "source_url": item.get("urlPartyJson"),
            "name": item.get("name"),
            "raw_data": item,
        }

    @staticmethod
    def map_event_details(json_data: dict, jsonld_data: dict) -> ResearchedFestival:
        """Map Goabase event details to ResearchedFestival."""
        party = json_data.get("party", {})

        # Extract basic info
        name = html.unescape(jsonld_data.get("name", ""))
        description = GoabaseMapper._parse_description(
            jsonld_data.get("description", ""),
            jsonld_data.get("performers", ""),
        )

        # Extract location
        location_data = jsonld_data.get("location", {})
        location_desc = GoabaseMapper._build_location_description(location_data)

        # Extract dates
        start_date = jsonld_data.get("startDate")
        end_date = jsonld_data.get("endDate")

        event_dates = []
        if start_date:
            from dateutil import parser

            event_dates.append(
                EventDateData(
                    start=parser.parse(start_date),
                    end=parser.parse(end_date) if end_date else None,
                    location_description=location_desc,
                    lineup=GoabaseMapper._parse_lineup(jsonld_data.get("performers", "")),
                    ticket_url=jsonld_data.get("url", ""),
                )
            )

        # Extract tags
        tags = ["goabase", "psytrance"]
        name_type = jsonld_data.get("nameType")
        if name_type:
            tags.append(name_type.lower())

        # Extract hashtags from description
        tags.extend(GoabaseMapper._extract_hashtags(description))

        # Extract media
        image_data = jsonld_data.get("image", {})
        logo_url = GoabaseMapper._get_image_url(image_data)

        return ResearchedFestival(
            name=name,
            description=GoabaseMapper._create_summary(description),
            full_description=description,
            website_url=jsonld_data.get("url"),
            location_description=location_desc,
            event_dates=event_dates,
            tags=list(set(tags)),  # Deduplicate
            logo_url=logo_url,
            source="goabase",
            source_url=jsonld_data.get("url"),
            source_modified=GoabaseMapper._parse_modified(party.get("dateModified")),
            lineup_images=[logo_url] if logo_url else [],
        )

    @staticmethod
    def _parse_description(description: Optional[str], lineup: Optional[str]) -> str:
        """Parse and combine description and lineup."""
        import html

        lineup = html.unescape(lineup or "")
        description = html.unescape(description or "")

        if not description or description.lower() in ["coming", ""]:
            return lineup or "Description coming soon..."

        if lineup and len(lineup) > 1:
            return f"{description}\n\n{lineup}"

        return description

    @staticmethod
    def _create_summary(description: str, max_length: int = 297) -> str:
        """Create short summary from description."""
        if len(description) <= max_length:
            return description
        return description[:max_length] + "..."

    @staticmethod
    def _build_location_description(location: dict) -> str:
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

    @staticmethod
    def _parse_lineup(performers: str) -> List[str]:
        """Parse performers string into artist list."""
        if not performers or performers.lower() == "tba":
            return []

        # Split by common separators
        import re

        artists = re.split(r"[,;\n]", performers)
        return [a.strip() for a in artists if a.strip()]

    @staticmethod
    def _extract_hashtags(text: str) -> List[str]:
        """Extract hashtags from text."""
        import re

        return re.findall(r"(?<=#)\w+", text)

    @staticmethod
    def _get_image_url(image: any) -> Optional[str]:
        """Extract image URL from image data."""
        if isinstance(image, list) and image:
            image = image[0]
        if isinstance(image, dict):
            return image.get("url") or image.get("thumbnailUrl")
        return None

    @staticmethod
    def _parse_modified(modified: Optional[str]) -> Optional[datetime]:
        """Parse modification date string."""
        if not modified:
            return None
        try:
            from dateutil import parser

            return parser.parse(modified)
        except Exception:
            return None


# Need to import html at module level
import html
