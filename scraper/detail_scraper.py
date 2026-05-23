
import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

from config.settings import (
    BID_RESULT_URL,
    BASE_URL,
    ALL_BIDS_URL,
    NUM_DETAIL_WORKERS,
    REQUEST_TIMEOUT,
    RETRY_ATTEMPTS,
    RETRY_DELAY,
)
from scraper.listing_scraper import BidListing

logger = logging.getLogger(__name__)


@dataclass
class BidDetail:
    result_id: str = ""
    winner_name: str = ""
    winner_price: str = ""
    num_bidders: int = 0
    result_accessible: str = "yes"   
    raw_html: str = ""


def _parse_result_page(html: str, result_id: str) -> BidDetail:
    """
    Parse getBidResultView HTML.
    The page contains a table with vendor rank, name, quoted price.
    L1 = rank 1 (winner), L2 = rank 2, etc.
    """
    detail = BidDetail(result_id=result_id)
    soup = BeautifulSoup(html, "lxml")

   
    page_text = soup.get_text().lower()
    if any(kw in page_text for kw in ["please login", "sign in", "sso login", "unauthorized"]):
        detail.result_accessible = "login_required"
        return detail

    tables = soup.select("table")
    result_table = None
    for tbl in tables:
        headers_text = " ".join(th.get_text(strip=True).lower() for th in tbl.select("th"))
        if any(kw in headers_text for kw in ["rank", "vendor", "price", "bidder", "l1", "l2"]):
            result_table = tbl
            break

    if not result_table:
        rank_items = soup.select("[class*='rank'], [class*='vendor'], [class*='bidder']")
        if not rank_items:
            detail.result_accessible = "error"
            return detail

    if result_table:
        rows = result_table.select("tbody tr, tr")
        headers = [th.get_text(strip=True).lower() for th in result_table.select("th")]

        rank_col = next((i for i, h in enumerate(headers) if "rank" in h or "sl" in h), 0)
        vendor_col = next((i for i, h in enumerate(headers) if "vendor" in h or "firm" in h or "name" in h), 1)
        price_col = next((i for i, h in enumerate(headers) if "price" in h or "amount" in h or "quoted" in h), 2)

        bidder_rows = []
        for row in rows:
            cells = row.find_all("td")
            if not cells or len(cells) < 2:
                continue
            try:
                rank_text = cells[rank_col].get_text(strip=True) if rank_col < len(cells) else ""
                vendor_text = cells[vendor_col].get_text(strip=True) if vendor_col < len(cells) else ""
                price_text = cells[price_col].get_text(strip=True) if price_col < len(cells) else ""
                if vendor_text:
                    bidder_rows.append({
                        "rank": rank_text,
                        "vendor": vendor_text,
                        "price": price_text,
                    })
            except Exception:
                continue

        detail.num_bidders = len(bidder_rows)
        if bidder_rows:
            detail.winner_name = bidder_rows[0]["vendor"]
            detail.winner_price = bidder_rows[0]["price"]

    
    if not detail.winner_name:
        winner_match = re.search(
            r"(?:winner|l1|lowest)[:\s]+([A-Za-z0-9\s&.,\-']{5,80})",
            page_text,
            re.IGNORECASE,
        )
        if winner_match:
            detail.winner_name = winner_match.group(1).strip()

    if not detail.winner_price:
        price_match = re.search(
            r"(?:l1\s*price|winning\s*price|final\s*price)[:\s₹]*([\d,\.]+)",
            page_text,
            re.IGNORECASE,
        )
        if price_match:
            detail.winner_price = price_match.group(1).strip()

    return detail


async def _fetch_result(
    session: aiohttp.ClientSession,
    result_id: str,
    cookies: dict,
    semaphore: asyncio.Semaphore,
) -> BidDetail:
    """Fetch and parse a single bid result page."""
    url = f"{BID_RESULT_URL}/{result_id}"
    async with semaphore:
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                async with session.get(
                    url,
                    headers={
                        "Referer": ALL_BIDS_URL,
                        "Accept": "text/html,application/xhtml+xml,*/*",
                    },
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        return _parse_result_page(html, result_id)
                    elif resp.status in (401, 403):
                        detail = BidDetail(result_id=result_id)
                        detail.result_accessible = "login_required"
                        return detail
                    else:
                        logger.warning("HTTP %d for result_id %s", resp.status, result_id)
            except asyncio.TimeoutError:
                logger.debug("Timeout on result_id %s (attempt %d)", result_id, attempt)
            except Exception as exc:
                logger.debug("Error on result_id %s: %s", result_id, exc)

            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY * attempt)

        detail = BidDetail(result_id=result_id)
        detail.result_accessible = "error"
        return detail


async def fetch_all_details(
    listings: list[BidListing],
    cookies: dict,
) -> dict[str, BidDetail]:
    """
    Fetch detail pages for all listings concurrently.
    Returns a dict keyed by result_id.
    """
    semaphore = asyncio.Semaphore(NUM_DETAIL_WORKERS)
    details: dict[str, BidDetail] = {}

    to_fetch = [l for l in listings if l.result_id]
    logger.info("Fetching details for %d listings (%d workers)...", len(to_fetch), NUM_DETAIL_WORKERS)

    async with aiohttp.ClientSession(cookies=cookies) as session:
        tasks = [
            _fetch_result(session, l.result_id, cookies, semaphore)
            for l in to_fetch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for listing, result in zip(to_fetch, results):
        if isinstance(result, Exception):
            logger.error("Detail fetch exception for %s: %s", listing.result_id, result)
            bad = BidDetail(result_id=listing.result_id, result_accessible="error")
            details[listing.result_id] = bad
        else:
            details[listing.result_id] = result

    accessible = sum(1 for d in details.values() if d.result_accessible == "yes")
    login_req = sum(1 for d in details.values() if d.result_accessible == "login_required")
    errors = sum(1 for d in details.values() if d.result_accessible == "error")
    logger.info(
        "Detail results — accessible: %d | login_required: %d | errors: %d",
        accessible, login_req, errors,
    )
    return details
