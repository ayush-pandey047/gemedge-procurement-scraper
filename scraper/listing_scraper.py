import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import Page

from config.settings import (
    ALL_BIDS_URL,
    BASE_URL,
    FILTERS,
    NUM_AGENTS,
    MAX_BIDS,
    TARGET_BIDS,
    PAGE_TIMEOUT,
)
from scraper.browser import BrowserManager, safe_goto

logger = logging.getLogger(__name__)


@dataclass
class BidListing:
    bid_id: str = ""
    category: str = ""
    buyer: str = ""
    quantity: str = ""
    bid_value: str = ""
    award_date: str = ""
    bid_type: str = ""          
    source_url: str = ""
    result_id: str = ""         
    raw_html: str = ""



def _extract_bid_id(text: str) -> str:
    m = re.search(r"GEM/\d{4}/[A-Z]+/\d+", text)
    return m.group(0) if m else text.strip()


def _extract_result_id(href: str) -> str:
    """Pull the numeric ID from a getBidResultView URL."""
    m = re.search(r"/getBidResultView/(\d+)", href)
    return m.group(1) if m else ""


def _parse_bid_card(card_soup) -> Optional[BidListing]:
    """Parse a single bid card from the listing HTML."""
    try:
        listing = BidListing()

     
        bid_id_el = card_soup.select_one(".bid-id, [class*='bid_no'], [class*='bidNo']")
        if not bid_id_el:
            bid_id_el = card_soup.find(string=re.compile(r"GEM/\d{4}"))
        listing.bid_id = _extract_bid_id(bid_id_el.get_text() if bid_id_el else "")


        cat_el = card_soup.select_one(
            ".category, [class*='item'], [class*='category'], td:nth-child(2)"
        )
        listing.category = cat_el.get_text(strip=True) if cat_el else ""


        buyer_el = card_soup.select_one(
            ".buyer, [class*='buyer'], [class*='ministry'], [class*='department']"
        )
        listing.buyer = buyer_el.get_text(strip=True) if buyer_el else ""


        qty_el = card_soup.select_one("[class*='quantity'], [class*='qty']")
        listing.quantity = qty_el.get_text(strip=True) if qty_el else ""


        val_el = card_soup.select_one(
            "[class*='value'], [class*='amount'], [class*='bid_val']"
        )
        listing.bid_value = val_el.get_text(strip=True) if val_el else ""


        date_el = card_soup.select_one(
            "[class*='date'], [class*='award'], [class*='end_date']"
        )
        listing.award_date = date_el.get_text(strip=True) if date_el else ""


        result_link = card_soup.select_one("a[href*='getBidResultView']")
        if result_link:
            href = result_link.get("href", "")
            listing.result_id = _extract_result_id(href)
            listing.source_url = BASE_URL + href if href.startswith("/") else href

   
        listing.bid_type = "RA" if "/R/" in listing.bid_id else "Direct"

        return listing if listing.bid_id else None
    except Exception as exc:
        logger.debug("Card parse error: %s", exc)
        return None


def _parse_table_row(row_soup, headers: list) -> Optional[BidListing]:
    """Parse a <tr> from a table-style listing."""
    try:
        cells = [td.get_text(strip=True) for td in row_soup.find_all("td")]
        if not cells or len(cells) < 3:
            return None

        listing = BidListing()
        for i, h in enumerate(headers):
            if i >= len(cells):
                break
            hl = h.lower()
            if "bid" in hl and "no" in hl:
                listing.bid_id = _extract_bid_id(cells[i])
            elif "category" in hl or "item" in hl:
                listing.category = cells[i]
            elif "buyer" in hl or "ministry" in hl or "dept" in hl:
                listing.buyer = cells[i]
            elif "qty" in hl or "quantity" in hl:
                listing.quantity = cells[i]
            elif "value" in hl or "amount" in hl:
                listing.bid_value = cells[i]
            elif "date" in hl or "award" in hl:
                listing.award_date = cells[i]


        result_link = row_soup.select_one("a[href*='getBidResultView']")
        if result_link:
            href = result_link.get("href", "")
            listing.result_id = _extract_result_id(href)
            listing.source_url = BASE_URL + href if href.startswith("/") else href

        listing.bid_type = "RA" if "/R/" in listing.bid_id else "Direct"
        return listing if listing.bid_id else None
    except Exception as exc:
        logger.debug("Row parse error: %s", exc)
        return None


