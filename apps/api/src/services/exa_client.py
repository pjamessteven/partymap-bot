"""Exa API client for web search."""

import logging
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import Settings
from src.core.schemas import DiscoveredFestival
from src.services.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)


class ExaResult:
    """Single result from Exa search."""

    def __init__(
        self,
        title: str,
        url: str,
        snippet: Optional[str] = None,
        published_date: Optional[str] = None,
        author: Optional[str] = None,
    ):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.published_date = published_date
        self.author = author


class ExaClient:
    """
    Client for Exa search API.

    API: https://api.exa.ai
    Cost: ~$0.10 per search
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.exa_api_key
        self.base_url = "https://api.exa.ai"
        self.client = httpx.AsyncClient(
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    @circuit_breaker("exa", failure_threshold=5, recovery_timeout=30.0)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.NetworkError)),
    )
    async def search(
        self,
        query: str,
        num_results: int = 10,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
    ) -> List[ExaResult]:
        """
        Search for content using Exa API.

        Args:
            query: Search query
            num_results: Number of results (max 100)
            include_domains: Only search these domains
            exclude_domains: Exclude these domains

        Returns:
            List of ExaResult objects
        """
        try:
            payload = {
                "query": query,
                "numResults": min(num_results, 100),
                "type": "neural",  # Use neural search
                "useAutoprompt": True,  # Let Exa optimize
                "contents": {
                    "text": True,  # Get text content
                    "summary": {"query": "festival information"},  # Get summary
                },
            }

            if include_domains:
                payload["includeDomains"] = include_domains
            if exclude_domains:
                payload["excludeDomains"] = exclude_domains

            response = await self.client.post(
                f"{self.base_url}/search",
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            results = []

            for result in data.get("results", []):
                try:
                    exa_result = ExaResult(
                        title=result.get("title", "Untitled"),
                        url=result.get("url", ""),
                        snippet=result.get("text", result.get("summary", "")),
                        published_date=result.get("published_date"),
                        author=result.get("author"),
                    )
                    results.append(exa_result)
                except Exception as e:
                    logger.warning(f"Failed to parse Exa result: {e}")
                    continue

            logger.info(f"Exa search '{query[:50]}...' returned {len(results)} results")
            return results

        except httpx.HTTPStatusError as e:
            logger.error(f"Exa API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Exa search failed: {e}")
            raise

    @circuit_breaker("exa", failure_threshold=5, recovery_timeout=30.0)
    async def find_similar(self, url: str, num_results: int = 5) -> List[ExaResult]:
        """Find similar pages to a given URL."""
        try:
            payload = {
                "url": url,
                "numResults": num_results,
                "contents": {
                    "text": True,
                    "summary": True,
                },
            }

            response = await self.client.post(
                f"{self.base_url}/findSimilar",
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            results = []

            for result in data.get("results", []):
                try:
                    exa_result = ExaResult(
                        title=result.get("title", "Untitled"),
                        url=result.get("url", ""),
                        snippet=result.get("summary", result.get("text", "")),
                    )
                    results.append(exa_result)
                except Exception as e:
                    logger.warning(f"Failed to parse similar result: {e}")
                    continue

            return results

        except Exception as e:
            logger.error(f"Find similar failed: {e}")
            return []

    def parse_to_discovered(self, results: List[ExaResult], query: str) -> List[DiscoveredFestival]:
        """
        Parse Exa results into DiscoveredFestival objects.

        Extracts festival name from title and URL.
        """
        discovered = []

        for result in results:
            try:
                # Skip social media and non-festival sites
                domain = urlparse(result.url).netloc.lower()
                skip_domains = [
                    "facebook.com",
                    "instagram.com",
                    "twitter.com",
                    "x.com",
                    "youtube.com",
                    "tiktok.com",
                    "eventbrite.com",
                    "ticketmaster.com",  # Ticket sites (handle separately)
                ]

                if any(skip in domain for skip in skip_domains):
                    logger.debug(f"Skipping {domain}")
                    continue

                # Extract festival name from title
                name = self._extract_festival_name(result.title)
                if not name:
                    continue

                # Create discovered festival
                festival = DiscoveredFestival(
                    source="exa",
                    source_id=result.url,  # Use URL as ID
                    source_url=result.url,
                    name=name,
                    discovered_data={
                        "title": result.title,
                        "snippet": result.snippet,
                        "query": query,
                        "published_date": result.published_date,
                        "author": result.author,
                    },
                )
                discovered.append(festival)

            except Exception as e:
                logger.warning(f"Failed to parse result {result.url}: {e}")
                continue

        logger.info(f"Parsed {len(discovered)} festivals from {len(results)} Exa results")
        return discovered

    def _extract_festival_name(self, title: str) -> Optional[str]:
        """Extract festival name from page title."""
        if not title:
            return None

        # Clean up title
        name = title.strip()

        # Remove common suffixes
        suffixes = [
            " - Official Website",
            " | Official Site",
            " - Home",
            " - Tickets",
            " - 2024",
            " - 2025",
            " - 2026",
            " | Facebook",
            " | Instagram",
        ]

        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[: -len(suffix)].strip()

        # Must be reasonable length
        if len(name) < 5 or len(name) > 200:
            return None

        return name

    @circuit_breaker("exa", failure_threshold=5, recovery_timeout=30.0)
    async def get_page_content(self, url: str) -> Optional[str]:
        """Get full text content of a page."""
        try:
            # Use Exa's content endpoint
            payload = {
                "urls": [url],
                "text": True,
            }

            response = await self.client.post(
                f"{self.base_url}/contents",
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            if results:
                return results[0].get("text", "")

            return None

        except Exception as e:
            logger.error(f"Failed to get page content for {url}: {e}")
            return None
