import pandas as pd
import os

# ─── Configuration ───────────────────────────────────────────────────────────

INPUT_FILENAME = "San_Diego_Load_EIA_Fixed.csv"
OUTPUT_FILENAME = "electricity_data.csv"

# Column mapping (adjust if your CSV headers are slightly different)
TIME_COL = "Timestamp_UTC"
LOAD_COL = "MW_Load"

# Timezone settings
FROM_TZ = "UTC"
TO_TZ = "America/Los_Angeles"

# ─── Helper functions ────────────────────────────────────────────────────────

def load_and_preprocess(filepath: str) -> pd.DataFrame:
    """
    Load the raw electricity CSV, parse UTC timestamps, and convert to Pacific Time.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Could not find {filepath}. Make sure it is in the same folder.")

    print(f"[1/3] Loading {filepath} ...")
    df = pd.read_csv(filepath)

    # Convert Timestamp to datetime objects
    df['datetime_utc'] = pd.to_datetime(df[TIME_COL])

    # Convert timezone: UTC -> Pacific
    df['datetime_local'] = df['datetime_utc'].dt.tz_localize(FROM_TZ).dt.tz_convert(TO_TZ)

    # Keep only relevant columns
    df = df[['datetime_local', LOAD_COL]].rename(columns={LOAD_COL: 'load_mw'})
    
    return df

def build_daily_dataframe(hourly_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate hourly data into daily stats:
      - daily_max: Maximum load in that day
      - daily_min: Minimum load in that day
      - daily_avg: Average load in that day
    """
    print("[2/3] Aggregating Hourly -> Daily ...")
    
    # Create a 'date' column for grouping
    hourly_df['date'] = hourly_df['datetime_local'].dt.date

    # Group by date and calculate stats
    daily = hourly_df.groupby('date').agg(
        load_max=('load_mw', 'max'),
        load_min=('load_mw', 'min'),
        load_avg=('load_mw', 'mean')
    ).reset_index()

    return daily

def aggregate_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate daily data into weekly buckets (7-day chunks).
    
    Logic matches the weather script:
      - weekly_max = Max of the daily maxes
      - weekly_min = Min of the daily mins
      - weekly_avg = Mean of the daily avgs
    """
    print("[3/3] Aggregating Daily -> Weekly ...")

    # Sort by date to ensure correct 7-day chunks
    daily_df = daily_df.sort_values("date").reset_index(drop=True)

    # Assign week number (1, 2, 3...)
    daily_df["week_number"] = (daily_df.index // 7) + 1

    weekly = daily_df.groupby("week_number").agg(
        # Load Stats
        weekly_aggregated_max_load=("load_max", "max"),
        weekly_aggregated_min_load=("load_min", "min"),
        weekly_aggregated_avg_load=("load_avg", "mean"),
        # Keep track of the start date of the week for reference
        week_start_date=("date", "first")
    ).reset_index()

    # Round numeric columns for readability
    weekly['weekly_aggregated_avg_load'] = weekly['weekly_aggregated_avg_load'].round(2)

    return weekly

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    
    # 1. Load & Process Timezones
    hourly_data = load_and_preprocess(INPUT_FILENAME)
    
    # 2. Daily Aggregation
    daily_data = build_daily_dataframe(hourly_data)
    
    # 3. Weekly Aggregation
    weekly_data = aggregate_weekly(daily_data)
    
    # 4. Save to CSV
    weekly_data.to_csv(OUTPUT_FILENAME, index=False)
    
    print(f"\n✅ Saved weekly electricity data to: {OUTPUT_FILENAME}")
    print(f"   Total Weeks Processed: {len(weekly_data)}")
    print("\nFirst 5 rows of output:")
    print(weekly_data.head().to_string(index=False))