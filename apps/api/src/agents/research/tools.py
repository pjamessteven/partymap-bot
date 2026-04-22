"""Tools for the research agent with progress streaming."""

import json
from datetime import datetime
from typing import Optional, Type, Any
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from src.services.browser_service import BrowserService
from src.services.llm_client import LLMClient
from src.services.exa_client import ExaClient
from src.partymap.client import PartyMapClient


class NavigateInput(BaseModel):
    url: str = Field(description="The URL to navigate to")


class NavigateTool(BaseTool):
    name: str = "navigate"
    description: str = "Navigate to a URL and load the page"
    args_schema: Type[BaseModel] = NavigateInput
    browser: Optional[BrowserService] = None
    writer: Optional[callable] = None

    def _run(self, url: str) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self, url: str) -> str:
        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": "navigate",
                "progress": 0.0,
                "message": f"Navigating to {url}..."
            })

        if not self.browser:
            return "Error: Browser not available"

        try:
            await self.browser.navigate(url)
            html = await self.browser.get_page_content()
            current_url = self.browser.page.url if self.browser.page else url
            title = await self.browser.get_page_title()

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "navigate",
                    "progress": 1.0,
                    "message": f"Loaded {current_url}",
                    "data": {"url": current_url, "title": title}
                })

            return f"Successfully navigated to {current_url}. Page content available."

        except Exception as e:
            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "navigate",
                    "progress": 1.0,
                    "message": f"Failed: {str(e)}"
                })
            return f"Navigation failed: {str(e)}"


class ClickLinkInput(BaseModel):
    link_text: str = Field(description="The text of the link to click (e.g., 'About', 'Lineup', 'Tickets')")


class ClickLinkTool(BaseTool):
    name: str = "click_link"
    description: str = "Click a link on the current page by its text"
    args_schema: Type[BaseModel] = ClickLinkInput
    browser: Optional[BrowserService] = None
    writer: Optional[callable] = None

    def _run(self, link_text: str) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self, link_text: str) -> str:
        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": "click_link",
                "progress": 0.0,
                "message": f"Looking for '{link_text}' link..."
            })

        if not self.browser:
            return "Error: Browser not available"

        try:
            clicked = await self.browser.click_link(link_text)

            if clicked:
                new_url = self.browser.page.url if self.browser.page else ""
                if self.writer:
                    await self.writer({
                        "type": "tool_progress",
                        "tool_name": "click_link",
                        "progress": 1.0,
                        "message": f"Clicked '{link_text}' link",
                        "data": {"new_url": new_url}
                    })
                return f"Successfully clicked '{link_text}'. Now on {new_url}"
            else:
                variations = ["About", "Info", "Lineup", "Tickets", "Details"]
                for text in variations:
                    if text.lower() != link_text.lower():
                        clicked = await self.browser.click_link(text)
                        if clicked:
                            new_url = self.browser.page.url if self.browser.page else ""
                            if self.writer:
                                await self.writer({
                                    "type": "tool_progress",
                                    "tool_name": "click_link",
                                    "progress": 1.0,
                                    "message": f"Clicked '{text}' link instead",
                                    "data": {"new_url": new_url}
                                })
                            return f"Could not find '{link_text}', but clicked '{text}' instead. Now on {new_url}"

                return f"Could not find any relevant links on the page."

        except Exception as e:
            return f"Failed to click link: {str(e)}"


class ExtractDataInput(BaseModel):
    fields_needed: Optional[list[str]] = Field(default=None, description="List of specific fields to extract")


