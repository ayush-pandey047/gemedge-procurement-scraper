import asyncio
import logging
from typing import Optional, List

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

from config.settings import (
    BASE_URL,
    ALL_BIDS_URL,
    HEADLESS,
    VIEWPORT,
    USER_AGENT,
    PAGE_TIMEOUT,
)

logger = logging.getLogger(__name__)


class BrowserManager:
    """
    Manages a pool of Playwright browser contexts.
    Each context holds an anonymous ci_session cookie so requests to
    getBidResultView succeed without login.
    """

    def __init__(self, num_contexts: int = 1):
        self.num_contexts = num_contexts
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._contexts: List[BrowserContext] = []
        self._cookie_jar: List[dict] = []   # shared anonymous cookies

    async def start(self) -> None:
        """Launch browser and harvest the anonymous session cookie."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=HEADLESS)
        logger.info("Browser launched (headless=%s)", HEADLESS)

        # ── Harvest anonymous cookie from /all-bids ───────────────────────
        seed_ctx = await self._browser.new_context(
            viewport=VIEWPORT,
            user_agent=USER_AGENT,
        )
        seed_page = await seed_ctx.new_page()
        seed_page.set_default_timeout(PAGE_TIMEOUT)

        logger.info("Visiting %s to obtain anonymous ci_session cookie...", ALL_BIDS_URL)
        try:
            await seed_page.goto(ALL_BIDS_URL, wait_until="domcontentloaded")
            await seed_page.wait_for_timeout(2000)  # let JS set cookies
            self._cookie_jar = await seed_ctx.cookies()
            logger.info("Harvested %d cookies", len(self._cookie_jar))
        except Exception as exc:
            logger.warning("Cookie harvest failed: %s — will try without preset cookie", exc)
        finally:
            await seed_page.close()
            await seed_ctx.close()

        # ── Spin up agent contexts ─────────────────────────────────────────
        for i in range(self.num_contexts):
            ctx = await self._browser.new_context(
                viewport=VIEWPORT,
                user_agent=USER_AGENT,
            )
            if self._cookie_jar:
                await ctx.add_cookies(self._cookie_jar)
            self._contexts.append(ctx)

        logger.info("Spawned %d browser contexts", len(self._contexts))

    async def get_context(self, index: int = 0) -> BrowserContext:
        return self._contexts[index % len(self._contexts)]

    async def new_page(self, index: int = 0) -> Page:
        ctx = await self.get_context(index)
        page = await ctx.new_page()
        page.set_default_timeout(PAGE_TIMEOUT)
        return page

    async def get_cookies_dict(self) -> dict:
        """Return cookies as a dict usable in aiohttp headers."""
        return {c["name"]: c["value"] for c in self._cookie_jar}

    async def stop(self) -> None:
        for ctx in self._contexts:
            await ctx.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser stopped")


async def safe_goto(page: Page, url: str, retries: int = 3) -> bool:
    """Navigate with retry logic. Returns True on success."""
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded")
            return True
        except Exception as exc:
            logger.warning("Goto attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
            if attempt < retries:
                await asyncio.sleep(2 * attempt)
    return False
