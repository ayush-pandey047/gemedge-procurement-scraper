import asyncio
import logging
from playwright.async_api import Page
from config.settings import NAVIGATION_WAIT, PAGE_TIMEOUT
from scraper.browser import safe_goto

logger = logging.getLogger(__name__)


async def scrape_evaluation(page: Page, detail_url: str) -> list[dict]:
    """
    Navigate to a bid's detail URL, then click "Evaluation Details"
    tab/section and extract the vendor evaluation table.

    Returns a list of vendor records:
        [{ vendor_name, vendor_rank, vendor_price, disqualified, remarks }, ...]
    """
    vendors = []

    if not detail_url:
        return vendors

    
    await safe_goto(page, detail_url)
    await asyncio.sleep(NAVIGATION_WAIT / 1000)

    eval_selectors = [
        "a:has-text('Evaluation Details')",
        "button:has-text('Evaluation Details')",
        "a:has-text('Evaluation')",
        "#evaluationTab",
        ".eval-tab",
        "li:has-text('Evaluation') a",
    ]
    for sel in eval_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=5_000):
                await el.click()
                await page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT)
                logger.info(f"  Clicked Evaluation Details tab.")
                break
        except Exception:
            continue

    await asyncio.sleep(NAVIGATION_WAIT / 1000)

    vendor_data = await page.evaluate("""
        () => {
            const vendors = [];

            
            const tableSelectors = [
                'table#evaluationTable',
                'table.eval-table',
                'table.comparison-table',
                'table',  
            ];

            let tableEl = null;
            for (const sel of tableSelectors) {
                tableEl = document.querySelector(sel);
                if (tableEl) break;
            }

            if (!tableEl) return vendors;

            const rows = tableEl.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length < 2) return;

               
                const vendor = {
                    vendor_name    : '',
                    vendor_rank    : '',
                    vendor_price   : '',
                    disqualified   : false,
                    remarks        : ''
                };

                
                cells.forEach((cell, idx) => {
                    const text = cell.innerText?.trim() || '';
                    if (/^L\d+$/.test(text) || text === 'DQ') {
                        vendor.vendor_rank = text;
                        if (text === 'DQ') vendor.disqualified = true;
                    } else if (idx === 1 && !vendor.vendor_name) {
                        vendor.vendor_name = text;
                    } else if (text.match(/^[\d,]+\.?\d*$/) && !vendor.vendor_price) {
                        vendor.vendor_price = text;  // numeric → price
                    } else if (idx === cells.length - 1 && text) {
                        vendor.remarks = text; 
                    }
                });

              
                if (vendor.vendor_name || vendor.vendor_rank) {
                    vendors.push(vendor);
                }
            });

            return vendors;
        }
    """)

    vendors = vendor_data
    logger.info(f"  Evaluation: found {len(vendors)} vendor records.")
    return vendors


async def scrape_all_evaluations(page: Page, listings: list[dict]) -> list[dict]:
    """
    For each listing entry, scrape evaluation details and attach
    vendor-level rows.

    Returns a FLAT list — one row per VENDOR (not per bid).
    This matches the expected output schema (vendor_name, vendor_rank,
    vendor_price all at row level).
    """
    import json
    from config.settings import RAW_DATA_DIR

    flat_rows = []

    for i, entry in enumerate(listings, 1):
        logger.info(f"Evaluation scraping [{i}/{len(listings)}]: {entry.get('bid_id')}")
        vendors = await scrape_evaluation(page, entry.get("detail_url", ""))

        if not vendors:
           
            row = dict(entry)
            row.update({
                "vendor_name" : "",
                "vendor_rank" : "",
                "vendor_price": "",
                "disqualified": False,
                "remarks"     : "",
            })
            flat_rows.append(row)
        else:
            for vendor in vendors:
                row = dict(entry) 
                row.update(vendor)  
                flat_rows.append(row)


    raw_path = RAW_DATA_DIR / "raw_evaluations.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(flat_rows, f, indent=2, ensure_ascii=False)
    logger.info(f"Raw evaluation data saved to {raw_path}")

    return flat_rows