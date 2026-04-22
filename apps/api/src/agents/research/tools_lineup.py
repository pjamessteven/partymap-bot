"""Lineup extraction tool with MusicBrainz MBID lookup.

Uses a two-step process since DeepSeek is not multimodal:
1. Vision step: GPT-4o-mini describes the lineup image as text
2. Extraction step: DeepSeek extracts structured artist names from the description
3. MusicBrainz: Lookup MBIDs for extracted artists
"""

import json
import logging
from typing import Any, Dict, List, Optional, Type

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from src.services.llm_client import LLMClient
from src.services.musicbrainz_client import MusicBrainzClient
from src.services.vision_client import VisionClient

logger = logging.getLogger(__name__)


class LineupExtractionInput(BaseModel):
    """Input for lineup extraction."""
    image_url: str = Field(description="URL of the lineup image to analyze")
    festival_context: Optional[str] = Field(
        default=None,
        description="Optional context about the festival (genre, location, etc.)"
    )


class LineupExtractionTool(BaseTool):
    """
    Extract artist lineup from an image with MusicBrainz MBID lookup.
    
    Two-step process (since DeepSeek is not multimodal):
    1. GPT-4o-mini describes the lineup image as text
    2. DeepSeek extracts structured artist names from the description
    3. MusicBrainz lookup for MBIDs
    
    Rate limiting: 1.1 seconds between MusicBrainz requests
    """

    name: str = "extract_lineup"
    description: str = """Extract artist lineup from an image with MusicBrainz MBID lookup.
    
    Use this tool when you find a lineup poster or artist list image.
    It will extract artist names and look up their MusicBrainz IDs for accurate identification.
    """
    args_schema: Type[BaseModel] = LineupExtractionInput

    # Dependencies
    vision: Optional[VisionClient] = None  # GPT-4o-mini for image description
    llm: Optional[LLMClient] = None  # DeepSeek for text extraction
    musicbrainz: Optional[MusicBrainzClient] = None
    writer: Optional[callable] = None

    def _run(self, image_url: str, festival_context: Optional[str] = None) -> str:
        """Synchronous execution not supported."""
        raise NotImplementedError("Use async version")

    async def _arun(
        self,
        image_url: str,
        festival_context: Optional[str] = None
    ) -> str:
        """
        Extract lineup from image and lookup MBIDs.
        
        Args:
            image_url: URL of lineup image
            festival_context: Optional context about the festival
            
        Returns:
            JSON string with structured artist data
        """
        if not self.vision or not self.llm or not self.musicbrainz:
            return json.dumps({
                "error": "Required services not available (vision, llm, musicbrainz)",
                "artists": []
            })

        # Progress update
        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": self.name,
                "progress": 0.0,
                "message": f"Analyzing lineup image: {image_url}"
            })

        try:
            # Step 1: Use GPT-4o-mini to describe the image
            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": self.name,
                    "progress": 0.1,
                    "message": "Step 1/3: Describing image with vision model..."
                })

            image_description = await self.vision.describe_lineup_image(
                image_url,
                festival_context=festival_context
            )

            if not image_description:
                return json.dumps({
                    "error": "Failed to describe image",
                    "artists": []
                })

            logger.info(f"Vision model described image: {len(image_description)} chars")

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": self.name,
                    "progress": 0.35,
                    "message": f"Step 1/3: Image described ({len(image_description)} chars)"
                })

            # Step 2: Use DeepSeek to extract artist names from description
            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": self.name,
                    "progress": 0.4,
                    "message": "Step 2/3: Extracting artist names from description..."
                })

            artist_names = await self._extract_artists_from_description(
                image_description,
                festival_context
            )

            if not artist_names:
                return json.dumps({
                    "message": "No artists found in image description",
                    "artists": [],
                    "description_preview": image_description[:200] + "..." if len(image_description) > 200 else image_description
                })

            logger.info(f"Extracted {len(artist_names)} artist names from description")

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": self.name,
                    "progress": 0.4,
                    "message": f"Found {len(artist_names)} artists. Looking up MusicBrainz IDs..."
                })

            # Step 3: Lookup MusicBrainz IDs for each artist
            artists = await self._lookup_artists(artist_names)

            # Progress update
            if self.writer:
                high_confidence = sum(1 for a in artists if a.get("confidence") == "high")
                with_mbids = sum(1 for a in artists if a.get("mbid"))

                await self.writer({
                    "type": "tool_progress",
                    "tool_name": self.name,
                    "progress": 1.0,
                    "message": f"Step 3/3: Complete! {len(artists)} artists ({with_mbids} with MBIDs, {high_confidence} high confidence)",
                    "data": {
                        "artist_count": len(artists),
                        "with_mbids": with_mbids,
                        "high_confidence": high_confidence,
                        "description_length": len(image_description)
                    }
                })

            return json.dumps({
                "artists": artists,
                "total_count": len(artists),
                "with_mbids": sum(1 for a in artists if a.get("mbid")),
                "source_url": image_url,
                "description": image_description[:500] + "..." if len(image_description) > 500 else image_description
            })

        except Exception as e:
            logger.error(f"Lineup extraction failed: {e}")
            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": self.name,
                    "progress": 1.0,
                    "message": f"Failed: {str(e)}"
                })
            return json.dumps({
                "error": str(e),
                "artists": []
            })

    async def _extract_artists_from_description(
        self,
        description: str,
        festival_context: Optional[str]
    ) -> List[str]:
        """
        Extract artist names from image description using DeepSeek.
        
        Args:
            description: Text description of the lineup image
            festival_context: Optional context about the festival
            
        Returns:
            List of artist names
        """

        prompt = f"""You are analyzing a music festival lineup. Based on the description below, extract ALL artist names mentioned.

{f"Festival context: {festival_context}" if festival_context else ""}

Image description:
{description}

Instructions:
1. Extract EVERY artist name mentioned (headliners, support acts, DJs, live acts)
2. Preserve the order they appear (headliners usually mentioned first or in larger/bolder text)
3. Do NOT include: stage names, venue names, times, dates, or generic text like "music festival"
4. Return ONLY artist names as a JSON array

Return format:
{{
    "artists": ["Artist Name 1", "Artist Name 2", "Artist Name 3"]
}}

If no clear artist names are found, return: {{"artists": []}}"""

        try:
            response = await self.llm.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a music festival lineup extraction specialist. Extract artist names accurately from descriptions."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"}
            )

            data = json.loads(response)
            artists = data.get("artists", [])

            # Clean up artist names
            cleaned = []
            for artist in artists:
                name = artist.strip()
                # Remove common suffixes/prefixes that aren't part of name
                name = self._clean_artist_name(name)
                if name and len(name) > 1:
                    cleaned.append(name)

            # Remove duplicates while preserving order
            seen = set()
            unique = []
            for name in cleaned:
                lower = name.lower()
                if lower not in seen:
                    seen.add(lower)
                    unique.append(name)

            logger.info(f"Extracted {len(unique)} unique artists from description")
            return unique

        except Exception as e:
            logger.error(f"Failed to extract artists from description: {e}")
            return []

    def _clean_artist_name(self, name: str) -> str:
        """Clean up artist name by removing common non-artist text."""
        import re

        # Remove common stage indicators
        stage_indicators = [
            r"\s*[-–]\s*(main\s+stage|second\s+stage|basement|upstairs|downstairs|oben|unten|bühne|stage|floor|room)",
            r"\s*\((live|dj|b2b|back2back)\)",
            r"^dj\s+",
            r"^live\s+",
        ]

        cleaned = name
        for pattern in stage_indicators:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

        return cleaned

    async def _lookup_artists(self, artist_names: List[str]) -> List[Dict[str, Any]]:
        """Lookup MusicBrainz IDs for all artists."""
        artists = []
        total = len(artist_names)

        for idx, name in enumerate(artist_names):
            # Progress update every 5 artists
            if self.writer and idx % 5 == 0:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": self.name,
                    "progress": 0.4 + (0.6 * (idx / total)),
                    "message": f"Looking up artist {idx + 1}/{total}: {name}"
                })

            # Lookup artist
            match = await self.musicbrainz.search_artist(name)
            artists.append(match.to_dict())

        return artists
