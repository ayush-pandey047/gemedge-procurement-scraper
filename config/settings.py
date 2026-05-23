import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

BASE_URL = "https://bidplus.gem.gov.in/all-bids"

FILTER_STATUS   = "Bid/RA"
FILTER_OUTCOME  = "Awarded"

MIN_ENTRIES     = 30          
PAGE_TIMEOUT    = 60_000      
NAVIGATION_WAIT = 3_000      
RETRY_LIMIT     = 3           
HEADLESS        = True  

RAW_DATA_DIR        = BASE_DIR / "data" / "raw"
PROCESSED_DATA_DIR  = BASE_DIR / "data" / "processed"
OUTPUT_CSV          = PROCESSED_DATA_DIR / "gem_bids.csv"
OUTPUT_JSON         = PROCESSED_DATA_DIR / "gem_bids.json"
INSIGHTS_FILE       = PROCESSED_DATA_DIR / "insights.txt"

EXPECTED_COLUMNS = [
    "bid_id", "category", "buyer", "quantity", "bid_value",
    "award_date", "winner_name", "winner_price", "num_bidders",
    "vendor_name", "winner_price", "vendor_rank", "vendor_price",
    "status_flag"
]

RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)   # This runs automatically when settings.py is imported.