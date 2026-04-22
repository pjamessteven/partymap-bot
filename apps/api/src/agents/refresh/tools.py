"""Tools for the refresh agent."""

import json
from typing import Any, Optional
from langchain.tools import BaseTool
from pydantic import BaseModel, Field


class SearchFestivalInput(BaseModel):
    query: str = Field(description="Search query for finding festival information")


class SearchFestivalTool(BaseTool):
    """Search for festival information using Exa."""

    name: str = "search_festival"
    description: str = "Search the web for current festival information"
    args_schema: type[BaseModel] = SearchFestivalInput
    exa: Optional[Any] = None
    writer: Optional[callable] = None

    def _run(self, query: str) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self, query: str) -> str:
        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": "search_festival",
                "progress": 0.0,
                "message": f"Searching for: {query}"
            })

        if not self.exa:
            return json.dumps({"error": "Exa client not available"})

        try:
            # Search with Exa
            results = await self.exa.search(
                query=query,
                num_results=5,
            )

            # Format results
            formatted = []
            for r in results:
                formatted.append({
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                })

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "search_festival",
                    "progress": 1.0,
                    "message": f"Found {len(formatted)} results",
                    "data": {"count": len(formatted)}
                })

            return json.dumps({
                "query": query,
                "results": formatted,
            })

        except Exception as e:
            return json.dumps({"error": str(e)})


class VisitWebsiteInput(BaseModel):
    url: str = Field(description="URL to visit")


class VisitWebsiteTool(BaseTool):
    """Visit a website and extract information."""

    name: str = "visit_website"
    description: str = "Visit a festival website and extract information"
    args_schema: type[BaseModel] = VisitWebsiteInput
    browser: Optional[Any] = None
    llm: Optional[Any] = None
    writer: Optional[callable] = None

    def _run(self, url: str) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self, url: str) -> str:
        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": "visit_website",
                "progress": 0.0,
                "message": f"Visiting: {url}"
            })

        if not self.browser or not self.llm:
            return json.dumps({"error": "Browser or LLM not available"})

        try:
            # Navigate and get content
            await self.browser.navigate(url)
            html = await self.browser.get_page_content()

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "visit_website",
                    "progress": 0.5,
                    "message": "Extracting information..."
                })

            # Extract festival data
            festival_data = await self.llm.extract_festival_data(html, url)

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "visit_website",
                    "progress": 1.0,
                    "message": f"Extracted data for {festival_data.name or 'unknown'}",
                    "data": {"name": festival_data.name}
                })

            return json.dumps(festival_data.model_dump(), default=str)

        except Exception as e:
            return json.dumps({"error": str(e)})


class ExtractLineupInput(BaseModel):
    url: Optional[str] = Field(default=None, description="URL to extract lineup from (optional)")


class ExtractLineupTool(BaseTool):
    """Extract lineup/artist list from website or image."""

    name: str = "extract_lineup"
    description: str = "Extract festival lineup from website or screenshot"
    args_schema: type[BaseModel] = ExtractLineupInput
    browser: Optional[Any] = None
    llm: Optional[Any] = None
    writer: Optional[callable] = None

    def _run(self, url: Optional[str] = None) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self, url: Optional[str] = None) -> str:
        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": "extract_lineup",
                "progress": 0.0,
                "message": "Looking for lineup information..."
            })

        if not self.browser or not self.llm:
            return json.dumps({"error": "Browser or LLM not available"})

        try:
            # Try to find lineup page
            if url:
                await self.browser.navigate(url)

            # Click "Lineup" link if exists
            clicked = await self.browser.click_link("Lineup")
            if not clicked:
                clicked = await self.browser.click_link("Artists")

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "extract_lineup",
                    "progress": 0.3,
                    "message": "Extracting artist list..."
                })

            # Get HTML and extract
            html = await self.browser.get_page_content()
            festival_data = await self.llm.extract_festival_data(html, self.browser.page.url)

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "extract_lineup",
                    "progress": 1.0,
                    "message": f"Found {len(festival_data.event_dates[0].lineup) if festival_data.event_dates else 0} artists",
                    "data": {"artist_count": len(festival_data.event_dates[0].lineup) if festival_data.event_dates else 0}
                })

            return json.dumps({
                "artists": festival_data.event_dates[0].lineup if festival_data.event_dates else [],
            })

        except Exception as e:
            return json.dumps({"error": str(e)})


class VerifyDateInput(BaseModel):
    current_date: str = Field(description="Current date from PartyMap (ISO format)")
    website_url: str = Field(description="Festival website URL to verify")


class VerifyDateTool(BaseTool):
    """Verify if the current date is correct."""

    name: str = "verify_date"
    description: str = "Verify festival dates against official website"
    args_schema: type[BaseModel] = VerifyDateInput
    browser: Optional[Any] = None
    llm: Optional[Any] = None
    writer: Optional[callable] = None

    def _run(self, current_date: str, website_url: str) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self, current_date: str, website_url: str) -> str:
        if self.writer:
            await self.writer({
                "type": "tool_progress",
                "tool_name": "verify_date",
                "progress": 0.0,
                "message": f"Verifying date: {current_date}"
            })

        if not self.browser or not self.llm:
            return json.dumps({"error": "Browser or LLM not available"})

        try:
            await self.browser.navigate(website_url)
            html = await self.browser.get_page_content()

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "verify_date",
                    "progress": 0.5,
                    "message": "Checking dates..."
                })

            festival_data = await self.llm.extract_festival_data(html, website_url)

            # Compare dates
            from dateutil import parser
            current = parser.parse(current_date)
            found = festival_data.event_dates[0].start if festival_data.event_dates else None

            date_correct = False
            if found:
                date_correct = (current.date() == found.date())

            if self.writer:
                await self.writer({
                    "type": "tool_progress",
                    "tool_name": "verify_date",
                    "progress": 1.0,
                    "message": f"Date {'verified' if date_correct else 'DIFFERENT'}",
                    "data": {
                        "current": current_date,
                        "found": found.isoformat() if found else None,
                        "correct": date_correct,
                    }
                })

            return json.dumps({
                "current_date": current_date,
                "found_date": found.isoformat() if found else None,
                "date_correct": date_correct,
                "confidence": 0.95 if date_correct else 0.7,
            })

        except Exception as e:
            return json.dumps({"error": str(e)})
