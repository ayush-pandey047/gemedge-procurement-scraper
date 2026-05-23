import asyncio
import logging
import re
import json
from dataclasses import dataclass
from typing import List, Optional
import aiohttp
from bs4 import BeautifulSoup
from config.settings import BASE_URL, MAX_BIDS, PAGE_TIMEOUT, TARGET_BIDS
from scraper.browser import BrowserManager, safe_goto

logger = logging.getLogger(__name__)
ALL_BIDS_URL = "https://bidplus.gem.gov.in/all-bids"
DATA_URL = "https://bidplus.gem.gov.in/all-bids-data"

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

def _extract_result_id(href: str) -> str:
    m = re.search(r"/getBidResultView/(\d+)", href)
    return m.group(1) if m else ""

def _parse_html(html: str) -> List[BidListing]:
    results = []
    soup = BeautifulSoup(html, "lxml")
    for link in soup.select("a[href*='getBidResultView']"):
        href = link.get("href", "")
        rid = _extract_result_id(href)
        if not rid:
            continue
        l = BidListing()
        l.result_id = rid
        l.source_url = BASE_URL + href if href.startswith("/") else href
        parent = link.find_parent(["tr", "div", "li"])
        if parent:
            cells = parent.find_all("td")
            if len(cells) >= 4:
                l.bid_id = cells[0].get_text(strip=True)
                l.category = cells[1].get_text(strip=True)
                l.buyer = cells[2].get_text(strip=True)
                l.quantity = cells[3].get_text(strip=True)
                l.bid_value = cells[4].get_text(strip=True) if len(cells) > 4 else ""
                l.award_date = cells[5].get_text(strip=True) if len(cells) > 5 else ""
            else:
                txt = parent.get_text("|", strip=True)
                m = re.search(r"GEM/\d{4}/[A-Z]+/\d+", txt)
                l.bid_id = m.group(0) if m else ""
        l.bid_type = "RA" if "/R/" in l.bid_id else "Direct"
        results.append(l)
    return results

def _parse_json(data) -> List[BidListing]:
    """
    Parse GeM's actual Solr-based JSON response.
    Expected structure: data["response"]["response"]["docs"]
    """
    results = []
    
    response_obj = data.get("response", {})
    if not isinstance(response_obj, dict):
        response_obj = {}
    solr_response = response_obj.get("response", {})
    if not isinstance(solr_response, dict):
        solr_response = {}
        
    items = solr_response.get("docs", [])
    if not isinstance(items, list):
        logger.info("JSON 'docs' key is not a list. Structure: %s", list(data.keys()) if isinstance(data, dict) else type(data))
        # Fallback to items if format differs
        items = data if isinstance(data, list) else data.get("data", data.get("bids", data.get("results", [])))
        
    if not isinstance(items, list):
        return results

    for item in items:
        l = BidListing()
        
        # Extract Bid ID
        bid_nums = item.get("b_bid_number") or []
        l.bid_id = str(bid_nums[0]) if bid_nums else str(item.get("bid_number") or item.get("bid_no") or item.get("ra_number") or "")
        
        # Extract Item Category
        cats = item.get("b_category_name") or item.get("bd_category_name") or []
        l.category = str(cats[0]) if cats else str(item.get("item_category") or item.get("category") or item.get("item_name") or "")
        
        # Extract Buyer Ministry & Department
        min_name = (item.get("ba_official_details_minName") or [""])[0]
        dept_name = (item.get("ba_official_details_deptName") or [""])[0]
        if min_name and dept_name:
            l.buyer = f"{min_name}\n{dept_name}"
        else:
            l.buyer = dept_name or min_name or str(item.get("buyer_name") or item.get("ministry") or item.get("department") or "")
            
        # Extract Quantity
        quants = item.get("b_total_quantity") or []
        l.quantity = str(quants[0]) if quants else str(item.get("quantity") or item.get("qty") or "")
        
        # Extract Estimated Bid Value (not directly in Solr list, but detail page gets it)
        l.bid_value = str(item.get("bid_value") or item.get("amount") or item.get("total_value") or "")
        
        # Extract Award / End Date
        end_dates = item.get("final_end_date_sort") or []
        l.award_date = str(end_dates[0]) if end_dates else str(item.get("award_date") or item.get("end_date") or item.get("closing_date") or "")
        
        # Extract Result ID
        href = str(item.get("result_url") or item.get("bid_result_url") or "")
        l.result_id = _extract_result_id(href)
        if not l.result_id:
            l.result_id = str(item.get("id") or item.get("bid_id") or "")
            
        # Build Source URL
        if l.result_id:
            l.source_url = f"{BASE_URL}/bidding/bid/getBidResultView/{l.result_id}"
            
        # Determine Bid Type
        b_bid_type = (item.get("b_bid_type") or [0])[0]
        if b_bid_type == 5 or b_bid_type == 2 or "/R/" in l.bid_id:
            l.bid_type = "RA"
        else:
            l.bid_type = "Direct"
            
        if l.bid_id or l.result_id:
            results.append(l)
            
    return results

