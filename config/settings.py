BASE_URL = "https://bidplus.gem.gov.in"
ALL_BIDS_URL = f"{BASE_URL}/all-bids"
BID_RESULT_URL = f"{BASE_URL}/bidding/bid/getBidResultView"
EVALUATION_URL = f"{BASE_URL}/bidding/bid/getEvaluationDetails"


FILTERS = {
    "status": "Bid/RA",        
    "outcome": "Awarded",      
}


NUM_AGENTS = 5                 
NUM_DETAIL_WORKERS = 8          
TARGET_BIDS = 30               
MAX_BIDS = 200                  
PAGE_TIMEOUT = 30_000           
REQUEST_TIMEOUT = 20            
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2                 


OUTPUT_DIR = "data/processed"
RAW_DIR = "data/raw"
CSV_FILENAME = "gem_procurement_data.csv"
JSON_FILENAME = "gem_procurement_data.json"


HEADLESS = True
VIEWPORT = {"width": 1280, "height": 900}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


SCHEMA_FIELDS = [
    "bid_id",
    "category",
    "buyer",
    "quantity",
    "bid_value",
    "award_date",
    "winner_name",
    "winner_price",
    "num_bidders",
    "vendor_name",
    "vendor_rank",
    "vendor_price",
    "status_flag",
    "result_accessible",
    "source_url",
]
