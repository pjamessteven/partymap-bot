"""Graph nodes for refresh agent."""

import json
from datetime import datetime
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from src.agents.refresh.state import RefreshState
from src.agents.refresh.tools import (
    SearchFestivalTool,
    VisitWebsiteTool,
    ExtractLineupTool,
    VerifyDateTool,
)


REFRESH_SYSTEM_PROMPT = """You are a festival data refresh assistant. Your job is to verify and improve existing PartyMap event data.

You have access to these tools:
- search_festival: Search the web for current festival information
- visit_website: Visit a festival website and extract structured data
- extract_lineup: Extract artist lineup from a website
- verify_date: Verify if the current date is correct

WORKFLOW:
1. First, search for the festival to find official sources
2. Visit the official website to get current data
3. Verify the date is correct
4. Look for lineup information if missing
5. Check for ticket information

IMPORTANT:
- Compare what you find with the CURRENT data provided
- Only propose changes if you find BETTER or DIFFERENT information
- If the current data looks accurate, confirm it's correct
- Be thorough - check lineup pages, about pages, ticket pages
- Note your confidence level for each change"""


def get_tools(browser, exa, llm, writer):
    """Create tool instances with dependencies."""
    return [
        SearchFestivalTool(exa=exa, writer=writer),
        VisitWebsiteTool(browser=browser, llm=llm, writer=writer),
        ExtractLineupTool(browser=browser, llm=llm, writer=writer),
        VerifyDateTool(browser=browser, llm=llm, writer=writer),
    ]


async def search_node(state: RefreshState, config: RunnableConfig) -> dict:
    """
    Search for festival information.
    This is always the first step.
    """
    settings = config.get("settings")

    # Build search query
    event_name = state.event_name
    current_start = state.current_event_date.get("start", "")
    year = ""
    if current_start:
        try:
            year = str(datetime.fromisoformat(current_start.replace("Z", "+00:00")).year)
        except (ValueError, TypeError):
            pass

    search_query = f"{event_name} {year} festival official website dates".strip()

    writer = config.get("writer")
    if writer:
        await writer({
            "type": "reasoning",
            "thought": f"Starting refresh for {event_name}. Searching with query: {search_query}",
        })

    # Use LLM to decide next steps
    model = ChatOpenAI(
        model="deepseek/deepseek-chat",
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key if settings else None,
        temperature=0.1,
    ).bind_tools([SearchFestivalTool(exa=config.get("exa"), writer=writer)])

    messages = [
        SystemMessage(content=REFRESH_SYSTEM_PROMPT),
        HumanMessage(content=f"""
Search for current information about: {event_name}

Current data from PartyMap:
- Event: {json.dumps(state.current_event_data, indent=2, default=str)}
- EventDate: {json.dumps(state.current_event_date, indent=2, default=str)}

Search query: {search_query}

Use the search_festival tool to find official sources.
""")
    ]

    response = await model.ainvoke(messages)

    return {
        "messages": [response],
        "search_query": search_query,
        "iteration": state.iteration + 1,
    }


async def research_node(state: RefreshState, config: RunnableConfig) -> dict:
    """
    Visit websites and gather detailed information.
    """
    settings = config.get("settings")
    writer = config.get("writer")

    # Get search results from previous step
    search_results = []
    for msg in state.messages:
        if isinstance(msg, ToolMessage) and msg.name == "search_festival":
            try:
                data = json.loads(msg.content)
                search_results = data.get("results", [])
            except (json.JSONDecodeError, TypeError):
                pass

    if not search_results:
        return {"error": "No search results found"}

    # Find official website (prefer non-social media)
    official_url = None
    for result in search_results:
        url = result.get("url", "").lower()
        if any(x in url for x in ["facebook.com", "instagram.com", "twitter.com", "x.com"]):
            continue
        official_url = result.get("url")
        break

    if not official_url:
        official_url = search_results[0].get("url")

    if writer:
        await writer({
            "type": "reasoning",
            "thought": f"Found official website: {official_url}. Visiting to extract current data.",
        })

    # Visit website and extract data
    tools = get_tools(
        config.get("browser"),
        config.get("exa"),
        config.get("llm"),
        writer,
    )

    model = ChatOpenAI(
        model="deepseek/deepseek-chat",
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key if settings else None,
        temperature=0.1,
    ).bind_tools(tools)

    messages = [
        SystemMessage(content=REFRESH_SYSTEM_PROMPT),
        *state.messages,
        HumanMessage(content=f"""
Visit the official website: {official_url}

Extract the following information:
1. Are the current dates correct? (start: {state.current_event_date.get("start")})
2. Is the description accurate and complete?
3. Can you find a lineup/artist list?
4. Are there ticket links?

Use the appropriate tools to gather this information.
""")
    ]

    response = await model.ainvoke(messages)

    return {
        "messages": [response],
        "official_url": official_url,
        "found_official_site": True,
        "iteration": state.iteration + 1,
    }


async def evaluate_node(state: RefreshState, config: RunnableConfig) -> dict:
    """
    Evaluate findings and propose changes.
    """
    writer = config.get("writer")

    if writer:
        await writer({
            "type": "reasoning",
            "thought": "Evaluating findings and proposing changes...",
        })

    # Analyze what we found vs current data
    proposed_event_changes = {}
    proposed_date_changes = {}
    change_summary = []
    date_confidence = 0.0
    lineup_confidence = 0.0
    description_confidence = 0.0

    # TODO: Parse tool results to extract actual changes
    # For now, create a summary based on what we know

    date_verified = False  # Set based on verify_date tool result
    lineup_found = False

    # Check for date verification
    for msg in state.messages:
        if isinstance(msg, ToolMessage) and msg.name == "verify_date":
            try:
                data = json.loads(msg.content)
                date_verified = data.get("date_correct", False)
                date_confidence = data.get("confidence", 0.0)
                if date_verified:
                    change_summary.append("✓ Date verified as correct")
                else:
                    found_date = data.get("found_date")
                    if found_date:
                        proposed_date_changes["start"] = found_date
                        change_summary.append(f"✗ Date corrected: {found_date}")
            except (json.JSONDecodeError, TypeError):
                pass

    # Check for lineup
    for msg in state.messages:
        if isinstance(msg, ToolMessage) and msg.name == "extract_lineup":
            try:
                data = json.loads(msg.content)
                artists = data.get("artists", [])
                if artists:
                    lineup_found = True
                    lineup_confidence = 0.85
                    current_lineup = state.current_event_date.get("artists", [])
                    if len(artists) > len(current_lineup):
                        proposed_date_changes["artists"] = [{"name": a} for a in artists]
                        change_summary.append(f"+ Lineup added: {len(artists)} artists")
            except (json.JSONDecodeError, TypeError):
                pass

    # Determine if auto-approval is appropriate
    should_auto_approve = (
        date_confidence >= 0.9 and
        (not proposed_event_changes or description_confidence >= 0.9) and
        len(change_summary) > 0
    )

    return {
        "proposed_event_changes": proposed_event_changes,
        "proposed_date_changes": proposed_date_changes,
        "change_summary": change_summary,
        "date_confidence": date_confidence,
        "lineup_confidence": lineup_confidence,
        "description_confidence": description_confidence,
        "date_verified": date_verified,
        "lineup_found": lineup_found,
        "should_auto_approve": should_auto_approve,
        "needs_approval": not should_auto_approve,
    }
