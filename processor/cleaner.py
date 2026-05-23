
import re
import logging
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


def clean_price(raw: str) -> float:
    """Extract numeric price from messy strings like '₹1,23,456.78' or '1.2 Lakh'."""
    if not raw:
        return 0.0
    raw = str(raw).strip()

    multiplier = 1
    if re.search(r"lakh|lac", raw, re.I):
        multiplier = 100_000
    elif re.search(r"crore|cr\b", raw, re.I):
        multiplier = 10_000_000

    numeric = re.sub(r"[^\d.]", "", raw)
    if not numeric:
        return 0.0
    try:
        return round(float(numeric) * multiplier, 2)
    except ValueError:
        return 0.0


def clean_quantity(raw: str) -> str:
    """Normalize quantity strings."""
    return raw.strip() if raw else ""


def clean_date(raw: str) -> str:
    """Parse date strings into ISO format YYYY-MM-DD."""
    if not raw:
        return ""
    try:
        dt = date_parser.parse(raw, dayfirst=True)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return raw.strip()



_SUFFIX_RE = re.compile(
    r"\b(pvt\.?\s*ltd\.?|private\s+limited|limited|llp|llc|inc\.?|corp\.?|"
    r"enterprises?|trading|solutions?|services?|technologies?)\b",
    re.IGNORECASE,
)
_SPACE_RE = re.compile(r"\s{2,}")


def normalize_vendor_name(name: str) -> str:
    """
    Lowercase, strip legal suffixes (for matching), then title-case.
    Keeps original if empty.
    """
    if not name:
        return ""
    normalized = name.strip()
    normalized = re.sub(r"[^\w\s&.]", " ", normalized)
    normalized = _SPACE_RE.sub(" ", normalized).strip()
    return normalized.title()


def canonical_vendor_name(name: str) -> str:
    """Return a canonical key (lowercase, no suffixes) for dedup matching."""
    name = normalize_vendor_name(name).lower()
    name = _SUFFIX_RE.sub("", name)
    name = _SPACE_RE.sub(" ", name).strip()
    return name


def clean_row(row: dict) -> dict:
    """Apply all cleaning functions to a flat row dict."""
    row = dict(row)  

    row["bid_value"] = clean_price(row.get("bid_value", ""))
    row["winner_price"] = clean_price(row.get("winner_price", ""))
    row["vendor_price"] = clean_price(row.get("vendor_price", ""))
    row["award_date"] = clean_date(row.get("award_date", ""))
    row["winner_name"] = normalize_vendor_name(row.get("winner_name", ""))
    row["vendor_name"] = normalize_vendor_name(row.get("vendor_name", ""))
    row["buyer"] = (row.get("buyer") or "").strip()
    row["category"] = (row.get("category") or "").strip()
    row["quantity"] = clean_quantity(row.get("quantity", ""))

   
    try:
        row["num_bidders"] = int(row.get("num_bidders") or 0)
    except (ValueError, TypeError):
        row["num_bidders"] = 0

    return row
