"""Graph nodes for research agent."""

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

from src.agents.research.state import ResearchState
from src.agents.research.tools import (
    ExtractDataTool,
    MediaSelectionTool,
    PartyMapTagTool,
    ScreenshotLineupTool,
    SearchAlternativesTool,
    TicketExtractionTool,
    YouTubeSearchTool,
)
from src.agents.shared.playwright_toolkit import create_playwright_tools_with_existing_browser

PLANNER_SYSTEM_PROMPT_NEW = """You are a festival research assistant. Your job is to gather comprehensive information about a NEW festival.

This is a NEW festival that doesn't exist in PartyMap yet. You need to collect complete information.

Available tools:
- navigate: Go to a specific URL
- extract_data: Extract structured festival data from current page
- click_link: Click a link to find more information (About, Lineup, Tickets, etc.)
- screenshot: Take screenshot and extract lineup from image
- search_alternatives: Search for alternative sources via Exa
- select_tags: Fetch PartyMap's popular tags and select up to 5 relevant ones
- search_youtube: Find official trailer/aftermovie on YouTube
- select_media: Intelligently select logo, gallery photos, and lineup images
- extract_tickets: Extract ticket pricing from ticket page

Your strategy:
1. Navigate to the main festival URL
2. extract_data to get basic info (name, dates, location, description)
3. PARALLEL operations:
   - select_tags: Get relevant tags from PartyMap's top 150
   - search_youtube: Find official video/trailer
   - select_media: Choose best logo and gallery images
4. If needed, click_link("Lineup") or screenshot for lineup
5. If tickets link exists, click_link("Tickets") then extract_tickets

Required fields to collect:
- name: Festival name
- start: Start date (ISO format)
- location: Location description

Enhanced fields:
- full_description, youtube_url, tags, logo_url, media_items, lineup_images, size, tickets, is_recurring

Be thorough - this is a NEW festival and needs complete data."""

PLANNER_SYSTEM_PROMPT_UPDATE = """You are a festival research assistant. Your job is to research UPDATES for an existing PartyMap festival.

This festival ALREADY EXISTS in PartyMap. You need to gather UPDATED information based on specific update reasons.

Update reasons tell you what needs updating:
- "missing_dates" - PartyMap has no future dates for this event
- "dates_unconfirmed" - Dates exist but need confirmation
- "location_change" - Location has changed significantly
- "lineup_released" - New lineup information available
- "event_cancelled" - Event was cancelled
- "description_update" - Description can be improved
- "media_update" - New images/media available
- "url_update" - Website URL changed

Available tools:
- navigate: Go to a specific URL
- extract_data: Extract structured festival data from current page
- click_link: Click a link to find more information
- screenshot: Take screenshot and extract lineup from image
- search_alternatives: Search for alternative sources via Exa
- select_tags: Fetch PartyMap's popular tags
- search_youtube: Find official video/trailer
- select_media: Select logo and gallery images
- extract_tickets: Extract ticket pricing

Your strategy:
1. Navigate to the main festival URL
2. Focus on the UPDATE REASONS - what specifically needs updating?
3. If "missing_dates" or "dates_unconfirmed": Prioritize extracting date information
4. If "location_change": Prioritize location information
5. If "lineup_released": Extract lineup information
6. Always collect enhanced data (tags, media, youtube) if available

Required fields:
- name, start, location (verify these match existing event)

Focus on what's CHANGED or MISSING compared to the existing PartyMap event."""


