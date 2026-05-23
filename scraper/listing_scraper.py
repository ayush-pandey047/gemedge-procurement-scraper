import asyncio
import logging
import json
from pathlib import Path
from playwright.async_api import Page
from config.settings import (
    BASE_URL, FILTER_STATUS, FILTER_OUTCOME,
    MIN_ENTRIES, NAVIGATION_WAIT, RAW_DATA_DIR
)
from scraper.browser import safe_goto, wait_for_table

logger = logging.getLogger(__name__)


async def apply_filters(page: Page) -> bool:
    """
    Navigate to the bids listing page and apply the required filters.

    GEM portal has dropdown/select filters at the top of the table.
    We select Status = 'Bid/RA' and Outcome = 'Awarded', then click Search.

    Returns True if filters applied successfully.
    """

    logger.info(f"Navigating to: {BASE_URL}")
    success = await safe_goto(page, BASE_URL)
    if not success:
        return False

    try:
       
        await page.wait_for_selector("select, input[type='search']", state="visible", timeout=30_000)
 
        status_selectors = [
            "select[name*='status']",
            "select[id*='status']",
            "#bid_status",
            "select:has(option:text('Bid/RA'))",
        ]
        for sel in status_selectors:
            try:
                await page.select_option(sel, label=FILTER_STATUS)
                logger.info(f"Status filter set via selector: {sel}")
                break
            except Exception:
                continue

        
        outcome_selectors = [
            "select[name*='outcome']",
            "select[id*='outcome']",
            "select:has(option:text('Awarded'))",
        ]
        for sel in outcome_selectors:
            try:
                await page.select_option(sel, label=FILTER_OUTCOME)
                logger.info(f"Outcome filter set via selector: {sel}")
                break
            except Exception:
                continue

 
        search_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Search')",
            "button:has-text('Filter')",
            "#searchBtn",
        ]
        for sel in search_selectors:
            try:
                await page.click(sel)
                logger.info(f"Search triggered via: {sel}")
                break
            except Exception:
                continue

       
        await page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT)
        await asyncio.sleep(NAVIGATION_WAIT / 1000)
        return True

    except Exception as e:
        logger.error(f"Filter application failed: {e}")
        return False


async def extract_listing_rows(page: Page) -> list[dict]:
    """
    Extract all visible rows from the bids listing table on the current page.

    Each row = one bid entry. We extract:
      bid_id, category, buyer, quantity, bid_value, award_date
    and also the URL to the bid detail page (needed for Steps 3 & 4).
    """
    rows = []

    try:
       
        table_visible = await wait_for_table(page, "table.table, table#bidsTable, table")
        if not table_visible:
            logger.warning("No table found on listing page.")
            return rows

       
        row_data = await page.evaluate("""
            () => {
                const rows = [];
                // Try multiple table selectors since GEM may have nested tables
                const tableSelectors = [
                    'table#bidsTable tbody tr',
                    'table.table tbody tr',
                    '.bid-list tr',
                    'table tbody tr',
                ];

                let trs = [];
                for (const sel of tableSelectors) {
                    trs = document.querySelectorAll(sel);
                    if (trs.length > 0) break;
                }

                trs.forEach(tr => {
                    const cells = tr.querySelectorAll('td');
                    if (cells.length < 4) return;  // skip header/empty rows

                    // Try to find the detail link inside this row
                    const link = tr.querySelector('a[href*="bid"], a[href*="result"]');
                    const href = link ? link.href : '';

                    rows.push({
                        bid_id    : cells[0]?.innerText?.trim() || '',
                        category  : cells[1]?.innerText?.trim() || '',
                        buyer     : cells[2]?.innerText?.trim() || '',
                        quantity  : cells[3]?.innerText?.trim() || '',
                        bid_value : cells[4]?.innerText?.trim() || '',
                        award_date: cells[5]?.innerText?.trim() || '',
                        detail_url: href,
                    });
                });
                return rows;
            }
        """)

        rows.extend(row_data)
        logger.info(f"Extracted {len(rows)} rows from current page.")

    except Exception as e:
        logger.error(f"Row extraction error: {e}")

    return rows


async def scrape_listings(page: Page) -> list[dict]:
    """
    Main listing scraper — handles pagination until we have MIN_ENTRIES rows.

    WHY pagination loop?
      GEM shows ~10-20 bids per page. We need at least 30 so we must
      navigate to the next page if needed.
    """
    all_entries = []

    
    filter_ok = await apply_filters(page)
    if not filter_ok:
        logger.error("Could not apply filters. Trying to scrape without filters.")

    page_num = 1
    while len(all_entries) < MIN_ENTRIES:
        logger.info(f"Scraping listing page {page_num}...")

        rows = await extract_listing_rows(page)
        if not rows:
            logger.warning(f"No rows found on page {page_num}. Stopping pagination.")
            break

        all_entries.extend(rows)
        logger.info(f"Total collected so far: {len(all_entries)}")

        
        if len(all_entries) < MIN_ENTRIES:
            next_clicked = await go_to_next_page(page, page_num)
            if not next_clicked:
                logger.info("No more pages available.")
                break
            page_num += 1
            await asyncio.sleep(NAVIGATION_WAIT / 1000)

    raw_path = RAW_DATA_DIR / "raw_listings.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, indent=2, ensure_ascii=False)
    logger.info(f"Raw listings saved to {raw_path}")

    return all_entries[:MIN_ENTRIES] 


async def go_to_next_page(page: Page, current_page: int) -> bool:
    """
    Attempt to click the 'Next' pagination button.

    GEM uses different pagination styles — numbered links, 'Next' button,
    or arrow icons. We try several selectors.
    """
    next_selectors = [
        "a:has-text('Next')",
        "a:has-text('»')",
        f"a:has-text('{current_page + 1}')",
        ".pagination .next a",
        "li.next a",
        "[aria-label='Next page']",
    ]
    for sel in next_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible():
                await btn.click()
                await page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT)
                return True
        except Exception:
            continue
    return False