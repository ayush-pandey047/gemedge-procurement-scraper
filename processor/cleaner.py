import re
import logging
import pandas as pd

logger = logging.getLogger(__name__)


def clean_price(value: str) -> float | None:
    """
    Convert a messy price string to a float.
    Examples:
        '₹1,23,456.78'  → 123456.78
        '1,23,456'      → 123456.0
        'N/A'           → None
        ''              → None
    """
    if not value or str(value).strip() in ("", "N/A", "-", "NA", "ERROR"):
        return None
    cleaned = re.sub(r"[₹,\s]", "", str(value))
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_vendor_name(name: str) -> str:
    """
    Normalize vendor names so duplicates can be detected:
      - Strip leading/trailing whitespace
      - Collapse internal whitespace
      - Title case (GEM sometimes returns ALL CAPS)
      - Remove common suffixes that are sometimes included, sometimes not
        (Pvt Ltd, Private Limited, etc.) — we keep them but standardize
    """
    if not name or str(name).strip() in ("", "N/A", "ERROR"):
        return ""

    name = str(name).strip()
    name = re.sub(r"\s+", " ", name) 
    name = name.title()              

   
    replacements = {
        r"\bPvt\.?\s*Ltd\.?$": "Pvt Ltd",
        r"\bPrivate Limited$": "Pvt Ltd",
        r"\bLimited$": "Ltd",
        r"\bLlp$": "LLP",
    }
    for pattern, replacement in replacements.items():
        name = re.sub(pattern, replacement, name, flags=re.IGNORECASE)

    return name.strip()


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply all cleaning operations to the full DataFrame.
    Returns a cleaned DataFrame.
    """
    logger.info(f"Cleaning DataFrame with {len(df)} rows...")

   
    text_cols = ["bid_id", "category", "buyer", "remarks"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({"nan": "", "None": "", "ERROR": ""})

   
    for col in ["winner_name", "vendor_name"]:
        if col in df.columns:
            df[col] = df[col].apply(normalize_vendor_name)


    for col in ["winner_price", "vendor_price", "bid_value"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_price)

    
    for col in ["quantity", "num_bidders"]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(r"[^\d.]", "", regex=True),
                errors="coerce"
            )

   
    if "award_date" in df.columns:
        df["award_date"] = pd.to_datetime(
            df["award_date"], dayfirst=True, errors="coerce"
        ).dt.strftime("%Y-%m-%d")

    
    df["status_flag"] = "OK"
    missing_mask = df[["winner_name", "winner_price"]].isnull().any(axis=1)
    df.loc[missing_mask, "status_flag"] = "INCOMPLETE"

    logger.info(
        f"Cleaning done. "
        f"{missing_mask.sum()} rows flagged INCOMPLETE out of {len(df)}."
    )
    return df