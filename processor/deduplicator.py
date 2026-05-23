 import logging
from thefuzz import fuzz
 
from processor.cleaner import canonical_vendor_name
 
logger = logging.getLogger(__name__)
 
FUZZY_THRESHOLD = 85  
 
 
def deduplicate_bids(rows: list[dict]) -> list[dict]:
    """Remove duplicate bid_id rows, keeping the most complete record."""
    seen: dict[str, dict] = {}
    for row in rows:
        bid_id = row.get("bid_id", "")
        if not bid_id:
            continue
        if bid_id not in seen:
            seen[bid_id] = row
        else:
            
            existing = seen[bid_id]
            if sum(bool(v) for v in row.values()) > sum(bool(v) for v in existing.values()):
                seen[bid_id] = row
 
    deduped = list(seen.values())
    logger.info("Dedup bids: %d → %d", len(rows), len(deduped))
    return deduped
 
 
def cluster_vendor_names(names: list[str]) -> dict[str, str]:
    """
    Build a mapping from variant names → canonical name.
    Uses fuzzy matching within sorted name groups.
    """
    canonical_keys = [canonical_vendor_name(n) for n in names]
    clusters: dict[str, str] = {}  
 
    for i, key_i in enumerate(canonical_keys):
        if not key_i:
            continue
        matched = False
        for existing_key in list(clusters.keys()):
            score = fuzz.token_sort_ratio(key_i, existing_key)
            if score >= FUZZY_THRESHOLD:
                clusters[key_i] = clusters[existing_key]
                matched = True
                break
        if not matched:
            clusters[key_i] = names[i]
 

    name_map: dict[str, str] = {}
    for i, name in enumerate(names):
        key = canonical_keys[i]
        name_map[name] = clusters.get(key, name)
 
    return name_map
 
 
def deduplicate_vendors_in_rows(rows: list[dict]) -> list[dict]:
    """Normalize winner_name and vendor_name using fuzzy clustering."""
    all_names = set()
    for row in rows:
        for field in ("winner_name", "vendor_name"):
            n = row.get(field, "")
            if n:
                all_names.add(n)
 
    name_map = cluster_vendor_names(list(all_names))
 
    for row in rows:
        for field in ("winner_name", "vendor_name"):
            original = row.get(field, "")
            if original:
                row[field] = name_map.get(original, original)
 
    return rows