import logging
import pandas as pd
from config.settings import INSIGHTS_FILE

logger = logging.getLogger(__name__)


def generate_insights(df: pd.DataFrame) -> str:
    """
    Compute summary statistics and return them as a formatted string.
    Also saves to INSIGHTS_FILE.
    """
    lines = ["=" * 60, "GemEdge Procurement Data — Summary Insights", "=" * 60, ""]

    if "num_bidders" in df.columns:
        unique_bids = df.drop_duplicates("bid_id")
        total_bids = len(unique_bids)
        bids_gt3 = (unique_bids["num_bidders"] > 3).sum()
        pct_gt3 = (bids_gt3 / total_bids * 100) if total_bids else 0
        lines.append(f"1. Bids with > 3 participants: "
                     f"{bids_gt3} / {total_bids} ({pct_gt3:.1f}%)")
    else:
        lines.append("1. num_bidders column not available.")

    lines.append("")

   
    if "l1_l2_gap_pct" in df.columns:
        gap_data = df.drop_duplicates("bid_id")["l1_l2_gap_pct"].dropna()
        if len(gap_data) > 0:
            lines.append("2. L1 vs L2 Price Gap (%):")
            lines.append(f"   Mean gap    : {gap_data.mean():.1f}%")
            lines.append(f"   Median gap  : {gap_data.median():.1f}%")
            lines.append(f"   Max gap     : {gap_data.max():.1f}%")
            lines.append(f"   Bids > 20%  : {(gap_data > 20).sum()}")
        else:
            lines.append("2. L1/L2 gap data not available.")
    else:
        lines.append("2. L1/L2 gap analysis requires evaluation data.")

    lines.append("")


    if "winner_name" in df.columns:
        winner_counts = (
            df.drop_duplicates("bid_id")
              .groupby("winner_name")["bid_id"]
              .count()
              .sort_values(ascending=False)
        )
        repeat_winners = winner_counts[winner_counts > 1]
        lines.append(f"3. Repeat Winners: {len(repeat_winners)} vendors won > 1 bid")

        if len(repeat_winners) > 0:
            lines.append("   Top repeat winners:")
            for vendor, count in repeat_winners.head(5).items():
                lines.append(f"     {vendor}: {count} wins")
    else:
        lines.append("3. winner_name column not available.")

    lines.append("")

   
    if "winner_not_lowest" in df.columns:
        anomaly_bids = df.drop_duplicates("bid_id")["winner_not_lowest"].sum()
        lines.append(f"4. Anomaly — Winner not lowest price: {anomaly_bids} bids")

    lines.append("")
    lines.append("=" * 60)

    report = "\n".join(lines)
    print(report)

    with open(INSIGHTS_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"Insights saved to {INSIGHTS_FILE}")

    return report