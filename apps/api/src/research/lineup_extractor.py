"""Generic lineup extraction from images and text using LLM."""

import base64
import json
import logging
from typing import List, Optional

import httpx
from PIL import Image

from src.config import Settings

logger = logging.getLogger(__name__)


class LineupExtractor:
    """Extract artist lineup from festival description and images."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.openrouter_base_url,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://partymap.com",
                "X-Title": "PartyMap Festival Bot",
            },
            timeout=60.0,
        )
        self.model = settings.openrouter_model

    async def extract_lineup(
        self,
        description: Optional[str],
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
    ) -> List[str]:
        """
        Extract artist lineup from description and/or image.

        Args:
            description: Festival description text
            image_url: URL to lineup image
            image_base64: Base64-encoded image data

        Returns:
            List of artist names
        """
        if not description and not image_url and not image_base64:
            logger.debug("No description or image provided for lineup extraction")
            return []

        try:
            # Build message content
            content = []

            # Add text prompt
            prompt = self._build_prompt(description)
            content.append({"type": "text", "text": prompt})

            # Add image if provided
            if image_base64:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    }
                )
            elif image_url:
                # Download and encode image
                base64_image = await self._download_and_encode_image(image_url)
                if base64_image:
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        }
                    )

            # Call LLM
            response = await self.client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": content}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,  # Low temperature for consistent extraction
                },
            )
            response.raise_for_status()

            result = response.json()
            content_text = result["choices"][0]["message"]["content"]

            # Parse JSON response
            parsed = json.loads(content_text)
            artists = parsed.get("artists", [])

            # Clean and validate
            cleaned = self._clean_artists(artists)
            logger.info(f"Extracted {len(cleaned)} artists from lineup")
            return cleaned

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during lineup extraction: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error during lineup extraction: {e}")
            return []

    def _build_prompt(self, description: Optional[str]) -> str:
        """Build the extraction prompt."""
        prompt = """You are a music festival lineup extraction assistant. Your task is to identify and extract all artist names from the provided festival description and/or lineup image.

Instructions:
1. Look for sections labeled "Lineup", "Artists", "Performers", "Music", etc.
2. Extract ALL artist names mentioned
3. Include both headliners and support acts
4. Return artists in title case (e.g., "The Beatles" not "the beatles")
5. If no lineup is found, return an empty array
6. Remove duplicates (same artist listed multiple times)
7. Do not include DJ set times, stage names, or venue info

"""

        if description:
            prompt += f"\nFestival Description:\n{description}\n\n"

        prompt += """Return your answer as JSON in this exact format:
{
    "artists": ["Artist Name 1", "Artist Name 2", "Artist Name 3"]
}

If no artists are found, return:
{
    "artists": []
}"""

        return prompt

    async def _download_and_encode_image(self, image_url: str) -> Optional[str]:
        """Download image and convert to base64."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url, timeout=30.0)
                response.raise_for_status()

                # Check size
                content_length = len(response.content)
                if content_length > self.settings.lineup_image_max_size:
                    logger.warning(f"Image too large ({content_length} bytes), resizing...")
                    return await self._resize_and_encode(response.content)

                return base64.b64encode(response.content).decode()

        except Exception as e:
            logger.error(f"Failed to download image from {image_url}: {e}")
            return None

    async def _resize_and_encode(self, image_data: bytes) -> Optional[str]:
        """Resize image to fit within size limits."""
        try:
            from io import BytesIO

            image = Image.open(BytesIO(image_data))

            # Convert to RGB if necessary
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")

            # Calculate new size to get under limit
            # Start with max dimension 1200px
            max_dimension = 1200
            while True:
                ratio = min(
                    max_dimension / image.size[0],
                    max_dimension / image.size[1],
                )
                new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
                resized = image.resize(new_size, Image.Resampling.LANCZOS)

                # Save to buffer
                buffer = BytesIO()
                resized.save(buffer, format="JPEG", quality=85)
                encoded = base64.b64encode(buffer.getvalue()).decode()

                if len(encoded) <= self.settings.lineup_image_max_size:
                    return encoded

                # Reduce further if still too large
                max_dimension -= 200
                if max_dimension < 400:
                    logger.error("Could not resize image to fit within limits")
                    return None

        except Exception as e:
            logger.error(f"Failed to resize image: {e}")
            return None

    def _clean_artists(self, artists: List[str]) -> List[str]:
        """Clean and deduplicate artist list."""
        if not artists:
            return []

        cleaned = []
        seen = set()

        for artist in artists:
            if not artist or not isinstance(artist, str):
                continue

            # Clean the name
            name = artist.strip()
            name = name.title()  # Title case

            # Remove common suffixes/prefixes
            name = name.replace(" (Live)", "")
            name = name.replace(" (Dj Set)", "")
            name = name.replace(" (Live Set)", "")

            # Skip if too short or already seen
            if len(name) < 2 or name.lower() in seen:
                continue

            seen.add(name.lower())
            cleaned.append(name)

        return cleaned

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
