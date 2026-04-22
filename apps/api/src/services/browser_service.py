"""Browser service for LangGraph tools."""

import logging
from typing import List, Optional

from playwright.async_api import Browser as PlaywrightBrowser
from playwright.async_api import Page, async_playwright

from src.config import Settings

logger = logging.getLogger(__name__)


class BrowserService:
    """Browser service for agent tools using Playwright."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.browser: Optional[PlaywrightBrowser] = None
        self.page: Optional[Page] = None
        self._playwright = None

    async def start(self):
        """Initialize browser."""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=self.settings.browser_headless
        )
        self.page = await self.browser.new_page()
        logger.info("Browser service started")

    async def close(self):
        """Close browser."""
        if self.page:
            await self.page.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser service closed")

    async def navigate(self, url: str) -> None:
        """Navigate to a URL."""
        if not self.page:
            await self.start()
        await self.page.goto(url, wait_until="networkidle")
        logger.info(f"Navigated to {url}")

    async def get_page_content(self) -> str:
        """Get current page HTML content."""
        if not self.page:
            return ""
        return await self.page.content()

    async def get_page_title(self) -> str:
        """Get current page title."""
        if not self.page:
            return ""
        return await self.page.title()

    async def click_link(self, link_text: str) -> bool:
        """Click a link by its text."""
        if not self.page:
            return False

        try:
            # Try exact match first
            link = self.page.get_by_role("link", name=link_text, exact=False)
            if await link.count() > 0:
                await link.first.click()
                await self.page.wait_for_load_state("networkidle")
                return True

            # Try case-insensitive contains
            link = self.page.locator(f'a:has-text("{link_text}")')
            if await link.count() > 0:
                await link.first.click()
                await self.page.wait_for_load_state("networkidle")
                return True

            return False
        except Exception as e:
            logger.warning(f"Failed to click link '{link_text}': {e}")
            return False

    async def screenshot(self) -> bytes:
        """Take a screenshot of the current page."""
        if not self.page:
            return b""
        return await self.page.screenshot(full_page=True)

    async def find_images(self) -> List[dict]:
        """Extract all images from the page with metadata for LLM selection.

        Returns list of dicts with:
        - url: image source URL
        - alt: alt text
        - width: natural width
        - height: natural height
        - aspect_ratio: width/height ratio (for detecting square logos)
        - is_visible: whether element is visible
        """
        if not self.page:
            return []

        try:
            images = await self.page.evaluate("""() => {
                return Array.from(document.querySelectorAll('img'))
                    .filter(img => {
                        // Filter out tiny images (icons, tracking pixels)
                        const minSize = 100;
                        return img.naturalWidth >= minSize && img.naturalHeight >= minSize;
                    })
                    .map(img => ({
                        url: img.src,
                        alt: img.alt || "",
                        width: img.naturalWidth,
                        height: img.naturalHeight,
                        aspect_ratio: +(img.naturalWidth / img.naturalHeight).toFixed(2),
                        is_visible: img.offsetParent !== null
                    }))
                    .filter(img => img.url && img.url.startsWith('http'));
            }""")
            return images
        except Exception as e:
            logger.warning(f"Failed to extract images: {e}")
            return []

    async def extract_jsonld(self) -> List[dict]:
        """Extract all JSON-LD structured data from the page.

        Returns list of parsed JSON-LD objects.
        """
        if not self.page:
            return []

        try:
            jsonld_data = await self.page.evaluate("""() => {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                return Array.from(scripts)
                    .map(script => {
                        try {
                            return JSON.parse(script.textContent);
                        } catch (e) {
                            return null;
                        }
                    })
                    .filter(data => data !== null);
            }""")
            return jsonld_data
        except Exception as e:
            logger.warning(f"Failed to extract JSON-LD: {e}")
            return []
