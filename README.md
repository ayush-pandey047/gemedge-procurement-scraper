# GemEdge Procurement Scraper

Automated data extraction system for [GEM BidPlus portal](https://bidplus.gem.gov.in/all-bids).
Built for the GemEdge Data Extraction & Structuring Assignment.

## What It Does
- Filters bids: Status = Bid/RA, Outcome = Awarded
- Extracts 30+ bid entries with full listing details
- Drills into each bid to get winner, L1 price, bidder count
- Deep-extracts evaluation tables (vendor-wise ranks, prices, remarks)
- Cleans, deduplicates, and flags anomalies
- Exports to CSV + JSON
- Generates procurement insights

## Tech Stack
- **Python 3.11** + **Playwright** (async browser automation)
- **Pandas** (data processing)
- **colorlog** (colored terminal logging)

## Setup & Run

### 1. Prerequisites
- Python 3.9+ installed
- Windows PowerShell or Terminal

### 2. Clone and Setup
```powershell
git clone https://github.com/YourUsername/gemedge-procurement-scraper.git
cd gemedge-procurement-scraper
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 3. Run
```powershell
python main.py
```

### 4. Output
- `data/processed/gem_bids.csv`
- `data/processed/gem_bids.json`

## Output Schema
| Column | Description |
|---|---|
| bid_id | GEM Bid/RA number |
| category | Item category |
| buyer | Buyer department |
| quantity | Quantity ordered |
| bid_value | Estimated bid value |
| award_date | Date awarded |
| winner_name | Winning vendor name |
| winner_price | Final awarded price |
| num_bidders | Number of participants |
| vendor_name | Vendor (per evaluation row) |
| vendor_rank | L1/L2/DQ etc. |
| vendor_price | Vendor quoted price |
| status_flag | OK / INCOMPLETE / ANOMALY |

## Notes
- Set `HEADLESS = False` in `config/settings.py` to watch the browser
- GEM portal is slow — expect ~2-3 min for 30 entries
