"""LLM client for DeepSeek via OpenRouter."""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from src.config import Settings
from src.core.schemas import EventDateData, FestivalData
from src.services.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Client for DeepSeek LLM via OpenRouter.

    API: https://openrouter.ai/api/v1
    Model: deepseek/deepseek-chat
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.openrouter_api_key
        self.base_url = settings.openrouter_base_url
        self.model = settings.openrouter_model
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://partymap.com",
                "X-Title": "PartyMap Festival Bot",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    @circuit_breaker("llm", failure_threshold=3, recovery_timeout=60.0)
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.1,
        response_format: Optional[Dict] = None,
    ) -> str:
        """Make chat completion request."""
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }

            if response_format:
                payload["response_format"] = response_format

            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            return content

        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.text[:500]
            except Exception:
                pass
            logger.error(
                f"LLM HTTP error {e.response.status_code}: {e}. Body: {body}"
            )
            raise
        except httpx.NetworkError as e:
            logger.error(f"LLM network error: {e}")
            raise
        except (KeyError, IndexError) as e:
            logger.error(f"LLM response parsing error: {e}")
            raise
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            raise

    async def extract_festival_data(
        self,
        html_content: str,
        url: str,
    ) -> FestivalData:
        """
        Extract structured festival data from HTML.

        Args:
            html_content: Raw HTML from festival website
            url: Source URL

        Returns:
            FestivalData with extracted info
        """
        # Truncate HTML if too long
        max_length = 10000
        if len(html_content) > max_length:
            html_content = html_content[:max_length] + "..."

        messages = [
            {
                "role": "system",
                "content": """You are a festival data extraction assistant.
Extract comprehensive information from the provided festival website HTML.

Return ONLY a JSON object in this exact format:
{
    "name": "Festival Name",
    "clean_name": "Canonical Festival Name (without year/edition numbers)",
    "description": "Short description (1-2 sentences)",
    "full_description": "Full detailed description with all relevant info",
    "website_url": "https://...",
    "youtube_url": "https://..." or null,
    "start_date": "2026-07-15T14:00:00",
    "end_date": "2026-07-17T23:00:00",
    "location_description": "Venue, City, Country",
    "lineup": ["Artist 1", "Artist 2"],
    "tags": ["electronic", "camping", "outdoor"],
    "size": 50000,
    "is_recurring": true,
    "recurrence_note": "annual festival"
}

IMPORTANT FIELDS:

1. clean_name: Remove year/number suffixes for deduplication
   - "Festival 2026" -> "Festival"
   - "Event VII" -> "Event"

2. full_description: Extract complete long-form description, not just summary

3. youtube_url: Look for embedded YouTube videos or links on the page

4. size: Expected attendance/capacity if mentioned (e.g., "50,000 people", "capacity 10k")

5. is_recurring: true if text mentions "annual", "yearly", "every summer", "returns each year"

6. recurrence_note: Brief description of recurrence pattern found

7. tags: Genre/style keywords found on page (electronic, psytrance, camping, etc.)

Rules:
- Use ISO 8601 format for dates
- Return empty array [] if no lineup found
- Return null for missing optional fields
- Be precise with location information
- Extract ALL available information
""",
            },
            {
                "role": "user",
                "content": f"Extract festival data from this HTML from {url}:\n\n{html_content}",
            },
        ]

        try:
            response = await self.chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
            )

            # Parse JSON response
            data = json.loads(response)

            # Convert to FestivalData
            from datetime import datetime
            from dateutil import parser
            from src.core.schemas import RRuleData

            # Build event date
            event_date = EventDateData(
                start=parser.parse(data["start_date"]) if data.get("start_date") else None,
                end=parser.parse(data["end_date"]) if data.get("end_date") else None,
                location_description=data.get("location_description", ""),
                lineup=data.get("lineup", []),
                size=data.get("size"),
            )

            # Extract clean_name from LLM or compute it
            clean_name = data.get("clean_name")
            if not clean_name and data.get("name"):
                from src.utils.name_cleaner import clean_event_name
                clean_name = clean_event_name(data.get("name"))

            # Build RRULE if recurring detected (defaults to yearly)
            rrule = None
            is_recurring = data.get("is_recurring", False)
            if is_recurring:
                rrule = RRuleData(
                    recurringType=3,  # yearly
                    exact=False  # Pattern-based unless specific dates mentioned
                )

            return FestivalData(
                name=data.get("name", ""),
                clean_name=clean_name,
                raw_name=data.get("name", ""),
                description=data.get("description"),
                full_description=data.get("full_description"),
                website_url=data.get("website_url"),
                youtube_url=data.get("youtube_url"),
                tags=data.get("tags", []),
                is_recurring=is_recurring,
                rrule=rrule,
                event_dates=[event_date],
            )

        except Exception as e:
            logger.error(f"Failed to extract festival data: {e}")
            raise

    async def extract_lineup_from_image(
        self,
        image_base64: str,
        description: str = "",
    ) -> List[str]:
        """
        Extract artist lineup from image.

        Args:
            image_base64: Base64-encoded image
            description: Optional context from page

        Returns:
            List of artist names
        """
        messages = [
            {
                "role": "system",
                "content": """You are a lineup extraction assistant.
Look at this festival lineup image and extract all artist names.

Return ONLY a JSON object in this format:
{
    "artists": ["Artist Name 1", "Artist Name 2", "Artist Name 3"]
}

Extract ALL artists mentioned, including headliners and support acts.
If no lineup is visible, return {"artists": []}.
""",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Extract lineup from this image. Context: {description}",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            },
        ]

        try:
            response = await self.chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
            )

            data = json.loads(response)
            return data.get("artists", [])

        except Exception as e:
            logger.error(f"Failed to extract lineup from image: {e}")
            return []

    async def analyze_page_structure(
        self,
        html_content: str,
    ) -> Dict[str, Any]:
        """
        Analyze page structure to find relevant links.

        Returns links to About, Lineup, Tickets, etc.
        """
        messages = [
            {
                "role": "system",
                "content": """Analyze this festival website HTML and find relevant page links.

Return a JSON object with found links:
{
    "about_page": "/about" or null,
    "lineup_page": "/lineup" or null,
    "tickets_page": "/tickets" or null,
    "info_page": "/info" or null,
    "has_lineup_on_current_page": true/false
}

Return relative URLs if found, or null if not found.
""",
            },
            {
                "role": "user",
                "content": html_content[:5000],  # Truncate for analysis
            },
        ]

        try:
            response = await self.chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
            )

            return json.loads(response)

        except Exception as e:
            logger.error(f"Failed to analyze page structure: {e}")
            return {}

    async def extract_lineup(self, text: str) -> List[str]:
        """
        Extract artist lineup from text description.

        This is used when the API doesn't provide explicit lineup field
        but the lineup might be embedded in the description text.

        Args:
            text: The text to analyze (description, performers string, etc.)

        Returns:
            List of artist names found
        """
        if not text or len(text) < 10:
            return []

        # Truncate if too long
        max_length = 8000
        if len(text) > max_length:
            text = text[:max_length] + "..."

        messages = [
            {
                "role": "system",
                "content": """You are a music festival lineup extraction assistant.

Extract ALL artist names from the provided text. The text may contain:
- A lineup section with artist names
- A performers list
- Artist mentions in description
- Headliners and support acts

Return ONLY a JSON object in this exact format:
{
    "artists": ["Artist Name 1", "Artist Name 2", "Artist Name 3"]
}

CRITICAL - Exclude these NON-ARTIST items:
- Stage/venue names: "oben", "unten", "upstairs", "downstairs", "main stage", "basement", "floor"
- Time indicators: "opening", "closing", "afterparty", "warmup"
- Generic terms: "live", "dj set", "b2b", "back2back", "all night long"
- Parenthetical info: "(live)", "(dj)", "[label]" - but keep the artist name outside the parens

Rules:
- Include ALL actual artists mentioned
- Use the full artist name as written (keep suffixes like "(live)" or "[label]" in the name if present)
- Remove prefixes like "DJ ", "Live ", "B2B " unless they're part of the artist name
- Return empty array [] if no artists found
- Be thorough - don't miss supporting acts
- Common stage names in any language should be excluded (oben/up, unten/down, hauptbühne/main stage, etc.)
""",
            },
            {
                "role": "user",
                "content": f"Extract all artist names from this text:\n\n{text}",
            },
        ]

        try:
            response = await self.chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
            )

            data = json.loads(response)
            artists = data.get("artists", [])

            # Clean up artist names and filter out non-artist items
            stage_indicators = {
                "oben",
                "unten",
                "upstairs",
                "downstairs",
                "main",
                "basement",
                "floor",
                "stage",
                "bühne",
                "raum",
                "room",
                "opening",
                "closing",
                "warmup",
                "afterparty",
                "headliner",
                "support",
            }

            cleaned = []
            for artist in artists:
                name = artist.strip()

                # Skip if it's just a stage indicator
                lower_name = name.lower()
                if lower_name in stage_indicators or len(name) < 2:
                    continue

                # Remove common prefixes but preserve the name
                for prefix in ["DJ ", "LIVE ", "B2B ", "B2b ", "b2b "]:
                    if name.startswith(prefix) and len(name) > len(prefix):
                        name = name[len(prefix) :]

                if len(name) > 1:
                    cleaned.append(name)

            # Remove duplicates while preserving order
            seen = set()
            unique = []
            for a in cleaned:
                lower = a.lower()
                if lower not in seen:
                    seen.add(lower)
                    unique.append(a)

            logger.info(f"Extracted {len(unique)} artists from text")
            return unique

        except Exception as e:
            logger.error(f"Failed to extract lineup from text: {e}")
            return []

    # ==================== New Enhanced Methods ====================

    async def select_relevant_tags(
        self,
        festival_name: str,
        description: str,
        available_tags: List[str],
        max_tags: int = 5
    ) -> List[str]:
        """
        Select the most relevant tags for a festival from PartyMap's available tags.

        Args:
            festival_name: Name of the festival
            description: Festival description for context
            available_tags: List of available tags from PartyMap (top 150)
            max_tags: Maximum number of tags to select (default 5)

        Returns:
            List of selected tag strings
        """
        # Truncate for token efficiency
        desc = description[:500] if description else ""
        tags_sample = available_tags[:150]  # Ensure max 150

        messages = [
            {
                "role": "system",
                "content": f"""You are a festival tagging expert.

Select up to {max_tags} most relevant tags for this festival from the available list.

Rules:
1. Only use tags from the provided list
2. Select tags that best match the festival's genre, style, and vibe
3. Prioritize specific genre tags over generic ones
4. Return empty array if no good matches
5. Maximum {max_tags} tags

Return ONLY a JSON object:
{{"tags": ["tag1", "tag2", ...]}}""",
            },
            {
                "role": "user",
                "content": f"""Festival: {festival_name}
Description: {desc}

Available tags: {json.dumps(tags_sample)}

Select up to {max_tags} most relevant tags.""",
            },
        ]

        try:
            response = await self.chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
            )

            data = json.loads(response)
            selected = data.get("tags", [])

            # Validate all selected tags are in available list
            valid = [t for t in selected if t in available_tags]

            # Enforce max limit
            return valid[:max_tags]

        except Exception as e:
            logger.error(f"Failed to select tags: {e}")
            return []

    async def select_media(
        self,
        festival_name: str,
        images: List[dict],
        source_url: str
    ) -> dict:
        """
        Intelligently classify and select the best images from a page.

        Args:
            festival_name: Name of the festival
            images: List of image dicts with url, alt, width, height, aspect_ratio
            source_url: Source page URL for attribution

        Returns:
            Dict with "logo", "gallery", and "lineup" keys
        """
        if not images:
            return {"logo": None, "gallery": [], "lineup": []}

        # Limit images for token efficiency
        image_sample = images[:30]  # Analyze top 30 largest images

        messages = [
            {
                "role": "system",
                "content": """You are a media curator for festival websites.

Analyze the provided images and classify them into:
1. LOGO - Best squarish image for event cover/logo (prefer 1:1 aspect ratio, prominent placement, clear branding)
2. GALLERY - Cool photos worth adding to event gallery (atmospheric shots, crowd photos, stage photos)
3. LINEUP - Lineup posters or artist graphics (text-heavy artist listings, schedule graphics)

For each category, select the best options:
- Logo: Choose 1 best option (square-ish preferred, high quality, clear branding)
- Gallery: Choose up to 5 best photos (diverse, high quality, interesting composition)
- Lineup: Choose up to 3 lineup images (readable text, complete lineup visible)

Return ONLY a JSON object:
{
  "logo": {"url": "...", "alt": "..."} or null,
  "gallery": [{"url": "...", "alt": "..."}, ...],
  "lineup": [{"url": "...", "alt": "..."}, ...]
}""",
            },
            {
                "role": "user",
                "content": f"""Festival: {festival_name}
Source: {source_url}

Images to analyze ({len(image_sample)} of {len(images)}):
{json.dumps(image_sample, indent=2)}

Classify and select the best images for each category.""",
            },
        ]

        try:
            response = await self.chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
            )

            data = json.loads(response)

            # Normalize response structure
            result = {
                "logo": data.get("logo"),
                "gallery": data.get("gallery", []),
                "lineup": data.get("lineup", [])
            }

            # Ensure gallery items have proper structure
            normalized_gallery = []
            for item in result["gallery"]:
                if isinstance(item, dict) and item.get("url"):
                    normalized_gallery.append({
                        "url": item["url"],
                        "caption": f"Photo from {source_url}",
                        "media_type": "gallery"
                    })
            result["gallery"] = normalized_gallery[:5]  # Max 5 gallery items

            # Ensure logo has proper structure
            if result["logo"] and isinstance(result["logo"], dict) and result["logo"].get("url"):
                result["logo"] = {
                    "url": result["logo"]["url"],
                    "caption": f"Logo from {source_url}",
                    "media_type": "logo"
                }
            else:
                result["logo"] = None

            # Normalize lineup (just URLs)
            lineup_urls = []
            for item in result["lineup"]:
                if isinstance(item, dict) and item.get("url"):
                    lineup_urls.append(item["url"])
                elif isinstance(item, str):
                    lineup_urls.append(item)
            result["lineup"] = lineup_urls[:3]  # Max 3 lineup images

            return result

        except Exception as e:
            logger.error(f"Failed to select media: {e}")
            return {"logo": None, "gallery": [], "lineup": []}

    async def extract_tickets(self, html: str) -> List[dict]:
        """
        Extract ticket information from HTML using LLM analysis.

        Args:
            html: HTML content of ticket page

        Returns:
            List of ticket dicts with description, price_min, price_max, price_currency_code, url
        """
        # Truncate HTML for token efficiency
        max_length = 8000
        if len(html) > max_length:
            html = html[:max_length] + "..."

        messages = [
            {
                "role": "system",
                "content": """You are a ticket information extraction specialist.

Extract ticket types with pricing from the provided HTML.
Look for:
- Ticket tiers (Early Bird, General Admission, VIP, etc.)
- Price ranges (if tiered pricing)
- Currency (USD, EUR, GBP, etc.)
- Purchase links

Return ONLY a JSON object:
{
  "tickets": [
    {
      "description": "Early Bird",
      "price_min": 149.99,
      "price_max": 149.99,
      "price_currency_code": "USD",
      "url": "https://..."
    },
    {
      "description": "VIP Package",
      "price_min": 499.99,
      "price_max": 599.99,
      "price_currency_code": "USD",
      "url": "https://..."
    }
  ]
}

Rules:
- Use 3-letter currency codes (USD, EUR, GBP, etc.)
- If single price, use same value for min and max
- Extract URL if present, otherwise null
- Return empty array if no pricing found""",
            },
            {
                "role": "user",
                "content": f"Extract ticket information from this HTML:\n\n{html}",
            },
        ]

        try:
            response = await self.chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
            )

            data = json.loads(response)
            tickets = data.get("tickets", [])

            # Validate and normalize tickets
            valid_tickets = []
            for ticket in tickets:
                if ticket.get("description"):
                    valid_tickets.append({
                        "description": ticket["description"],
                        "price_min": ticket.get("price_min"),
                        "price_max": ticket.get("price_max"),
                        "price_currency_code": ticket.get("price_currency_code"),
                        "url": ticket.get("url")
                    })

            return valid_tickets

        except Exception as e:
            logger.error(f"Failed to extract tickets: {e}")
            return []
