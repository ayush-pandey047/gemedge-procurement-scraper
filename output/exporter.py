
import json
import logging
import os
from datetime import datetime

import pandas as pd

from config.settings import (
    OUTPUT_DIR,
    RAW_DIR,
    CSV_FILENAME,
    JSON_FILENAME,
    SCHEMA_FIELDS,
)

logger = logging.getLogger(__name__)


def _ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)


def _enforce_schema(rows: list[dict]) -> list[dict]:
    """Ensure every row has all required schema fields (fill missing with empty string)."""
    result = []
    for row in rows:
        clean = {f: row.get(f, "") for f in SCHEMA_FIELDS}
        result.append(clean)
    return result


def save_csv(rows: list[dict], filename: str = CSV_FILENAME) -> str:
    _ensure_dirs()
    rows = _enforce_schema(rows)
    df = pd.DataFrame(rows, columns=SCHEMA_FIELDS)
    path = os.path.join(OUTPUT_DIR, filename)
    df.to_csv(path, index=False, encoding="utf-8")
    logger.info("CSV saved: %s (%d rows)", path, len(df))
    return path


def save_json(rows: list[dict], filename: str = JSON_FILENAME) -> str:
    _ensure_dirs()
    rows = _enforce_schema(rows)
    meta = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_records": len(rows),
        "schema": SCHEMA_FIELDS,
        "data": rows,
    }
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    logger.info("JSON saved: %s (%d records)", path, len(rows))
    return path


def save_raw_json(data: object, tag: str) -> str:
    """Save raw scraper output for debugging/reproducibility."""
    _ensure_dirs()
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(RAW_DIR, f"{tag}_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return path
