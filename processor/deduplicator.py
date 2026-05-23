import logging
import pandas as pd

logger = logging.getLogger(__name__)


def deduplicate_bids(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove rows with duplicate bid_id + vendor_name combinations.

    We keep the FIRST occurrence (sorted by any available date or original order).
    Duplicate rows are logged for transparency.
    """
    before = len(df)

   
    subset = ["bid_id", "vendor_name"]
    subset = [c for c in subset if c in df.columns]  

    df = df.drop_duplicates(subset=subset, keep="first")
    after = len(df)

    logger.info(f"Deduplication: removed {before - after} duplicate rows. "
                f"{after} rows remain.")
    return df


def flag_duplicate_vendors(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a column 'is_repeat_winner' = True if the winner_name has won
    more than one bid in our dataset.

    WHY: The assignment asks us to detect patterns in repeat winners.
    """
    if "winner_name" not in df.columns:
        return df

    win_counts = (
        df.drop_duplicates(subset=["bid_id", "winner_name"])
          .groupby("winner_name")["bid_id"]
          .count()
          .rename("win_count")
    )
    df = df.merge(win_counts, on="winner_name", how="left")
    df["is_repeat_winner"] = df["win_count"] > 1
    logger.info(
        f"Repeat winner detection: "
        f"{df['is_repeat_winner'].sum()} rows belong to repeat winners."
    )
    return df