import logging
import json
import re
import asyncio
import requests
import pdfplumber
from pathlib import Path
from playwright.async_api import Page
from config.settings import RAW_DATA_DIR, PAGE_TIMEOUT, NAVIGATION_WAIT

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
    result = {
        "ra_number": "", "ra_start_date": "", "ra_end_date": "",
        "ministry": "", "department": "", "organisation": "",
        "contract_period": "", "mse_exemption": "",
    }
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for pg in pdf.pages:
                for table in (pg.extract_tables() or []):
                    for row in table:
                        if not row or len(row) < 2:
                            continue
                        key = str(row[0] or "").strip().lower()
                        val = str(row[1] or "").strip() if row[1] else ""
                        if not key or not val:
                            continue
                        if "ra number" in key:        result["ra_number"] = val
                        elif "ra start" in key:       result["ra_start_date"] = val
                        elif "ra end" in key:         result["ra_end_date"] = val
                        elif "ministry" in key:       result["ministry"] = val
                        elif "department name" in key: result["department"] = val
                        elif "organisation" in key:   result["organisation"] = val
                        elif "contract period" in key: result["contract_period"] = val
                        elif "mse exemption" in key:  result["mse_exemption"] = val
    except Exception as e:
        logger.error(f"PDF parse error {pdf_path}: {e}")
    return result


async def scrape_result_page(page: Page, result_url: str) -> dict:
    """Try to get winner data from getBidResultView HTML page."""
    empty = {"winner_name": "REQUIRES_LOGIN", "winner_price": "", "num_bidders": ""}
    if not result_url:
        return empty
    try:
        await page.goto(result_url, wait_until="networkidle", timeout=PAGE_TIMEOUT)
        await asyncio.sleep(2)

        # If redirected away from bidplus, it needs login
        if "bidplus.gem.gov.in" not in page.url:
            logger.warning(f"  Redirected to {page.url} — login required")
            return empty

        text = await page.evaluate("() => document.body.innerText")
        data = {"winner_name": "", "winner_price": "", "num_bidders": ""}

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for i, line in enumerate(lines):
            ll = line.lower()
            if "winner" in ll or "l1 vendor" in ll or "awarded to" in ll:
                if i+1 < len(lines): data["winner_name"] = lines[i+1]
            if "l1 price" in ll or "awarded price" in ll or "final price" in ll:
                if i+1 < len(lines): data["winner_price"] = lines[i+1]
            if "total bidder" in ll or "participating" in ll or "no. of bid" in ll:
                if i+1 < len(lines): data["num_bidders"] = lines[i+1]

        if not data["winner_name"]:
            data["winner_name"] = "REQUIRES_LOGIN"
        return data
    except Exception as e:
        logger.warning(f"  Result page error: {e}")
        return empty


async def scrape_all_details(page: Page, listings: list[dict]) -> list[dict]:
    pdf_dir = RAW_DATA_DIR / "pdfs"
    pdf_dir.mkdir(exist_ok=True)

    enriched = []
    for i, entry in enumerate(listings, 1):
        bid_id     = entry.get("bid_id", f"bid_{i}")
        ra_url     = entry.get("ra_pdf_url", "")
        result_url = entry.get("result_url", "")
        logger.info(f"Detail [{i}/{len(listings)}]: {bid_id}")

        # 1. Try HTML result page first
        result_data = await scrape_result_page(page, result_url)
        entry.update(result_data)

        # 2. Parse RA PDF for extra metadata
        if ra_url:
            safe_name = re.sub(r"[^\w]", "_", bid_id) + ".pdf"
            pdf_path  = pdf_dir / safe_name
            if not pdf_path.exists():
                download_pdf(ra_url, pdf_path)
            if pdf_path.exists():
                parsed = parse_ra_pdf(pdf_path)
                # Only fill fields not already set from card text
                for k, v in parsed.items():
                    if not entry.get(k) and v:
                        entry[k] = v

        logger.info(f"  Winner: {entry.get('winner_name')} | Price: {entry.get('winner_price')}")
        enriched.append(entry)
        await asyncio.sleep(NAVIGATION_WAIT / 1000)

    raw_path = RAW_DATA_DIR / "raw_with_details.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved detail data to {raw_path}")
    return enriched
