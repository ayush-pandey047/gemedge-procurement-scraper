import logging
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from config.settings import PAGE_TIMEOUT, RETRY_LIMIT, HEADLESS, BASE_DIR

logger = logging.getLogger(__name__)


class BrowserManager:
    """
    Context manager that owns the Playwright browser instance.
    Using 'async with BrowserManager() as bm' ensures the browser
    is always closed, even if an exception occurs mid-scrape.
    """

    def __init__(self):
        self._playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()

        
        self.browser = await self._playwright.chromium.launch(
                headless=HEADLESS,
                args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                    ])

       
        self.context = await self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )

        await self.context.route("**/*.pdf", lambda route: route.abort())
        await self.context.route("**/showbidDocument/**", lambda route: route.abort())
        self.context.set_default_timeout(PAGE_TIMEOUT)
        logger.info("Browser launched successfully.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed.")

    async def new_page(self) -> Page:
        """Open a new tab."""
        return await self.context.new_page()


async def safe_goto(page: Page, url: str, wait_until: str = "networkidle") -> bool:
    """
    Navigate to a URL with retry logic.

    WHY retry? Government portals timeout randomly. Instead of crashing the
    entire scrape run, we retry up to RETRY_LIMIT times with exponential backoff.

    Returns True if navigation succeeded, False after all retries failed.
    """
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            await page.goto(url, wait_until=wait_until, timeout=PAGE_TIMEOUT)
            logger.debug(f"Navigated to {url}")
            return True
        except Exception as e:
            logger.warning(f"Attempt {attempt}/{RETRY_LIMIT} failed for {url}: {e}")
            if attempt < RETRY_LIMIT:
                await asyncio.sleep(2 ** attempt)  
            else:
                
                screenshot_path = BASE_DIR / "data" / f"error_screenshot_{attempt}.png"
                try:
                    await page.screenshot(path=str(screenshot_path))
                    logger.error(f"Screenshot saved to {screenshot_path}")
                except Exception:
                    pass
                logger.error(f"All retries failed for {url}")
                return False


async def wait_for_table(page: Page, selector: str = "table") -> bool:
    """
    Wait for a table element to appear on the page.

    GEM portal loads tables via AJAX. We must wait for the table
    to be visible before trying to read its rows.
    """
    try:
        await page.wait_for_selector(selector, state="visible", timeout=PAGE_TIMEOUT)
        return True
    except Exception as e:
        logger.warning(f"Table not found with selector '{selector}': {e}")
        return False