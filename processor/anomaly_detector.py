
import logging
import pandas as pd

logger = logging.getLogger(__name__)


def flag_winner_not_lowest(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each bid_id, find the minimum vendor_price.
    If winner_price > min_vendor_price (by more than 0.5%), flag it.

    WHY 0.5% tolerance? Floating point and rounding in GEM data can cause
    tiny differences. We only flag meaningful discrepancies.
    """
    if "winner_price" not in df.columns or "vendor_price" not in df.columns:
        return df

    min_prices = (
        df.groupby("bid_id")["vendor_price"]
          .min()
          .rename("min_vendor_price")
    )
    df = df.merge(min_prices, on="bid_id", how="left")

    df["winner_not_lowest"] = (
        (df["winner_price"].notna()) &
        (df["min_vendor_price"].notna()) &
        (df["winner_price"] > df["min_vendor_price"] * 1.005)
    )

    anomaly_count = df.drop_duplicates("bid_id")["winner_not_lowest"].sum()
    logger.info(f"Anomaly: {anomaly_count} bids where winner was NOT the lowest price.")

   
    df.loc[df["winner_not_lowest"], "status_flag"] = "ANOMALY_WINNER_NOT_LOWEST"

    return df


def flag_large_l1_l2_gap(df: pd.DataFrame, threshold_pct: float = 20.0) -> pd.DataFrame:
    """
    For each bid, compute gap between L1 and L2 price as a %.
    Flag bids where the gap exceeds threshold_pct%.

    A very large L1-L2 gap can indicate:
      - A single dominant vendor (monopolistic)
      - Possible bid manipulation
    """
    if "vendor_rank" not in df.columns or "vendor_price" not in df.columns:
        return df

    l1 = df[df["vendor_rank"] == "L1"][["bid_id", "vendor_price"]].rename(
        columns={"vendor_price": "l1_price"}
    )
    l2 = df[df["vendor_rank"] == "L2"][["bid_id", "vendor_price"]].rename(
        columns={"vendor_price": "l2_price"}
    )

    gaps = pd.merge(l1, l2, on="bid_id", how="inner")
    gaps["l1_l2_gap_pct"] = ( (gaps["l2_price"] - gaps["l1_price"]) / gaps["l1_price"] * 100).round(2)
    gaps["large_l1_l2_gap"] = gaps["l1_l2_gap_pct"] > threshold_pct

    df = df.merge(gaps[["bid_id", "l1_l2_gap_pct", "large_l1_l2_gap"]],  on="bid_id", how="left")

    large_gap_count = gaps["large_l1_l2_gap"].sum()
    logger.info(
        f"Anomaly: {large_gap_count} bids with L1-L2 price gap > {threshold_pct}%."
    )
    return df