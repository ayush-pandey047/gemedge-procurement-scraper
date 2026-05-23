import asyncio
import logging
import colorlog
import pandas as pd

from scraper.browser import BrowserManager
from scraper.listing_scraper import scrape_listings
from scraper.detail_scraper import scrape_all_details
from scraper.evaluation_scraper import scrape_all_evaluations
from processor.cleaner import clean_dataframe
from processor.deduplicator import deduplicate_bids, flag_duplicate_vendors
from processor.anomaly_detector import flag_winner_not_lowest, flag_large_l1_l2_gap
from output.exporter import export
from analysis.insights import generate_insights


def setup_logging():
    """
    Configure colorlog so we get nicely colored terminal output:
      DEBUG   → cyan
      INFO    → green
      WARNING → yellow
      ERROR   → red
    """
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG"   : "cyan",
            "INFO"    : "green",
            "WARNING" : "yellow",
            "ERROR"   : "red",
            "CRITICAL": "bold_red",
        }
    ))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


async def run_pipeline():
    """Full scraping + processing pipeline."""
    logger = logging.getLogger("main")
    logger.info("╔══════════════════════════════════════╗")
    logger.info("║  GemEdge Procurement Scraper v1.0    ║")
    logger.info("╚══════════════════════════════════════╝")

    async with BrowserManager() as bm:
        page = await bm.new_page()

        logger.info("STEP 1 & 2: Scraping bid listings...")
        listings = await scrape_listings(page)
        if not listings:
            logger.error("No listings scraped. Exiting.")
            return
        logger.info(f"Collected {len(listings)} listing entries.")


        logger.info("STEP 3: Scraping detail pages (winner, L1 price, bidder count)...")
        listings_with_details = await scrape_all_details(page, listings)

       
        logger.info("STEP 4: Scraping evaluation details (vendor-wise data)...")
        flat_rows = await scrape_all_evaluations(page, listings_with_details)

   
    df = pd.DataFrame(flat_rows)
    logger.info(f"Raw DataFrame: {len(df)} rows × {len(df.columns)} columns")

   
    logger.info("PROCESSING: Cleaning data...")
    df = clean_dataframe(df)

   
    logger.info("PROCESSING: Deduplicating...")
    df = deduplicate_bids(df)
    df = flag_duplicate_vendors(df)

    
    logger.info("PROCESSING: Detecting anomalies...")
    df = flag_winner_not_lowest(df)
    df = flag_large_l1_l2_gap(df)

   
    logger.info("OUTPUT: Exporting to CSV and JSON...")
    export(df)

   
    logger.info("ANALYSIS: Generating insights...")
    generate_insights(df)

    logger.info("Pipeline complete!")


if __name__ == "__main__":
    setup_logging()
    asyncio.run(run_pipeline())