async def get_tools(browser, llm, exa, partymap, writer, config_settings=None, cost_tracker=None):
    """Create tool instances with dependencies using PlayWrightBrowserToolkit."""
    from src.agents.research.tools_lineup import LineupExtractionTool

    # Get clients from config if available
    musicbrainz = config_settings.get("musicbrainz") if config_settings else None
    vision = config_settings.get("vision") if config_settings else None

    tools = []

    # Create Playwright browser tools from toolkit
    try:
        # Get the underlying playwright browser from our BrowserService
        if browser.page and hasattr(browser.page, 'context'):
            playwright_browser = browser.page.context.browser
            playwright_tools = await create_playwright_tools_with_existing_browser(playwright_browser)
            tools.extend(playwright_tools)
            logger.info(f"Added {len(playwright_tools)} Playwright toolkit tools")
    except Exception as e:
        logger.error(f"Could not create Playwright toolkit tools: {e}")
        raise  # Serious issue if Playwright fails

    # Create research-specific tools
    research_tools = [
        ExtractDataTool(browser=browser, llm=llm, writer=writer, cost_tracker=cost_tracker),
        ScreenshotLineupTool(browser=browser, llm=llm, writer=writer, cost_tracker=cost_tracker),
        SearchAlternativesTool(exa=exa, writer=writer, cost_tracker=cost_tracker),
        PartyMapTagTool(partymap=partymap, llm=llm, writer=writer, cost_tracker=cost_tracker),
        YouTubeSearchTool(exa=exa, writer=writer),
        MediaSelectionTool(browser=browser, llm=llm, writer=writer, cost_tracker=cost_tracker),
        TicketExtractionTool(browser=browser, llm=llm, writer=writer, cost_tracker=cost_tracker),
    ]
    tools.extend(research_tools)

    # Add lineup extraction tool if vision and MusicBrainz clients are available
    if vision and musicbrainz:
        tools.append(LineupExtractionTool(
            vision=vision,  # GPT-4o-mini for image description
            llm=llm,  # DeepSeek for text extraction
            musicbrainz=musicbrainz,
            writer=writer,
            cost_tracker=cost_tracker
        ))

    return tools


async def planner_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Decide next action based on current state.
    This node uses the LLM to decide which tool to call next.
    """
    # Format the current state for the LLM
    missing = state.missing_fields or []

    prompt = f"""
Current collected data:
{json.dumps(state.collected_data, indent=2, default=str)}

Missing fields: {", ".join(missing) if missing else "None - all collected!"}

Current URL: {state.current_url or "None"}
Visited URLs: {state.visited_urls}
Iteration: {state.iteration + 1}/{state.max_iterations}

Based on what's missing and the current state, what should be the next action?
"""

    # Select system prompt based on workflow type
    system_prompt = (
        PLANNER_SYSTEM_PROMPT_UPDATE
        if state.workflow_type == "update"
        else PLANNER_SYSTEM_PROMPT_NEW
    )

    messages = [
        SystemMessage(content=system_prompt),
        *state.messages,
        HumanMessage(content=prompt),
    ]

    # Get tools (now async)
    tools = await get_tools(
        config.get("browser"),
        config.get("llm"),
        config.get("exa"),
        config.get("partymap"),
        config.get("writer"),
        config.get("settings")
    )

    # Bind tools to the model
    settings = config.get("settings")
    model = ChatOpenAI(
        model="deepseek/deepseek-chat",
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key if settings else None,
        temperature=0.1,
    ).bind_tools(tools)

    # Get response with tool calls
    response = await model.ainvoke(messages)

    # Emit reasoning if content is present
    writer = config.get("writer")
    if writer and response.content:
        await writer(
            {
                "type": "reasoning",
                "thought": response.content,
                "iteration": state.iteration + 1,
                "missing_fields": missing,
            }
        )

    return {
        "messages": [response],
        "iteration": state.iteration + 1,
    }


async def tools_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Execute tools. This node runs the tools selected by the planner.
    Includes budget checking and cost tracking.
    """
    from src.agents.research.cost_tracker import CostTracker

    last_message = state.messages[-1] if state.messages else None

    if not last_message or not last_message.tool_calls:
        return {}

    # Check budget before executing tools
    cost_tracker = CostTracker.from_dict({
        "budget_cents": state.budget_cents,
        "per_tool": state.cost_tracker.get("per_tool", {}),
        "total_cents": state.total_cost_cents,
        "is_exceeded": state.budget_exceeded
    })

    if cost_tracker.is_exceeded:
        writer = config.get("writer")
        if writer:
            await writer({
                "type": "budget_exceeded",
                "message": f"Budget exceeded: {state.total_cost_cents}c / {state.budget_cents}c",
                "total_cost": state.total_cost_cents,
                "budget": state.budget_cents
            })

        return {
            "error": f"Budget exceeded: {state.total_cost_cents}c / {state.budget_cents}c",
            "budget_exceeded": True,
            "final_result": state.collected_data  # Return what we have
        }

    # Get tools (now async)
    tools = await get_tools(
        config.get("browser"),
        config.get("llm"),
        config.get("exa"),
        config.get("partymap"),
        config.get("writer"),
        config.get("settings"),
        cost_tracker
    )
    tools_by_name = {t.name: t for t in tools}

    # Execute each tool
    tool_results = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_call_id = tool_call["id"]

        tool = tools_by_name.get(tool_name)
        if not tool:
            result = f"Unknown tool: {tool_name}"
        else:
            try:
                # Check if we can afford this tool
                estimated_cost = 5 if tool_name in ["extract_data", "select_tags", "select_media"] else 10
                if not cost_tracker.can_afford(estimated_cost):
                    result = json.dumps({
                        "error": f"Insufficient budget for {tool_name}",
                        "budget_exceeded": True
                    })
                else:
                    result = await tool.ainvoke(tool_args)

                    # Track Exa search costs
                    if tool_name == "search_alternatives":
                        cost_tracker.track_exa_search(tool_name)

            except Exception as e:
                result = f"Tool execution failed: {str(e)}"

        tool_results.append(
            ToolMessage(content=result, tool_call_id=tool_call_id, name=tool_name)
        )

    # Update cost state
    cost_report = cost_tracker.get_report()

    return {
        "messages": tool_results,
        "cost_tracker": cost_report.get("per_tool", {}),
        "total_cost_cents": cost_report.get("total_cents", 0),
        "budget_exceeded": cost_tracker.is_exceeded
    }