class ExtractDataTool(BaseTool):
    """Extract structured festival data from page HTML."""

    name: str = "extract_data"
    description: str = "Extract structured data (name, dates, location, lineup) from current page"
    args_schema: Type[BaseModel] = ExtractDataInput
    browser: Optional[BrowserService] = None
    llm: Optional[LLMClient] = None
    writer: Optional[callable] = None
    cost_tracker: Optional[Any] = None

    def _run(self, fields_needed: Optional[list[str]] = None) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self, fields_needed: Optional[list[str]] = None) -> str:
        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": "extract_data",
                "progress": 0.0,
                "message": "Analyzing page content..."
            })

        if not self.browser or not self.llm:
            return "Error: Browser or LLM not available"

        try:
            html = await self.browser.get_page_content()
            url = self.browser.page.url if self.browser.page else ""

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "extract_data",
                    "progress": 0.3,
                    "message": "Extracting structured data..."
                })

            festival_data = await self.llm.extract_festival_data(html, url)
            
            # Track cost (estimated ~5 cents for extract_data)
            if self.cost_tracker:
                self.cost_tracker.track_tool_execution("extract_data", 5)

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "extract_data",
                    "progress": 0.7,
                    "message": "Processing extracted data..."
                })

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "extract_data",
                    "progress": 1.0,
                    "message": f"Extracted data for {festival_data.name or 'unknown festival'}",
                    "data": {
                        "name": festival_data.name,
                        "start_date": (
                            festival_data.event_dates[0].start.isoformat()
                            if festival_data.event_dates and festival_data.event_dates[0].start
                            else None
                        ),
                        "location": (
                            festival_data.event_dates[0].location_description
                            if festival_data.event_dates
                            else None
                        ),
                    }
                })

            return json.dumps(festival_data.model_dump(), default=str)

        except Exception as e:
            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "extract_data",
                "progress": 1.0,
                "message": f"Extraction failed: {str(e)}"
            })
            return f"Extraction failed: {str(e)}"


class ScreenshotLineupTool(BaseTool):
    """Take screenshot and extract lineup from image using LLM."""

    name: str = "screenshot_lineup"
    description: str = "Take a screenshot and use LLM vision to extract artist lineup"
    browser: Optional[BrowserService] = None
    llm: Optional[LLMClient] = None
    writer: Optional[callable] = None
    cost_tracker: Optional[Any] = None

    def _run(self) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self) -> str:
        import base64

        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": self.name,
                "progress": 0.0,
                "message": "Capturing screenshot..."
            })

        if not self.browser or not self.llm:
            return json.dumps({"error": "Browser or LLM not available"})

        try:
            screenshot_bytes = await self.browser.screenshot()

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": self.name,
                    "progress": 0.5,
                    "message": "Analyzing image for lineup..."
                })

            screenshot_base64 = base64.b64encode(screenshot_bytes).decode()
            artists = await self.llm.extract_lineup_from_image(screenshot_base64, "")

            # Track cost
            if self.cost_tracker:
                self.cost_tracker.track_tool_execution(self.name, 10)

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": self.name,
                    "progress": 1.0,
                    "message": f"Found {len(artists)} artists",
                    "data": {"artists": artists}
                })

            return json.dumps({"artists": artists})

        except Exception as e:
            error_msg = f"Screenshot extraction failed: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg})


class SearchAlternativesInput(BaseModel):
    query: str = Field(description="Search query to find alternative sources")


class SearchAlternativesTool(BaseTool):
    name: str = "search_alternatives"
    description: str = "Search for alternative sources using Exa API"
    args_schema: Type[BaseModel] = SearchAlternativesInput
    exa: Optional[ExaClient] = None
    writer: Optional[callable] = None

    def _run(self, query: str) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self, query: str) -> str:
        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": "search_alternatives",
                "progress": 0.0,
                "message": f"Searching: {query}"
            })

        if not self.exa:
            return "Error: Exa client not available"

        try:
            results = await self.exa.search(query, num_results=3)

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "search_alternatives",
                    "progress": 1.0,
                    "message": f"Found {len(results)} results",
                    "data": {"results": [{"url": r.url, "title": r.title} for r in results]}
                })

            if results:
                return json.dumps({
                    "results": [{"url": r.url, "title": r.title, "snippet": r.snippet} for r in results]
                })
            else:
                return "No alternative sources found."

        except Exception as e:
            return f"Search failed: {str(e)}"


# ==================== Enhanced Research Tools ====================


class PartyMapTagInput(BaseModel):
    festival_name: str = Field(description="Name of the festival")
    description: str = Field(description="Festival description for context")


