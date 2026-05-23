"""
main.py — GemEdge Procurement Scraper
Entry point — orchestrates all agents and processors.

Pipeline:
  1. [ListingAgents x5]  → parallel listing scrape (filter + extract)
  2. [DetailWorkers x8]  → async HTTP detail fetch (winner, L1 price)
  3. [EvalWorkers x8]    → async HTTP evaluation fetch (L1/L2/DQ ranks)
  4. [Processor]         → clean, dedup, anomaly detection
  5. [Exporter]          → CSV + JSON output
  6. [Insights]          → summary analysis

No login required. Anonymous ci_session cookie from /all-bids is sufficient
for ~83% of bids. The remaining 17% (SSO-gated Direct Bids) are flagged.
"""

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import asdict

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from config.settings import TARGET_BIDS, OUTPUT_DIR, NUM_AGENTS
from scraper.browser import BrowserManager
from scraper.listing_scraper import run_listing_agents, BidListing
from scraper.detail_scraper import fetch_all_details
from scraper.evaluation_scraper import fetch_all_evaluations
from processor.cleaner import clean_row
from processor.deduplicator import deduplicate_bids, deduplicate_vendors_in_rows
from processor.anomaly_detector import flag_anomalies
from output.exporter import save_csv, save_json, save_raw_json
from analysis.insights import compute_insights, print_insights

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def _merge_to_rows(
    listings: list[BidListing],
    details: dict,
    evaluations: dict,
) -> list[dict]:
    """
    Merge listing + detail + evaluation data into flat rows.
    One row per vendor per bid (so L1, L2, L3 each get their own row).
    If no evaluation vendors found, create one row per listing using detail data.
    """
    rows = []

    for listing in listings:
        rid = listing.result_id
        detail = details.get(rid)
        eval_detail = evaluations.get(rid)

        base = {
            "bid_id": listing.bid_id,
            "category": listing.category,
            "buyer": listing.buyer,
            "quantity": listing.quantity,
            "bid_value": listing.bid_value,
            "award_date": listing.award_date,
            "source_url": listing.source_url,
            "result_accessible": detail.result_accessible if detail else "not_fetched",
            "winner_name": detail.winner_name if detail else "",
            "winner_price": detail.winner_price if detail else "",
            "num_bidders": detail.num_bidders if detail else 0,
        }

       
        if eval_detail and eval_detail.vendors:
            for vendor in eval_detail.vendors:
                row = dict(base)
                row["vendor_name"] = vendor.vendor_name
                row["vendor_rank"] = vendor.vendor_rank
                row["vendor_price"] = vendor.vendor_price
                rows.append(row)
        else:
           
            row = dict(base)
            row["vendor_name"] = detail.winner_name if detail else ""
            row["vendor_rank"] = "L1"
            row["vendor_price"] = detail.winner_price if detail else ""
            rows.append(row)

    return rows


async def main():
    start_time = time.time()
    console.print("\n[bold cyan]GemEdge Procurement Scraper[/bold cyan]")
    console.print(f"Target: ≥{TARGET_BIDS} awarded bids | {NUM_AGENTS} listing agents\n")

   
    console.print("[bold yellow]Phase 1/4:[/bold yellow] Launching listing agents...")
    browser = BrowserManager(num_contexts=NUM_AGENTS)
    await browser.start()

    try:
        listings = await run_listing_agents(browser)
    finally:
        await browser.stop()

    console.print(f"  ✓ Collected [green]{len(listings)}[/green] bid listings")

    if not listings:
        console.print("[red]No listings found. Check network or filters.[/red]")
        return


    raw_listings = [asdict(l) if hasattr(l, '__dataclass_fields__') else vars(l) for l in listings]
    save_raw_json(raw_listings, "listings")

    
    console.print("[bold yellow]Phase 2/4:[/bold yellow] Fetching bid result details...")
    cookies = await browser.get_cookies_dict() if False else {}
    
    temp_browser = BrowserManager(num_contexts=1)
    await temp_browser.start()
    cookies = await temp_browser.get_cookies_dict()
    await temp_browser.stop()

    details = await fetch_all_details(listings, cookies)
    console.print(f"  ✓ Details fetched for [green]{len(details)}[/green] bids")

    console.print("[bold yellow]Phase 3/4:[/bold yellow] Fetching evaluation details (L1/L2/DQ)...")
    result_ids = [l.result_id for l in listings if l.result_id]
    evaluations = await fetch_all_evaluations(result_ids, cookies)
    console.print(f"  ✓ Evaluations fetched for [green]{len(evaluations)}[/green] bids")

    
    console.print("[bold yellow]Phase 4/4:[/bold yellow] Processing, cleaning, and saving...")
    rows = _merge_to_rows(listings, details, evaluations)
    console.print(f"  → Merged rows: {len(rows)}")


    rows = [clean_row(r) for r in rows]

    rows = deduplicate_bids(rows)
    rows = deduplicate_vendors_in_rows(rows)

    rows = flag_anomalies(rows)

    csv_path = save_csv(rows)
    json_path = save_json(rows)
    console.print(f"  ✓ CSV:  [green]{csv_path}[/green]")
    console.print(f"  ✓ JSON: [green]{json_path}[/green]")

    insights = compute_insights(rows)
    save_raw_json(insights, "insights")
    print_insights(insights)

    elapsed = round(time.time() - start_time, 1)
    console.print(f"[bold green]Done in {elapsed}s[/bold green] — {len(rows)} rows exported.\n")


if __name__ == "__main__":
    asyncio.run(main())