async def evaluator_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Evaluate if we have enough data to complete.
    Parses results from all tools including enhanced tools.
    """
    # Parse collected data from tool results
    collected = state.collected_data.copy()

    # Check tool results for new data
    for msg in state.messages:
        if isinstance(msg, ToolMessage):
            try:
                data = json.loads(msg.content)

                if msg.name == "extract_data":
                    # Merge extracted festival data
                    collected.update(data)
                elif msg.name == "select_tags":
                    # Store selected tags
                    collected["tags"] = data.get("tags", [])
                elif msg.name == "search_youtube":
                    # Store YouTube URL
                    if data.get("youtube_url"):
                        collected["youtube_url"] = data["youtube_url"]
                elif msg.name == "select_media":
                    # Store media selections
                    if data.get("logo"):
                        collected["logo"] = data["logo"]
                    if data.get("gallery"):
                        collected["media_items"] = data["gallery"]
                    if data.get("lineup"):
                        collected["lineup_images"] = data["lineup"]
                elif msg.name == "extract_tickets":
                    # Store ticket information
                    if data.get("tickets"):
                        collected["tickets"] = data["tickets"]
                elif msg.name == "screenshot":
                    # Store lineup from screenshot
                    if data.get("artists"):
                        existing = collected.get("lineup", [])
                        collected["lineup"] = list(set(existing + data["artists"]))
            except Exception:
                pass  # Skip invalid JSON

    # Determine missing fields (required)
    missing = []
    if not collected.get("name"):
        missing.append("name")
    if not collected.get("start") and not any(
        ed.get("start") for ed in collected.get("event_dates", [])
    ):
        missing.append("start date")
    if not collected.get("location") and not any(
        ed.get("location_description") for ed in collected.get("event_dates", [])
    ):
        missing.append("location")

    # Enhanced optional fields
    enhanced_missing = []
    if not collected.get("tags"):
        enhanced_missing.append("tags")
    if not collected.get("youtube_url"):
        enhanced_missing.append("youtube_url")
    if not collected.get("logo"):
        enhanced_missing.append("logo")
    if not collected.get("full_description"):
        enhanced_missing.append("full_description")
    if not collected.get("media_items"):
        enhanced_missing.append("media_items")

    # Standard optional fields
    if not collected.get("end"):
        missing.append("end date (optional)")
    if not collected.get("description"):
        missing.append("description (optional)")

    # Check if we have minimum required
    has_minimum = bool(
        collected.get("name")
        and (
            collected.get("start")
            or any(ed.get("start") for ed in collected.get("event_dates", []))
        )
        and (
            collected.get("location")
            or any(ed.get("location_description") for ed in collected.get("event_dates", []))
        )
    )

    # Emit evaluation
    writer = config.get("writer")
    if writer:
        await writer(
            {
                "type": "evaluation",
                "has_minimum_required": has_minimum,
                "missing_fields": missing,
                "enhanced_fields_pending": enhanced_missing,
                "collected_data_summary": {
                    "name": collected.get("name"),
                    "start": collected.get("start"),
                    "location": collected.get("location"),
                    "has_tags": bool(collected.get("tags")),
                    "has_youtube": bool(collected.get("youtube_url")),
                    "has_logo": bool(collected.get("logo")),
                    "has_media": bool(collected.get("media_items")),
                },
            }
        )

    if has_minimum and (not missing or all("(optional)" in m for m in missing)):
        # We have enough data - build final result
        from dateutil import parser

        from src.core.schemas import EventDateData, FestivalData, MediaItem, RRuleData

        event_dates = []
        if collected.get("event_dates"):
            for ed in collected["event_dates"]:
                event_dates.append(EventDateData(**ed))
        else:
            # Build from flat fields
            start = None
            end = None
            if collected.get("start"):
                try:
                    start = parser.parse(collected["start"])
                except (ValueError, TypeError):
                    pass
            if collected.get("end"):
                try:
                    end = parser.parse(collected["end"])
                except (ValueError, TypeError):
                    pass

            # Build EventDateData with enhanced fields
            event_date_data = EventDateData(
                start=start,
                end=end,
                location_description=collected.get("location", ""),
                lineup=collected.get("lineup", []),
                size=collected.get("size"),
                lineup_images=collected.get("lineup_images", []),
            )

            # Add tickets if extracted
            if collected.get("tickets"):
                from src.core.schemas import TicketInfo
                tickets = []
                for t in collected["tickets"]:
                    tickets.append(TicketInfo(
                        url=t.get("url"),
                        description=t.get("description"),
                        price_min=t.get("price_min"),
                        price_max=t.get("price_max"),
                        price_currency_code=t.get("price_currency_code")
                    ))
                event_date_data.tickets = tickets

            event_dates.append(event_date_data)

        # Build media_items from gallery
        media_items = []
        if collected.get("media_items"):
            for item in collected["media_items"]:
                if isinstance(item, dict) and item.get("url"):
                    media_items.append(MediaItem(
                        url=item["url"],
                        caption=item.get("caption"),
                        media_type=item.get("media_type", "gallery")
                    ))

        # Build logo from selection
        logo_url = None
        if collected.get("logo"):
            logo = collected["logo"]
            if isinstance(logo, dict) and logo.get("url"):
                logo_url = logo["url"]

        # Build RRULE if recurring detected
        rrule = None
        is_recurring = collected.get("is_recurring", False)
        if is_recurring:
            rrule = RRuleData(recurringType=3)  # Default to yearly

        final_result = FestivalData(
            name=collected.get("name", ""),
            description=collected.get("description"),
            full_description=collected.get("full_description"),
            website_url=collected.get("website_url") or state.current_url,
            youtube_url=collected.get("youtube_url"),
            logo_url=logo_url,
            media_items=media_items,
            tags=collected.get("tags", []),
            is_recurring=is_recurring,
            rrule=rrule,
            event_dates=event_dates,
            source="research_agent",
            source_url=state.source_url,
        )

        # Include workflow information for pipeline
        workflow_info = {
            "workflow_type": state.workflow_type,
            "partymap_event_id": state.partymap_event_id,
            "update_reasons": state.update_reasons,
        }

        if writer:
            workflow_msg = "update" if state.workflow_type == "update" else "new festival"
            await writer(
                {
                    "type": "complete",
                    "message": f"Research complete for {workflow_msg}! Enhanced with {len(final_result.tags)} tags, logo, and media.",
                    "workflow_type": state.workflow_type,
                }
            )

        return {
            "final_result": final_result.model_dump(),
            "collected_data": collected,
            "missing_fields": [],
            "workflow_info": workflow_info,
        }

    # Not complete - continue
    return {"collected_data": collected, "missing_fields": missing}