class PartyMapTagTool(BaseTool):
    """Fetch popular tags from PartyMap and select up to 5 relevant ones."""

    name: str = "select_tags"
    description: str = """Select up to 5 most relevant tags for this festival from PartyMap's popular tags.
    Fetches the top 150 tags by popularity and uses AI to select the best matches."""
    args_schema: Type[BaseModel] = PartyMapTagInput
    partymap: Optional[PartyMapClient] = None
    llm: Optional[LLMClient] = None
    writer: Optional[callable] = None
    cost_tracker: Optional[Any] = None

    def _run(self, festival_name: str, description: str) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self, festival_name: str, description: str) -> str:
        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": "select_tags",
                "progress": 0.0,
                "message": f"Fetching popular tags for {festival_name}..."
            })

        if not self.partymap or not self.llm:
            return "Error: PartyMap or LLM client not available"

        try:
            # Fetch top 150 tags by count
            tags_response = await self.partymap.get_tags(
                sort="count",
                per_page=150,
                page=1,
                desc=True
            )

            if not tags_response or "items" not in tags_response:
                raise Exception("Tag API returned invalid response")

            available_tags = [t["tag"] for t in tags_response["items"]]

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "select_tags",
                    "progress": 0.5,
                    "message": f"Selecting best tags from {len(available_tags)} options..."
                })

            # Use LLM to select up to 5 most relevant tags
            selected = await self.llm.select_relevant_tags(
                festival_name=festival_name,
                description=description,
                available_tags=available_tags,
                max_tags=5
            )

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "select_tags",
                    "progress": 1.0,
                    "message": f"Selected {len(selected)} tags: {', '.join(selected)}",
                    "data": {"tags": selected}
                })

            return json.dumps({"tags": selected})

        except Exception as e:
            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "select_tags",
                    "progress": 1.0,
                    "message": f"Failed: {str(e)}"
                })
            raise  # Re-raise to signal error as requested


class YouTubeSearchInput(BaseModel):
    festival_name: str = Field(description="Name of the festival")
    year: Optional[int] = Field(default=None, description="Year to search for (defaults to current year)")


class YouTubeSearchTool(BaseTool):
    """Find official festival video/trailer or aftermovie on YouTube."""

    name: str = "search_youtube"
    description: str = """Search YouTube for official festival video.
    Tries current year trailer first, then aftermovie fallback."""
    args_schema: Type[BaseModel] = YouTubeSearchInput
    exa: Optional[ExaClient] = None
    writer: Optional[callable] = None

    def _run(self, festival_name: str, year: Optional[int] = None) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self, festival_name: str, year: Optional[int] = None) -> str:
        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": "search_youtube",
                "progress": 0.0,
                "message": f"Searching YouTube for {festival_name}..."
            })

        if not self.exa:
            return "Error: Exa client not available"

        try:
            current_year = year or datetime.now().year

            # Search strategy: current year trailer → current year video → aftermovie
            search_queries = [
                (f"{festival_name} {current_year} official trailer", "trailer"),
                (f"{festival_name} {current_year} official video", "video"),
                (f"{festival_name} official aftermovie", "aftermovie"),
                (f"{festival_name} aftermovie", "aftermovie"),
            ]

            for query, video_type in search_queries:
                if self.writer:
                    await self.writer({
                        "type": "tool_progress",
                        "tool_name": "search_youtube",
                        "progress": 0.3,
                        "message": f"Trying: {query}"
                    })

                results = await self.exa.search(
                    query=query,
                    num_results=3,
                    include_domains=["youtube.com", "youtu.be"]
                )

                if results:
                    best_match = results[0]

                    if self.writer:
                        await self.writer({
                            "type": "tool_progress",
                            "tool_name": "search_youtube",
                            "progress": 1.0,
                            "message": f"Found {video_type}: {best_match.title}",
                            "data": {
                                "youtube_url": best_match.url,
                                "video_type": video_type,
                                "title": best_match.title
                            }
                        })

                    return json.dumps({
                        "youtube_url": best_match.url,
                        "video_type": video_type,
                        "title": best_match.title
                    })

            # No results found
            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "search_youtube",
                    "progress": 1.0,
                    "message": "No YouTube video found"
                })

            return json.dumps({"youtube_url": None})

        except Exception as e:
            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "search_youtube",
                    "progress": 1.0,
                    "message": f"Search failed: {str(e)}"
                })
            return json.dumps({"youtube_url": None, "error": str(e)})


