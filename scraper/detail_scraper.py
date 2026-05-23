import asyncio
import logging
from playwright.async_api import Page
from config.settings import NAVIGATION_WAIT, PAGE_TIMEOUT
from scraper.browser import safe_goto, wait_for_table

logger = logging.getLogger(__name__)


async def scrape_bid_detail(page: Page, entry: dict) -> dict:
    """
    Given a listing entry with a detail_url, navigate to the bid result page
    and extract winner info.

    Returns the entry dict enriched with:
        winner_name, winner_price, num_bidders
    """
    detail_url = entry.get("detail_url", "")
    if not detail_url:
        logger.warning(f"No detail URL for bid {entry.get('bid_id')}. Skipping.")
        entry.update({"winner_name": "", "winner_price": "", "num_bidders": ""})
        return entry

    logger.info(f"  → Detail page for bid {entry.get('bid_id')}: {detail_url}")

    success = await safe_goto(page, detail_url)
    if not success:
        entry.update({"winner_name": "ERROR", "winner_price": "ERROR", "num_bidders": "ERROR"})
        return entry

    await asyncio.sleep(NAVIGATION_WAIT / 1000)

    view_result_selectors = [
        "a:has-text('View Bid Result')",
        "button:has-text('View Bid Result')",
        "a:has-text('Bid Result')",
        "#viewBidResult",
    ]
    for sel in view_result_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=5_000):
                await el.click()
                await page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT)
                logger.info(f"    Clicked 'View Bid Result'")
                break
        except Exception:
            continue

    await asyncio.sleep(NAVIGATION_WAIT / 1000)

    
    result_data = await page.evaluate("""
        () => {
            const data = {
                winner_name  : '',
                winner_price : '',
                num_bidders  : ''
            };

           
            const winnerSelectors = [
                '.winner-name', '#winnerName',
                'td:contains("L1")', 'tr.winner td',
            ];
     
            const allCells = document.querySelectorAll('td, th');
            allCells.forEach(cell => {
                const text = cell.innerText?.trim();
                if (!text) return;

                if (text === 'L1' || text.includes('L1 Price') || text.includes('Winning')) {
                   
                    const next = cell.nextElementSibling;
                    if (next && !data.winner_price) {
                        data.winner_price = next.innerText?.trim() || '';
                    }
                }
                if (text.toLowerCase().includes('vendor name') ||
                    text.toLowerCase().includes('winner')) {
                    const next = cell.nextElementSibling;
                    if (next && !data.winner_name) {
                        data.winner_name = next.innerText?.trim() || '';
                    }
                }
                if (text.toLowerCase().includes('total bidder') ||
                    text.toLowerCase().includes('participating') ||
                    text.toLowerCase().includes('no. of vendor')) {
                    const next = cell.nextElementSibling;
                    if (next && !data.num_bidders) {
                        data.num_bidders = next.innerText?.trim() || '';
                    }
                }
            });

           
            if (!data.num_bidders) {
                const resultTable = document.querySelector(
                    'table.result-table, table#vendorTable, table'
                );
                if (resultTable) {
                    const bodyRows = resultTable.querySelectorAll('tbody tr');
                    data.num_bidders = String(bodyRows.length) || '';
                }
            }

            return data;
        }
    """)

    entry.update(result_data)
    logger.info(f"    Winner: {result_data.get('winner_name')} | "
                f"Price: {result_data.get('winner_price')} | "
                f"Bidders: {result_data.get('num_bidders')}")
    return entry


async def scrape_all_details(page: Page, listings: list[dict]) -> list[dict]:
    """
    Loop over all listing entries and enrich each with detail-page data.
    Saves raw detail data after completion.
    """
    import json
    from config.settings import RAW_DATA_DIR

    enriched = []
    for i, entry in enumerate(listings, 1):
        logger.info(f"Detail scraping [{i}/{len(listings)}]: {entry.get('bid_id')}")
        enriched_entry = await scrape_bid_detail(page, entry)
        enriched.append(enriched_entry)

    raw_path = RAW_DATA_DIR / "raw_with_details.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)
    logger.info(f"Raw detail data saved to {raw_path}")

    return enriched