class ListingAgent:
    """
    One agent = one Playwright page.
    Agents are assigned page numbers and scrape concurrently.
    """

    def __init__(self, agent_id: int, page: Page):
        self.agent_id = agent_id
        self.page = page

    async def _apply_filters(self) -> None:
        """Navigate to /all-bids and apply Status + Outcome filters."""
        logger.info("[Agent %d] Navigating to %s", self.agent_id, ALL_BIDS_URL)
        await safe_goto(self.page, ALL_BIDS_URL)
        await self.page.wait_for_timeout(2000)


        try:
            status_sel = self.page.locator(
                "select[name*='status'], select[id*='status'], select[name*='bid_type']"
            ).first
            await status_sel.select_option(label=FILTERS["status"])
            await self.page.wait_for_timeout(500)
        except Exception:
            logger.debug("[Agent %d] Status filter select not found — skipping", self.agent_id)

    
        try:
            outcome_sel = self.page.locator(
                "select[name*='outcome'], select[id*='outcome'], select[name*='award']"
            ).first
            await outcome_sel.select_option(label=FILTERS["outcome"])
            await self.page.wait_for_timeout(500)
        except Exception:
            logger.debug("[Agent %d] Outcome filter select not found — trying URL params", self.agent_id)

            filtered_url = (
                f"{ALL_BIDS_URL}?"
                f"bid_status=awarded&bid_type=ra"
            )
            await safe_goto(self.page, filtered_url)


        try:
            btn = self.page.locator(
                "button[type='submit'], input[type='submit'], button:has-text('Search'), button:has-text('Filter')"
            ).first
            await btn.click()
            await self.page.wait_for_load_state("domcontentloaded")
            await self.page.wait_for_timeout(2000)
        except Exception:
            logger.debug("[Agent %d] No submit button found", self.agent_id)

    async def scrape_page(self, page_num: int) -> list[BidListing]:
        """Scrape a single page number and return listings."""
        results = []
        try:
            if page_num > 1:
             
                try:
                    pager = self.page.locator(f"a[href*='page={page_num}'], a:has-text('{page_num}')").first
                    await pager.click()
                    await self.page.wait_for_load_state("domcontentloaded")
                    await self.page.wait_for_timeout(1500)
                except Exception:
                    page_url = f"{ALL_BIDS_URL}?page={page_num}&bid_status=awarded&bid_type=ra"
                    success = await safe_goto(self.page, page_url)
                    if not success:
                        return results

            html = await self.page.content()
            soup = BeautifulSoup(html, "lxml")


            cards = soup.select(".bid-card, [class*='bid_card'], [class*='bid-item'], .card")
            if cards:
                for card in cards:
                    listing = _parse_bid_card(card)
                    if listing:
                        results.append(listing)
                logger.info("[Agent %d] Page %d → %d cards", self.agent_id, page_num, len(results))
                return results

            table = soup.select_one("table.table, table#bidsTable, table")
            if table:
                headers = [th.get_text(strip=True) for th in table.select("thead th, tr th")]
                rows = table.select("tbody tr")
                for row in rows:
                    listing = _parse_table_row(row, headers)
                    if listing:
                        results.append(listing)
                logger.info("[Agent %d] Page %d → %d rows", self.agent_id, page_num, len(results))
                return results


            result_links = soup.select("a[href*='getBidResultView']")
            seen = set()
            for link in result_links:
                href = link.get("href", "")
                rid = _extract_result_id(href)
                if rid and rid not in seen:
                    seen.add(rid)
                    listing = BidListing()
                    listing.result_id = rid
                    listing.source_url = BASE_URL + href if href.startswith("/") else href
     
                    parent = link.find_parent(["tr", "div", "li"])
                    if parent:
                        text = parent.get_text(" | ", strip=True)
                        listing.bid_id = _extract_bid_id(text)
                    results.append(listing)

            logger.info("[Agent %d] Page %d → %d links (fallback)", self.agent_id, page_num, len(results))

        except Exception as exc:
            logger.error("[Agent %d] Page %d error: %s", self.agent_id, page_num, exc)

        return results



async def run_listing_agents(browser_manager: BrowserManager) -> list[BidListing]:
    """
    Spawn NUM_AGENTS parallel listing agents.
    Agent 0 applies filters and reports total pages.
    All agents then divide pages among themselves.
    """
    all_listings: list[BidListing] = []
    seen_ids: set[str] = set()


    page0 = await browser_manager.new_page(0)
    agent0 = ListingAgent(0, page0)
    await agent0._apply_filters()

    html = await page0.content()
    soup = BeautifulSoup(html, "lxml")


    total_pages = 1
    pager = soup.select(".pagination a, [class*='pager'] a, [class*='page'] a")
    for el in pager:
        try:
            n = int(re.sub(r"[^\d]", "", el.get_text()))
            total_pages = max(total_pages, n)
        except ValueError:
            pass
    total_pages = min(total_pages, (MAX_BIDS // 10) + 1)  
    logger.info("Total listing pages detected: %d", total_pages)


    page1_listings = await agent0.scrape_page(1)
    for l in page1_listings:
        key = l.result_id or l.bid_id
        if key and key not in seen_ids:
            seen_ids.add(key)
            all_listings.append(l)
    await page0.close()

    if len(all_listings) >= MAX_BIDS or total_pages <= 1:
        return all_listings[:MAX_BIDS]

    remaining_pages = list(range(2, total_pages + 1))
    if not remaining_pages:
        return all_listings


    n_agents = min(NUM_AGENTS, len(remaining_pages))
    chunks = [remaining_pages[i::n_agents] for i in range(n_agents)]

    async def agent_worker(agent_id: int, page_nums: list[int]):
        page = await browser_manager.new_page(agent_id)
        agent = ListingAgent(agent_id, page)
        
        await agent._apply_filters()
        worker_results = []
        for pn in page_nums:
            if len(all_listings) + len(worker_results) >= MAX_BIDS:
                break
            listings = await agent.scrape_page(pn)
            worker_results.extend(listings)
        await page.close()
        return worker_results

    tasks = [agent_worker(i + 1, chunks[i]) for i in range(n_agents)]
    agent_results = await asyncio.gather(*tasks, return_exceptions=True)

    for batch in agent_results:
        if isinstance(batch, Exception):
            logger.error("Agent error: %s", batch)
            continue
        for listing in batch:
            key = listing.result_id or listing.bid_id
            if key and key not in seen_ids and len(all_listings) < MAX_BIDS:
                seen_ids.add(key)
                all_listings.append(listing)

    logger.info("Total listings collected: %d", len(all_listings))
    return all_listings
