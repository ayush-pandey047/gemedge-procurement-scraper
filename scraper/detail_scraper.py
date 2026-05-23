import asyncio
import logging
import json
import re
from playwright.async_api import Page
from config.settings import RAW_DATA_DIR, PAGE_TIMEOUT, NAVIGATION_WAIT

logger = logging.getLogger(__name__)


async def scrape_result_page(page: Page, result_url: str, numeric_id: str) -> dict:
    """
    Fetch getBidResultView with the anonymous ci_session cookie
    that Playwright already has from visiting /all-bids.
    Works for ~83% of bids without any login.
    """
    empty = {
        "winner_name"   : "LOGIN_REQUIRED",
        "winner_price"  : "",
        "num_bidders"   : "",
        "vendors"       : [],
        "result_accessible": "login_required"
    }

    if not result_url:
        return empty

    try:
        await page.goto(result_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        await asyncio.sleep(2)

        # If redirected away — this bid is SSO-gated
        if "bidplus.gem.gov.in" not in page.url:
            logger.warning(f"  [{numeric_id}] SSO-gated — login required")
            return empty

        # Extract all text
        page_text = await page.evaluate("() => document.body.innerText || ''")

        # Check if result data is actually present
        has_data = any(k in page_text.lower() for k in [
            'l1', 'winner', 'vendor', 'rank', 'price', 'bidder', 'awarded'
        ])
        if not has_data:
            logger.warning(f"  [{numeric_id}] No result data visible")
            return empty

        # Extract vendor table
        vendors = await page.evaluate("""
            () => {
                var vendors = [];
                var tables = document.querySelectorAll('table');
                tables.forEach(function(tbl) {
                    var headers = Array.from(tbl.querySelectorAll('th')).map(function(h){
                        return h.innerText.trim().toLowerCase();
                    });
                    var hasVendor = headers.some(function(h){
                        return h.includes('vendor') || h.includes('bidder') || h.includes('rank') || h.includes('name');
                    });
                    if (!hasVendor) return;

                    var rows = tbl.querySelectorAll('tbody tr');
                    rows.forEach(function(row) {
                        var cells = Array.from(row.querySelectorAll('td')).map(function(c){
                            return c.innerText.trim();
                        });
                        if (cells.length < 2) return;
                        var vendor = {
                            vendor_name : '', vendor_rank: '',
                            vendor_price: '', disqualified: false, remarks: ''
                        };
                        headers.forEach(function(h, i) {
                            var val = cells[i] || '';
                            if (h.includes('name') || h.includes('vendor') || h.includes('bidder')) vendor.vendor_name = val;
                            else if (h.includes('rank') || h === 'l1' || h === 'l2') vendor.vendor_rank = val;
                            else if (h.includes('price') || h.includes('amount') || h.includes('quoted')) vendor.vendor_price = val.replace(/,/g,'');
                            else if (h.includes('remark') || h.includes('status')) {
                                vendor.remarks = val;
                                if (val.toLowerCase().includes('disq') || val.toLowerCase() === 'dq') vendor.disqualified = true;
                            }
                        });
                        if (vendor.vendor_name || vendor.vendor_rank) vendors.push(vendor);
                    });
                });
                return vendors;
            }
        """)

        # Extract winner + L1 price from text patterns
        winner_name  = ""
        winner_price = ""
        num_bidders  = str(len(vendors)) if vendors else ""

        # L1 vendor is first ranked vendor
        for v in vendors:
            rank = str(v.get("vendor_rank", "")).upper()
            if rank in ("L1", "1", "RANK 1", "WINNER"):
                winner_name  = v.get("vendor_name", "")
                winner_price = v.get("vendor_price", "")
                break

        # Fallback: regex on page text
        if not winner_name:
            patterns = [
                r"L1\s+Vendor[:\s]+([A-Za-z0-9\s&.,()-]+)",
                r"Winner[:\s]+([A-Za-z0-9\s&.,()-]+)",
                r"Awarded\s+to[:\s]+([A-Za-z0-9\s&.,()-]+)",
            ]
            for pat in patterns:
                m = re.search(pat, page_text, re.IGNORECASE)
                if m:
                    winner_name = m.group(1).strip()[:100]
                    break

        if not winner_price:
            price_patterns = [
                r"L1\s+Price[:\s]+([\d,]+\.?\d*)",
                r"Awarded\s+Price[:\s]+([\d,]+\.?\d*)",
                r"Final\s+Price[:\s]+([\d,]+\.?\d*)",
            ]
            for pat in price_patterns:
                m = re.search(pat, page_text, re.IGNORECASE)
                if m:
                    winner_price = m.group(1).replace(",", "")
                    break

        if not num_bidders:
            m = re.search(r"(?:total|no\.?\s*of)\s*bidder[s]?[:\s]+(\d+)", page_text, re.IGNORECASE)
            if m:
                num_bidders = m.group(1)

        logger.info(f"  [{numeric_id}] Winner: {winner_name[:40] if winner_name else 'N/A'} | "
                    f"Price: {winner_price} | Vendors: {len(vendors)}")

        return {
            "winner_name"      : winner_name or "NOT_FOUND",
            "winner_price"     : winner_price,
            "num_bidders"      : num_bidders,
            "vendors"          : vendors,
            "result_accessible": "public"
        }

    except Exception as e:
        logger.warning(f"  Result page error [{numeric_id}]: {e}")
        return empty


async def scrape_all_details(page: Page, listings: list[dict]) -> list[dict]:
    enriched = []
    public_count = 0
    gated_count  = 0

    for i, entry in enumerate(listings, 1):
        bid_id     = entry.get("bid_id", f"bid_{i}")
        result_url = entry.get("result_url", "")
        numeric_id = entry.get("numeric_id", "")
        logger.info(f"Detail [{i}/{len(listings)}]: {bid_id}")

        result_data = await scrape_result_page(page, result_url, numeric_id)
        entry.update(result_data)

        if result_data["result_accessible"] == "public":
            public_count += 1
        else:
            gated_count += 1

        enriched.append(entry)
        await asyncio.sleep(NAVIGATION_WAIT / 1000)

    logger.info(f"Results: {public_count} public | {gated_count} login-required")

    raw_path = RAW_DATA_DIR / "raw_with_details.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(enriched)} enriched entries")
    return enriched