class MediaSelectionInput(BaseModel):
    festival_name: str = Field(description="Name of the festival")
    page_url: str = Field(description="URL of the page to analyze")


class MediaSelectionTool(BaseTool):
    """Intelligently select logo, gallery images, and lineup images from page."""

    name: str = "select_media"
    description: str = """Analyze page images and select the best:
    1. Logo/cover image (preferably squarish)
    2. Gallery photos (cool shots with attribution)
    3. Lineup images/posters"""
    args_schema: Type[BaseModel] = MediaSelectionInput
    browser: Optional[BrowserService] = None
    llm: Optional[LLMClient] = None
    writer: Optional[callable] = None

    def _run(self, festival_name: str, page_url: str) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self, festival_name: str, page_url: str) -> str:
        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": "select_media",
                "progress": 0.0,
                "message": f"Analyzing images on {page_url}..."
            })

        if not self.browser or not self.llm:
            return "Error: Browser or LLM not available"

        try:
            # Ensure we're on the right page
            current_url = self.browser.page.url if self.browser.page else ""
            if page_url not in current_url:
                await self.browser.navigate(page_url)

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "select_media",
                    "progress": 0.3,
                    "message": "Extracting image metadata..."
                })

            # Get all images from page
            images = await self.browser.find_images()

            if not images:
                if self.writer:
                    await self.writer({
                        "type": "tool_progress",
                        "tool_name": "select_media",
                        "progress": 1.0,
                        "message": "No images found on page"
                    })
                return json.dumps({"logo": None, "gallery": [], "lineup": []})

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "select_media",
                    "progress": 0.6,
                    "message": f"Classifying {len(images)} images..."
                })

            # Use LLM to classify and select best images
            selected = await self.llm.select_media(
                festival_name=festival_name,
                images=images,
                source_url=page_url
            )

            # Validate selected image URLs
            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "select_media",
                    "progress": 0.8,
                    "message": "Validating selected images..."
                })

            # Validate logo
            if selected.get("logo") and selected["logo"].get("url"):
                if not await self._validate_image_url(selected["logo"]["url"]):
                    logger.warning(f"Logo image validation failed: {selected['logo']['url']}")
                    selected["logo"] = None

            # Validate gallery images
            valid_gallery = []
            for item in selected.get("gallery", []):
                if item.get("url") and await self._validate_image_url(item["url"]):
                    valid_gallery.append(item)
                else:
                    logger.warning(f"Gallery image validation failed: {item.get('url')}")
            selected["gallery"] = valid_gallery

            # Validate lineup images
            valid_lineup = []
            for url in selected.get("lineup", []):
                if await self._validate_image_url(url):
                    valid_lineup.append(url)
                else:
                    logger.warning(f"Lineup image validation failed: {url}")
            selected["lineup"] = valid_lineup

            # Add source URL to all captions
            if selected.get("logo"):
                selected["logo"]["caption"] = f"Logo from {page_url}"

            for item in selected.get("gallery", []):
                item["caption"] = f"Photo from {page_url}"

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "select_media",
                    "progress": 1.0,
                    "message": f"Selected logo + {len(selected.get('gallery', []))} gallery + {len(selected.get('lineup', []))} lineup images",
                    "data": {
                        "logo_url": selected.get("logo", {}).get("url") if selected.get("logo") else None,
                        "gallery_count": len(selected.get("gallery", [])),
                        "lineup_count": len(selected.get("lineup", []))
                    }
                })

            return json.dumps(selected)

        except Exception as e:
            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "select_media",
                    "progress": 1.0,
                    "message": f"Failed: {str(e)}"
                })
            return json.dumps({"logo": None, "gallery": [], "lineup": [], "error": str(e)})

    async def _validate_image_url(self, url: str) -> bool:
        """
        Validate that an image URL is accessible and meets requirements.
        
        Checks:
        - URL is accessible (200 status)
        - Content type is image/*
        - File size is reasonable (< 10MB)
        - Minimum dimensions (if available in headers)
        
        Args:
            url: Image URL to validate
            
        Returns:
            True if valid, False otherwise
        """
        import httpx
        
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                # Use HEAD request first (lighter)
                try:
                    response = await client.head(url)
                except Exception:
                    # Fallback to GET if HEAD fails
                    response = await client.get(url)
                
                # Check status code
                if response.status_code != 200:
                    logger.debug(f"Image validation failed - status {response.status_code}: {url}")
                    return False
                
                # Check content type
                content_type = response.headers.get("content-type", "").lower()
                if not content_type.startswith("image/"):
                    logger.debug(f"Image validation failed - not an image ({content_type}): {url}")
                    return False
                
                # Check file size (avoid huge images)
                content_length = response.headers.get("content-length")
                if content_length:
                    size_bytes = int(content_length)
                    if size_bytes > 10 * 1024 * 1024:  # 10MB max
                        logger.debug(f"Image validation failed - too large ({size_bytes} bytes): {url}")
                        return False
                    if size_bytes < 1000:  # Less than 1KB is probably an icon/tracking pixel
                        logger.debug(f"Image validation failed - too small ({size_bytes} bytes): {url}")
                        return False
                
                return True
                
        except httpx.TimeoutException:
            logger.debug(f"Image validation failed - timeout: {url}")
            return False
        except Exception as e:
            logger.debug(f"Image validation failed - error: {e}: {url}")
            return False