async def run_listing_agents(browser_manager: BrowserManager) -> List[BidListing]:
    """
    Main listing gatherer.
    1. Obtains anonymous session cookies and CSRF token from BrowserManager.
    2. Directly queries the /all-bids-data endpoint page-by-page.
    3. Leverages aiohttp for high speed and light memory footprint.
    """
    all_listings: List[BidListing] = []
    seen: set = set()

    # Get active session cookies from BrowserManager
    cookies_dict = await browser_manager.get_cookies_dict()
    csrf_token = cookies_dict.get("csrf_gem_cookie")

    if not csrf_token:
        logger.error("Could not obtain 'csrf_gem_cookie' from Playwright session.")
        return []

    logger.info("Harvested session cookies and CSRF token successfully.")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://bidplus.gem.gov.in/all-bids",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    }

    async with aiohttp.ClientSession(cookies=cookies_dict) as session:
        page_num = 1
        
        while len(all_listings) < TARGET_BIDS and len(all_listings) < MAX_BIDS:
            logger.info("Programmatic query: Requesting page %d of awarded bids...", page_num)
            
            # Formulate the payload asking for Awarded bids (status: bidrastatus, byStatus: bid_awarded)
            payload_data = {
                "page": page_num,
                "param": {
                    "searchBid": "",
                    "searchType": "fullText"
                },
                "filter": {
                    "bidStatusType": "bidrastatus",
                    "byType": "all",
                    "highBidValue": "",
                    "byEndDate": {
                        "from": "",
                        "to": ""
                    },
                    "sort": "Bid-End-Date-Latest",
                    "byStatus": "bid_awarded"
                }
            }

            data = {
                "payload": json.dumps(payload_data),
                "csrf_bd_gem_nk": csrf_token
            }

            try:
                async with session.post(DATA_URL, data=data, headers=headers, timeout=20) as response:
                    if response.status != 200:
                        logger.error("POST request failed with status %d", response.status)
                        break
                        
                    text = await response.text()
                    res_json = json.loads(text)
                    
                    if res_json.get("code") != 200:
                        logger.warning("GeM responded with non-200 code inside payload: %s", res_json)
                        break
                        
                    listings = _parse_json(res_json)
                    logger.info("Successfully fetched %d listings from page %d", len(listings), page_num)
                    
                    if not listings:
                        logger.info("No further listings found on page %d. Stopping.", page_num)
                        break
                        
                    new_count = 0
                    for l in listings:
                        key = l.result_id or l.bid_id
                        if key and key not in seen:
                            seen.add(key)
                            all_listings.append(l)
                            new_count += 1
                            
                    logger.info("Page %d added %d new listings (Total collected: %d/%d)", 
                                page_num, new_count, len(all_listings), TARGET_BIDS)
                    
                    page_num += 1
                    
                    # Polite sleep between programmatic requests to be an ethical scraper
                    await asyncio.sleep(1.0)
                    
            except Exception as e:
                logger.error("Error during programmatic replay request: %s", e)
                break

    logger.info("Listing collection complete. Total unique listings gathered: %d", len(all_listings))
    return all_listings
