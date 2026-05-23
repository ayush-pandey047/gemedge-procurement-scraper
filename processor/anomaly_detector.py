
import logging
from collections import Counter

logger = logging.getLogger(__name__)


def _safe_float(val) -> float:
    try:
        return float(val) if val else 0.0
    except (ValueError, TypeError):
        return 0.0


def flag_anomalies(rows: list[dict]) -> list[dict]:
    """
    Add a 'status_flag' field to each row with comma-separated anomaly codes.
    Operates on the full dataset for repeat-winner detection.
    """

    for row in rows:
        flags = []

        winner_price = _safe_float(row.get("winner_price"))
        vendor_price = _safe_float(row.get("vendor_price"))
        num_bidders = int(row.get("num_bidders") or 0)
        vendor_rank = (row.get("vendor_rank") or "").upper()


        if winner_price == 0:
            flags.append("zero_price")


        if num_bidders == 1:
            flags.append("single_bidder")

     
        if vendor_rank == "L2" and vendor_price and winner_price:
            if vendor_price < winner_price:
                flags.append("winner_not_lowest")


        if vendor_rank == "L2" and vendor_price and winner_price and winner_price > 0:
            gap_pct = (vendor_price - winner_price) / winner_price * 100
            if gap_pct >= 50:
                flags.append("suspicious_gap")

        row["status_flag"] = ",".join(flags) if flags else "ok"


    winner_counts = Counter(
        row.get("winner_name", "").strip()
        for row in rows
        if row.get("winner_name", "").strip()
    )
    repeat_winners = {name for name, count in winner_counts.items() if count > 1}

    for row in rows:
        winner = row.get("winner_name", "").strip()
        if winner in repeat_winners:
            existing = row.get("status_flag", "ok")
            if "repeat_winner" not in existing:
                row["status_flag"] = (
                    existing + ",repeat_winner" if existing != "ok" else "repeat_winner"
                )

    flagged = sum(1 for r in rows if r.get("status_flag", "ok") != "ok")
    logger.info("Anomaly detection complete: %d/%d rows flagged", flagged, len(rows))
    return rows
