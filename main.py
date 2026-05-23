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

