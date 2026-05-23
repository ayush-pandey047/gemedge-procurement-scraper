
import logging
import pandas as pd
from config.settings import OUTPUT_CSV, OUTPUT_JSON

logger = logging.getLogger(__name__)


def export(df: pd.DataFrame) -> None:
    """Save DataFrame to CSV and JSON output files."""

    #CSV Export 
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    logger.info(f"CSV saved: {OUTPUT_CSV}  ({len(df)} rows)")

    #JSON Export
    df.to_json(
        OUTPUT_JSON,
        orient="records",  
        indent=2,
        force_ascii=False, 
        date_format="iso",
    )
    logger.info(f"JSON saved: {OUTPUT_JSON}  ({len(df)} rows)")