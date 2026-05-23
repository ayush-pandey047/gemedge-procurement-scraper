import logging
import json
from config.settings import RAW_DATA_DIR

logger = logging.getLogger(__name__)


async def scrape_all_evaluations(page, listings: list[dict]) -> list[dict]:
    flat_rows = []

    for entry in listings:
        vendors = entry.pop("vendors", [])

        if not vendors:
            row = dict(entry)
            row.update({
                "vendor_name" : "",
                "vendor_rank" : "",
                "vendor_price": "",
                "disqualified": False,
                "remarks"     : "",
            })
            flat_rows.append(row)
        else:
            for vendor in vendors:
                row = dict(entry)
                row.update(vendor)
                flat_rows.append(row)

    raw_path = RAW_DATA_DIR / "raw_evaluations.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(flat_rows, f, indent=2, ensure_ascii=False)
    logger.info(f"Evaluation flat rows saved: {len(flat_rows)}")
    return flat_rows
