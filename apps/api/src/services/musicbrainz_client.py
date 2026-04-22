"""MusicBrainz API client for artist lookup with rate limiting."""

import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

import musicbrainzngs

from src.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class ArtistMatch:
    """Result of MusicBrainz artist lookup."""
    
    name: str
    mbid: Optional[str] = None
    sort_name: Optional[str] = None
    disambiguation: Optional[str] = None
    artist_type: Optional[str] = None
    country: Optional[str] = None
    confidence: str = "low"  # high, medium, low
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "mbid": self.mbid,
            "sort_name": self.sort_name,
            "disambiguation": self.disambiguation,
            "type": self.artist_type,
            "country": self.country,
            "confidence": self.confidence,
        }


class MusicBrainzClient:
    """
    Client for MusicBrainz API with rate limiting.
    
    MusicBrainz allows 1 request per second for non-authorized users.
    This client enforces a 1.1 second delay between requests to be safe.
    """
    
    RATE_LIMIT_DELAY = 1.1  # Seconds between requests
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self._last_request_time: Optional[float] = None
        self._lock = asyncio.Lock()
        
        # Set up MusicBrainz API user agent
        musicbrainzngs.set_useragent(
            settings.musicbrainz_useragent or "PartyMap Festival Bot",
            settings.musicbrainz_version or "1.0",
            settings.musicbrainz_contact or "bot@partymap.com"
        )
    
    async def search_artist(self, name: str) -> ArtistMatch:
        """
        Search for an artist by name and return the best match.
        
        Args:
            name: Artist name to search for
            
        Returns:
            ArtistMatch with MBID if found, or name only if not found
        """
        await self._rate_limit()
        
        try:
            # Search for artist (limit to 3 results for faster response)
            result = musicbrainzngs.search_artists(artist=name, limit=3)
            
            if not result or "artist-list" not in result or not result["artist-list"]:
                logger.debug(f"No MusicBrainz results for: {name}")
                return ArtistMatch(name=name, confidence="low")
            
            artists = result["artist-list"]
            best_match = artists[0]
            
            # Determine confidence based on result quality
            confidence = self._determine_confidence(name, best_match, len(artists))
            
            return ArtistMatch(
                name=name,
                mbid=best_match.get("id"),
                sort_name=best_match.get("sort-name"),
                disambiguation=best_match.get("disambiguation"),
                artist_type=best_match.get("type"),
                country=best_match.get("country"),
                confidence=confidence
            )
            
        except Exception as e:
            logger.warning(f"MusicBrainz lookup failed for '{name}': {e}")
            return ArtistMatch(name=name, confidence="low")
    
    async def search_artists_batch(
        self, 
        names: list[str],
        progress_callback: Optional[callable] = None
    ) -> list[ArtistMatch]:
        """
        Search for multiple artists with rate limiting between each.
        
        Args:
            names: List of artist names
            progress_callback: Optional callback(current, total) for progress updates
            
        Returns:
            List of ArtistMatch results in same order as input
        """
        results = []
        total = len(names)
        
        for idx, name in enumerate(names):
            match = await self.search_artist(name)
            results.append(match)
            
            if progress_callback:
                await progress_callback(idx + 1, total)
        
        return results
    
    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        async with self._lock:
            import time
            
            current_time = time.time()
            
            if self._last_request_time is not None:
                elapsed = current_time - self._last_request_time
                if elapsed < self.RATE_LIMIT_DELAY:
                    sleep_time = self.RATE_LIMIT_DELAY - elapsed
                    logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
                    await asyncio.sleep(sleep_time)
            
            self._last_request_time = time.time()
    
    def _determine_confidence(
        self, 
        query_name: str, 
        match: dict, 
        result_count: int
    ) -> str:
        """
        Determine confidence level for a match.
        
        Args:
            query_name: Original search query
            match: Best matching artist data
            result_count: Total number of results returned
            
        Returns:
            Confidence level: "high", "medium", or "low"
        """
        match_name = match.get("name", "").lower()
        query_lower = query_name.lower()
        
        # Exact match = high confidence
        if match_name == query_lower:
            return "high"
        
        # Single result with close name = high confidence
        if result_count == 1:
            return "high"
        
        # Check for exact word match
        if query_lower in match_name or match_name in query_lower:
            return "medium"
        
        # Multiple results with no exact match = medium confidence
        if result_count > 1:
            return "medium"
        
        return "low"
    
    async def close(self):
        """Cleanup (no-op for this client)."""
        pass
