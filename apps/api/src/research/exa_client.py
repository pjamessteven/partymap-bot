"""Exa API integration for festival search."""

import logging
from typing import List, Optional

import httpx
from pydantic import BaseModel

from src.config import Settings

logger = logging.getLogger(__name__)


class ExaSearchResult(BaseModel):
    """Single search result from Exa."""

    title: str
    url: str
    published_date: Optional[str] = None
    author: Optional[str] = None
    summary: Optional[str] = None
    score: Optional[float] = None


class ExaClient:
    """Client for Exa search API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url="https://api.exa.ai",
            headers={
                "x-api-key": settings.exa_api_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def search_festivals(
        self,
        query: str,
        num_results: int = 10,
        start_published_date: Optional[str] = None,
        end_published_date: Optional[str] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
    ) -> List[ExaSearchResult]:
        """
        Search for music festivals.

        Args:
            query: Search query (e.g., "music festival 2026 Europe")
            num_results: Number of results to return (max 100)
            start_published_date: Filter by start date (ISO 8601)
            end_published_date: Filter by end date (ISO 8601)
            include_domains: Only search these domains
            exclude_domains: Exclude these domains

        Returns:
            List of search results
        """
        try:
            payload = {
                "query": query,
                "numResults": min(num_results, 100),
                "type": "auto",  # Exa decides between neural and keyword
                "useAutoprompt": True,  # Let Exa optimize the query
                "contents": {
                    "text": True,
                    "summary": {"query": "music festival details lineup dates location"},
                },
            }

            # Add optional filters
            if start_published_date:
                payload["start_published_date"] = start_published_date
            if end_published_date:
                payload["end_published_date"] = end_published_date
            if include_domains:
                payload["includeDomains"] = include_domains
            if exclude_domains:
                payload["excludeDomains"] = exclude_domains

            response = await self.client.post("/search", json=payload)
            response.raise_for_status()

            data = response.json()
            results = []

            for result in data.get("results", []):
                try:
                    # Extract summary if available
                    summary = None
                    if "summary" in result:
                        summary = result["summary"]
                    elif "text" in result:
                        summary = result["text"][:500]  # First 500 chars

                    search_result = ExaSearchResult(
                        title=result.get("title", "Untitled"),
                        url=result.get("url", ""),
                        published_date=result.get("published_date"),
                        author=result.get("author"),
                        summary=summary,
                        score=result.get("score"),
                    )
                    results.append(search_result)
                except Exception as e:
                    logger.warning(f"Failed to parse search result: {e}")
                    continue

            logger.info(f"Exa search returned {len(results)} results for query: {query}")
            return results

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during Exa search: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error during Exa search: {e}")
            return []

    async def search_by_url(self, url: str) -> Optional[ExaSearchResult]:
        """Get information about a specific URL."""
        try:
            response = await self.client.post(
                "/search",
                json={
                    "query": url,
                    "numResults": 1,
                    "includeDomains": [url.split("/")[2]],  # Extract domain
                    "contents": {"text": True},
                },
            )
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            if results:
                result = results[0]
                return ExaSearchResult(
                    title=result.get("title", "Untitled"),
                    url=result.get("url", url),
                    published_date=result.get("published_date"),
                    author=result.get("author"),
                    summary=result.get("text", "")[:500],
                    score=result.get("score"),
                )

            return None

        except Exception as e:
            logger.error(f"Failed to search by URL: {e}")
            return None

    async def find_similar(self, url: str, num_results: int = 5) -> List[ExaSearchResult]:
        """Find similar pages to a given URL."""
        try:
            response = await self.client.post(
                "/findSimilar",
                json={
                    "url": url,
                    "numResults": num_results,
                    "contents": {"text": True, "summary": True},
                },
            )
            response.raise_for_status()

            data = response.json()
            results = []

            for result in data.get("results", []):
                try:
                    search_result = ExaSearchResult(
                        title=result.get("title", "Untitled"),
                        url=result.get("url", ""),
                        published_date=result.get("published_date"),
                        author=result.get("author"),
                        summary=result.get("summary") or result.get("text", "")[:500],
                        score=result.get("score"),
                    )
                    results.append(search_result)
                except Exception as e:
                    logger.warning(f"Failed to parse similar result: {e}")
                    continue

            return results

        except Exception as e:
            logger.error(f"Failed to find similar pages: {e}")
            return []

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
