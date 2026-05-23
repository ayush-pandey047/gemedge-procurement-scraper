import asyncio
import logging
import json
from pathlib import Path
from playwright.async_api import Page
from config.settings import BASE_URL, MIN_ENTRIES, NAVIGATION_WAIT, RAW_DATA_DIR, PAGE_TIMEOUT
from scraper.browser import safe_goto

logger = logging.getLogger(__name__)

JS_FILE = Path(__file__).parent / "card_extractor.js"


async def scrape_listings(page: Page) -> list[dict]:
    logger.info(f"Navigating to: {BASE_URL}")
    await safe_goto(page, BASE_URL)
    await asyncio.sleep(5)

    try:
        await page.evaluate("() => { var inputs = Array.from(document.querySelectorAll('input')); for (var inp of inputs) { var label = inp.labels && inp.labels[0] ? inp.labels[0].innerText.trim() : ''; if (label === 'Bid/RA Status') { inp.click(); return; } } }")
        await asyncio.sleep(3)
        logger.info("Clicked Bid/RA Status filter")
    except Exception as e:
        logger.warning(f"Filter click failed: {e}")

    try:
        await page.evaluate("() => { var cb = document.getElementById('bid_awarded'); if (cb) { cb.removeAttribute('disabled'); cb.click(); if (typeof bidStatusFilter === 'function') bidStatusFilter('bid_awarded'); } }")
        await asyncio.sleep(4)
        await page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT)
        logger.info("Applied Bid/RA Awarded filter")
    except Exception as e:
        logger.warning(f"Awarded filter failed: {e}")

    # Load JS extractor from file — avoids all Python string escaping issues
    js_code = JS_FILE.read_text(encoding="utf-8")

    all_entries = []
    page_num = 1

    while len(all_entries) < MIN_ENTRIES:
        logger.info(f"Scraping page {page_num}...")
        try:
            await page.wait_for_selector("div.card", timeout=PAGE_TIMEOUT)
        except Exception:
            logger.warning("No cards found. Stopping.")
            break

        rows = await page.evaluate(js_code)
        rows = [r for r in rows if r.get("bid_id")]
        logger.info(f"  Found {len(rows)} cards on page {page_num}")
        all_entries.extend(rows)

        if len(all_entries) >= MIN_ENTRIES:
            break

        next_clicked = await go_to_next_page(page)
        if not next_clicked:
            logger.info("No more pages.")
            break

        page_num += 1
        await asyncio.sleep(NAVIGATION_WAIT / 1000)

    raw_path = RAW_DATA_DIR / "raw_listings.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(all_entries)} listings to {raw_path}")
    return all_entries[:MIN_ENTRIES]


async def go_to_next_page(page: Page) -> bool:
    for sel in ["a:has-text('Next')", "a:has-text('»')", ".pagination .next a", "li.next a"]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3_000):
                await btn.click()
                await page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT)
                return True
        except Exception:
            continue
    return False
