"""Shared Playwright browser tools using LangChain's PlayWrightBrowserToolkit.

This module provides reusable browser automation tools using the official
LangChain PlayWrightBrowserToolkit for consistency across all agents.

Usage:
    from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
    from langchain_community.tools.playwright.utils import create_async_playwright_browser
    
    async_browser = await create_async_playwright_browser()
    toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=async_browser)
    tools = toolkit.get_tools()
"""

import logging
from typing import Any, List, Optional

from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
from langchain_community.tools.playwright.utils import create_async_playwright_browser

logger = logging.getLogger(__name__)


async def create_playwright_tools(
    headless: bool = True,
    slow_mo: Optional[int] = None
) -> List[Any]:
    """
    Create Playwright browser tools using LangChain's PlayWrightBrowserToolkit.
    
    Args:
        headless: Whether to run browser in headless mode
        slow_mo: Slow down operations by specified milliseconds
        
    Returns:
        List of Playwright tools from the toolkit
    """
    try:
        # Create async Playwright browser
        async_browser = await create_async_playwright_browser(
            headless=headless,
            slow_mo=slow_mo
        )

        # Create toolkit
        toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=async_browser)

        # Get all tools
        tools = toolkit.get_tools()

        logger.info(f"Created {len(tools)} Playwright tools from toolkit: {[t.name for t in tools]}")
        return tools

    except Exception as e:
        logger.error(f"Failed to create Playwright tools: {e}")
        logger.warning("Falling back to custom browser tools")
        raise


async def create_playwright_tools_with_existing_browser(
    async_browser: Any,
) -> List[Any]:
    """
    Create Playwright tools from an existing async browser instance.
    
    Args:
        async_browser: Existing async Playwright browser instance
        
    Returns:
        List of Playwright tools
    """
    try:
        # Create toolkit from existing browser
        toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=async_browser)

        # Get all tools
        tools = toolkit.get_tools()

        logger.info(f"Created {len(tools)} Playwright tools from existing browser")
        return tools

    except Exception as e:
        logger.error(f"Failed to create Playwright tools: {e}")
        raise


# Export toolkit utilities
__all__ = [
    "create_playwright_tools",
    "create_playwright_tools_with_existing_browser",
    "PlayWrightBrowserToolkit",
    "create_async_playwright_browser",
]
