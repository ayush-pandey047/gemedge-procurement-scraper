import logging
import json
import re
import requests
import pdfplumber
from pathlib import Path
from config.settings import RAW_DATA_DIR

logger = logging.getLogger(__name__)


def download_pdf(url: str, save_path: Path) -> bool:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
        r = requests.get(url, headers=headers, timeout=30, stream=True)
        if r.status_code == 200:
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return True
        logger.warning(f"Bad response {r.status_code} for {url}")
        return False
    except Exception as e:
        logger.error(f"Download failed {url}: {e}")
        return False


def parse_ra_pdf(pdf_path: Path) -> dict:
    """
    Extract all available fields from GEM RA specification PDF.
    Winner data requires portal login — flagged accordingly.
    """
    result = {
        "ra_number"     : "",
        "ra_start_date" : "",
        "ra_end_date"   : "",
        "ministry"      : "",
        "department"    : "",
        "organisation"  : "",
        "contract_period": "",
        "mse_exemption" : "",
        "winner_name"   : "REQUIRES_LOGIN",
        "winner_price"  : "REQUIRES_LOGIN",
        "num_bidders"   : "REQUIRES_LOGIN",
        "vendors"       : []
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Collect all table rows as key-value pairs
            for pg in pdf.pages:
                tables = pg.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 2:
                            continue
                        key = str(row[0] or "").strip().lower()
                        val = str(row[1] or "").strip() if row[1] else ""
                        if not key or not val:
                            continue

                        if "ra number" in key:
                            result["ra_number"] = val
                        elif "ra start" in key:
                            result["ra_start_date"] = val
                        elif "ra end" in key:
                            result["ra_end_date"] = val
                        elif "ministry" in key or "state name" in key:
                            result["ministry"] = val
                        elif "department name" in key:
                            result["department"] = val
                        elif "organisation name" in key:
                            result["organisation"] = val
                        elif "contract period" in key:
                            result["contract_period"] = val
                        elif "mse exemption" in key:
                            result["mse_exemption"] = val

    except Exception as e:
        logger.error(f"PDF parse error {pdf_path}: {e}")

    return result


async def scrape_all_details(page, listings: list[dict]) -> list[dict]:
    pdf_dir = RAW_DATA_DIR / "pdfs"
    pdf_dir.mkdir(exist_ok=True)

    enriched = []
    for i, entry in enumerate(listings, 1):
        bid_id  = entry.get("bid_id", f"bid_{i}")
        ra_url  = entry.get("ra_pdf_url", "")
        logger.info(f"Detail [{i}/{len(listings)}]: {bid_id}")

        if not ra_url:
            logger.warning(f"  No RA PDF URL for {bid_id}")
            entry.update({
                "ra_number": "", "ra_start_date": "", "ra_end_date": "",
                "ministry": "", "department": "", "organisation": "",
                "contract_period": "", "mse_exemption": "",
                "winner_name": "REQUIRES_LOGIN",
                "winner_price": "REQUIRES_LOGIN",
                "num_bidders": "REQUIRES_LOGIN",
                "vendors": []
            })
            enriched.append(entry)
            continue

        safe_name = re.sub(r"[^\w]", "_", bid_id) + ".pdf"
        pdf_path  = pdf_dir / safe_name

        # Reuse cached PDF if already downloaded
        if not pdf_path.exists():
            ok = download_pdf(ra_url, pdf_path)
            if not ok:
                entry.update({
                    "winner_name": "DOWNLOAD_FAILED",
                    "winner_price": "", "num_bidders": "", "vendors": []
                })
                enriched.append(entry)
                continue

        parsed = parse_ra_pdf(pdf_path)
        entry.update(parsed)
        logger.info(f"  RA: {parsed['ra_number']} | Ministry: {parsed['ministry'][:40]}")
        enriched.append(entry)

    raw_path = RAW_DATA_DIR / "raw_with_details.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved detail data to {raw_path}")

    return enriched
