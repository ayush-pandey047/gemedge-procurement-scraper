import asyncio
import logging
import json
from playwright.async_api import Page
from config.settings import (
    BASE_URL, MIN_ENTRIES, NAVIGATION_WAIT,
    RAW_DATA_DIR, PAGE_TIMEOUT
)
from scraper.browser import safe_goto

logger = logging.getLogger(__name__)


async def scrape_listings(page: Page) -> list[dict]:
    logger.info(f"Navigating to: {BASE_URL}")
    await safe_goto(page, BASE_URL)
    await asyncio.sleep(5)

    # ── Step 1: Click "Bid/RA Status" to enable status checkboxes ────────────
    try:
        # Find and click the "Bid/RA Status" parent checkbox/label first
        await page.evaluate("""
            () => {
                var inputs = Array.from(document.querySelectorAll('input'));
                for (var inp of inputs) {
                    var label = inp.labels && inp.labels[0] ? inp.labels[0].innerText.trim() : '';
                    if (label === 'Bid/RA Status') {
                        inp.click();
                        return 'clicked Bid/RA Status';
                    }
                }
                // Also try by label text
                var labels = Array.from(document.querySelectorAll('label'));
                for (var lbl of labels) {
                    if (lbl.innerText.trim() === 'Bid/RA Status') {
                        lbl.click();
                        return 'clicked label';
                    }
                }
                return 'not found';
            }
        """)
        await asyncio.sleep(3)
        logger.info("Clicked 'Bid/RA Status' parent filter")
    except Exception as e:
        logger.warning(f"Could not click Bid/RA Status: {e}")

    # ── Step 2: Now click "Bid /RA Awarded" via JS to bypass disabled state ──
    try:
        await page.evaluate("""
            () => {
                var cb = document.getElementById('bid_awarded');
                if (cb) {
                    cb.removeAttribute('disabled');
                    cb.click();
                    // Also trigger the onclick handler manually
                    if (typeof bidStatusFilter === 'function') {
                        bidStatusFilter('bid_awarded');
                    }
                    return 'clicked bid_awarded';
                }
                return 'not found';
            }
        """)
        await asyncio.sleep(4)
        await page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT)
        logger.info("Applied 'Bid /RA Awarded' filter")
    except Exception as e:
        logger.warning(f"Could not apply awarded filter: {e}")

    all_entries = []
    page_num = 1

    while len(all_entries) < MIN_ENTRIES:
        logger.info(f"Scraping page {page_num}...")

        try:
            await page.wait_for_selector("div.card", timeout=PAGE_TIMEOUT)
        except Exception:
            logger.warning("No cards found on page. Stopping.")
            break

        rows = await page.evaluate("""
            () => {
                var results = [];
                var cards = document.querySelectorAll('div.card');
                cards.forEach(function(card) {
                    if (!card) return;
                    var text = card.innerText || '';
                    if (!text) return;

                    var bidLink = card.querySelector('a.bid_no_hover');
                    var bid_id = bidLink ? bidLink.innerText.trim() : '';
                    if (!bid_id) return;

                    var allLinks = Array.from(card.querySelectorAll('a'));
                    var ra_pdf_url = '';
                    var bid_doc_url = '';
                    allLinks.forEach(function(a) {
                        if (a.href.indexOf('showradocumentPdf') > -1) ra_pdf_url = a.href;
                        if (a.href.indexOf('showbidDocument') > -1) bid_doc_url = a.href;
                    });

                    function extract(label) {
                        try {
                            var re = new RegExp(label + '[:\\s]+([^\\n]+)', 'i');
                            var m = text.match(re);
                            return (m && m[1]) ? m[1].trim() : '';
                        } catch(e) { return ''; }
                    }

                    results.push({
                        bid_id      : bid_id,
                        ra_pdf_url  : ra_pdf_url,
                        bid_doc_url : bid_doc_url,
                        category    : extract('Item Category|Category'),
                        buyer       : extract('Ministry|Department|Buyer|Organisation'),
                        quantity    : extract('Quantity'),
                        bid_value   : extract('Bid Value|EMD Amount|Estimated Value'),
                        award_date  : extract('Bid End Date|End Date|Award Date'),
                        raw_text    : text.substring(0, 500)
                    });
                });
                return results;
            }
        """)

        rows = [r for r in rows if r.get("bid_id")]
        logger.info(f"  Found {len(rows)} awarded bid cards on page {page_num}")
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
    next_selectors = [
        "a:has-text('Next')",
        "a:has-text('»')",
        ".pagination .next a",
        "li.next a",
        "a[aria-label='Next']",
    ]
    for sel in next_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3_000):
                await btn.click()
                await page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT)
                return True
        except Exception:
            continue
    return False