class TicketExtractionTool(BaseTool):
    """Extract ticket information with pricing from ticket page."""

    name: str = "extract_tickets"
    description: str = "Extract ticket types, prices, and currency from the current page (JSON-LD or HTML analysis)"
    browser: Optional[BrowserService] = None
    llm: Optional[LLMClient] = None
    writer: Optional[callable] = None

    def _run(self) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self) -> str:
        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": "extract_tickets",
                "progress": 0.0,
                "message": "Analyzing page for ticket information..."
            })

        if not self.browser or not self.llm:
            return "Error: Browser or LLM not available"

        try:
            html = await self.browser.get_page_content()

            # Method 1: Try JSON-LD structured data
            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "extract_tickets",
                    "progress": 0.3,
                    "message": "Checking for structured data..."
                })

            tickets = await self._extract_jsonld_tickets(html)

            # Method 2: Fallback to LLM extraction
            if not tickets:
                if self.writer:
                    await self.writer({
                        "type": "tool_progress",
                        "tool_name": "extract_tickets",
                        "progress": 0.6,
                        "message": "Extracting from page content..."
                    })

                tickets = await self.llm.extract_tickets(html)

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "extract_tickets",
                    "progress": 1.0,
                    "message": f"Found {len(tickets)} ticket types",
                    "data": {"tickets": tickets}
                })

            return json.dumps({"tickets": tickets})

        except Exception as e:
            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "extract_tickets",
                    "progress": 1.0,
                    "message": f"Extraction failed: {str(e)}"
                })
            return json.dumps({"tickets": [], "error": str(e)})

    async def _extract_jsonld_tickets(self, html: str) -> list:
        """Extract tickets from JSON-LD Offers if present."""
        import re

        tickets = []

        # Find JSON-LD scripts
        jsonld_pattern = r'<script type="application/ld\+json">(.*?)</script>'
        matches = re.findall(jsonld_pattern, html, re.DOTALL)

        for match in matches:
            try:
                data = json.loads(match)

                # Handle single Offer
                if isinstance(data, dict) and data.get("@type") == "Offer":
                    ticket = self._parse_offer(data)
                    if ticket:
                        tickets.append(ticket)

                # Handle array of Offers
                elif isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "Offer":
                            ticket = self._parse_offer(item)
                            if ticket:
                                tickets.append(ticket)

            except json.JSONDecodeError:
                continue

        return tickets

    def _parse_offer(self, offer: dict) -> Optional[dict]:
        """Parse a JSON-LD Offer into ticket format."""
        price = offer.get("price")
        currency = offer.get("priceCurrency")

        if not price:
            return None

        return {
            "description": offer.get("name", offer.get("description", "Ticket")),
            "price_min": float(price) if price else None,
            "price_max": float(price) if price else None,
            "price_currency_code": currency,
            "url": offer.get("url")
        }
