import logging
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)


def _safe_float(val) -> float:
    try:
        return float(val) if val else 0.0
    except (ValueError, TypeError):
        return 0.0


def compute_insights(rows: list[dict]) -> dict:
    """Compute all required insights and return as a structured dict."""
    total = len(rows)
    if total == 0:
        return {"error": "no data"}

    insights = {}

    bid_vendors: dict[str, set] = defaultdict(set)
    bid_bidders: dict[str, int] = {}

    for row in rows:
        bid_id = row.get("bid_id", "")
        num_bidders = int(row.get("num_bidders") or 0)
        vendor = row.get("vendor_name", "")
        if bid_id:
            if vendor:
                bid_vendors[bid_id].add(vendor)
            if num_bidders > 0:
                bid_bidders[bid_id] = max(bid_bidders.get(bid_id, 0), num_bidders)

    unique_bids = set(bid_bidders.keys()) | set(bid_vendors.keys())
    bids_with_3plus = 0
    for bid_id in unique_bids:
        n = bid_bidders.get(bid_id, len(bid_vendors.get(bid_id, set())))
        if n > 3:
            bids_with_3plus += 1

    pct_3plus = round(bids_with_3plus / max(len(unique_bids), 1) * 100, 1)
    insights["pct_bids_more_than_3_participants"] = {
        "value": pct_3plus,
        "numerator": bids_with_3plus,
        "denominator": len(unique_bids),
        "label": f"{pct_3plus}% of bids had more than 3 participants",
    }

   
    bid_prices: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        bid_id = row.get("bid_id", "")
        rank = (row.get("vendor_rank") or "").strip().upper()
        price = _safe_float(row.get("vendor_price"))
        if bid_id and rank in ("L1", "L2") and price > 0:
            bid_prices[bid_id][rank] = price

    gaps = []
    for bid_id, prices in bid_prices.items():
        if "L1" in prices and "L2" in prices:
            l1, l2 = prices["L1"], prices["L2"]
            gap_pct = (l2 - l1) / l1 * 100 if l1 > 0 else 0
            gaps.append(gap_pct)

    if gaps:
        avg_gap = round(sum(gaps) / len(gaps), 1)
        median_gap = round(sorted(gaps)[len(gaps) // 2], 1)
        max_gap = round(max(gaps), 1)
        large_gaps = sum(1 for g in gaps if g > 20)
    else:
        avg_gap = median_gap = max_gap = large_gaps = 0

    insights["l1_l2_price_gap"] = {
        "avg_gap_pct": avg_gap,
        "median_gap_pct": median_gap,
        "max_gap_pct": max_gap,
        "bids_with_gap_over_20pct": large_gaps,
        "total_bids_analyzed": len(gaps),
        "label": (
            f"Average L1-L2 gap: {avg_gap}% | "
            f"Median: {median_gap}% | "
            f"{large_gaps} bids with gap >20%"
        ),
    }

    
    bid_winner: dict[str, str] = {}
    for row in rows:
        bid_id = row.get("bid_id", "")
        winner = (row.get("winner_name") or "").strip()
        rank = (row.get("vendor_rank") or "").strip().upper()
        if bid_id and winner:
            if rank == "L1" or bid_id not in bid_winner:
                bid_winner[bid_id] = winner

    winner_counts = Counter(bid_winner.values())
    repeat_winners = {k: v for k, v in winner_counts.items() if v > 1}
    top_5 = winner_counts.most_common(5)

    insights["repeat_winners"] = {
        "num_unique_winners": len(winner_counts),
        "num_repeat_winners": len(repeat_winners),
        "top_5_winners": [{"vendor": v, "wins": c} for v, c in top_5],
        "concentration": round(
            sum(c for c in repeat_winners.values()) / max(len(bid_winner), 1) * 100, 1
        ),
        "label": (
            f"{len(repeat_winners)} vendors won multiple bids. "
            f"Top winner: {top_5[0][0]} ({top_5[0][1]} wins)" if top_5 else "No repeat winner data"
        ),
    }

   
    insights["summary"] = {
        "total_rows": total,
        "total_unique_bids": len(unique_bids),
        "data_accessibility": {
            "accessible": sum(1 for r in rows if r.get("result_accessible") == "yes"),
            "login_required": sum(1 for r in rows if r.get("result_accessible") == "login_required"),
            "error": sum(1 for r in rows if r.get("result_accessible") == "error"),
        },
        "anomaly_counts": _count_anomalies(rows),
    }

    return insights


def _count_anomalies(rows: list[dict]) -> dict:
    counter: dict[str, int] = Counter()
    for row in rows:
        flags = row.get("status_flag", "ok")
        for flag in flags.split(","):
            flag = flag.strip()
            if flag and flag != "ok":
                counter[flag] += 1
    return dict(counter)


def print_insights(insights: dict) -> None:
    """Print a human-readable summary to stdout."""
    print("\n" + "=" * 60)
    print("  GemEdge Procurement — Summary Insights")
    print("=" * 60)

    s = insights.get("summary", {})
    print(f"\nTotal records: {s.get('total_rows', 0)}")
    print(f"Unique bids:   {s.get('total_unique_bids', 0)}")

    acc = s.get("data_accessibility", {})
    print(f"\nData accessibility:")
    print(f"   Accessible:      {acc.get('accessible', 0)}")
    print(f"   Login required:  {acc.get('login_required', 0)}")
    print(f"   Errors:          {acc.get('error', 0)}")

    p = insights.get("pct_bids_more_than_3_participants", {})
    print(f"\n👥 {p.get('label', '')}")

    g = insights.get("l1_l2_price_gap", {})
    print(f"\n{g.get('label', '')}")

    r = insights.get("repeat_winners", {})
    print(f"\n{r.get('label', '')}")
    for entry in r.get("top_5_winners", [])[:3]:
        print(f"   • {entry['vendor']}: {entry['wins']} wins")

    anom = s.get("anomaly_counts", {})
    if anom:
        print(f"\nAnomalies detected:")
        for flag, count in anom.items():
            print(f"   • {flag}: {count}")

    print("\n" + "=" * 60 + "\n")
