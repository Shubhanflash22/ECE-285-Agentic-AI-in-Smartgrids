"""
data_extractor.py – Thin wrapper around the two data-extraction scripts.

Called by pipeline.py **before** feature engineering so that
  data/weather_data.csv   and   data/household_data.csv
are regenerated from scratch for the configured (latitude, longitude).

The electricity_data.csv is derived from the same household extraction
(weekly aggregation), so all three CSVs stay in sync.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ── Resolve project paths ────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent
_DATA_DIR = _PROJECT_ROOT / "data"

# Household extraction source CSV (regional EIA load data)
_EIA_CSV = (
    _PROJECT_ROOT
    / "data_extraction"
    / "Household_electricity_data"
    / "San_Diego_Load_EIA_Fixed.csv"
)

# ── Ensure the extraction packages are importable ─────────────
sys.path.insert(0, str(_PROJECT_ROOT / "data_extraction"))
sys.path.insert(
    0,
    str(_PROJECT_ROOT / "data_extraction" / "Household_electricity_data"),
)


# ═════════════════════════════════════════════════════════════
# Weather extraction
# ═════════════════════════════════════════════════════════════

def regenerate_weather_csv(
    latitude: float,
    longitude: float,
    output_path: str | Path = "data/weather_data.csv",
    years_back: int = 5,
) -> Path:
    """
    Fetch weather data from Open-Meteo and write *output_path*.

    Returns the absolute path to the saved CSV.
    """
    from weather_data import (
        get_date_range,
        fetch_weather_data,
        build_daily_dataframe,
        aggregate_weekly,
    )

    logger.info(
        "Fetching weather data for (%.4f, %.4f), last %d years …",
        latitude, longitude, years_back,
    )

    start_date, end_date = get_date_range(years_back)
    raw = fetch_weather_data(latitude, longitude, start_date, end_date)
    daily_df = build_daily_dataframe(raw)
    weekly_df = aggregate_weekly(daily_df)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    weekly_df.to_csv(out, index=False)
    logger.info("  ✅  Saved weather CSV → %s  (%d rows)", out, len(weekly_df))
    return out.resolve()


# ═════════════════════════════════════════════════════════════
# Household extraction
# ═════════════════════════════════════════════════════════════

def regenerate_household_csv(
    latitude: float,
    longitude: float,
    output_path: str | Path = "data/household_data.csv",
) -> Path:
    """
    Generate per-household hourly kW data from the regional EIA load
    CSV and write *output_path*.

    Returns the absolute path to the saved CSV.
    """
    from household_extraction_per_house import (
        load_regional_data,
        apply_all_variability_factors,
        create_hourly_output,
    )

    logger.info(
        "Generating household electricity data for (%.4f, %.4f) …",
        latitude, longitude,
    )

    if not _EIA_CSV.is_file():
        raise FileNotFoundError(
            f"Regional EIA load CSV not found: {_EIA_CSV}\n"
            "Make sure San_Diego_Load_EIA_Fixed.csv is in "
            "data_extraction/Household_electricity_data/"
        )

    hourly_df = load_regional_data(str(_EIA_CSV))
    hourly_df = apply_all_variability_factors(hourly_df, latitude, longitude)
    output_df = create_hourly_output(hourly_df)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(out, index=False)
    logger.info("  ✅  Saved household CSV → %s  (%d rows)", out, len(output_df))
    return out.resolve()


# ═════════════════════════════════════════════════════════════
# Electricity (weekly aggregation of household data)
# ═════════════════════════════════════════════════════════════

def regenerate_electricity_csv(
    household_csv: str | Path = "data/household_data.csv",
    output_path: str | Path = "data/electricity_data.csv",
) -> Path:
    """
    Aggregate the per-household hourly data into the weekly electricity
    format that feature_engineering.py expects:

        week_number, weekly_aggregated_max_load,
        weekly_aggregated_min_load, weekly_aggregated_avg_load,
        week_start_date

    Returns the absolute path to the saved CSV.
    """
    logger.info("Aggregating household data → weekly electricity CSV …")

    df = pd.read_csv(household_csv, parse_dates=["datetime_local"])
    df["date"] = df["datetime_local"].dt.date

    # Daily aggregation first
    daily = df.groupby("date").agg(
        daily_max=("household_kw", "max"),
        daily_min=("household_kw", "min"),
        daily_avg=("household_kw", "mean"),
    ).reset_index()
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values("date").reset_index(drop=True)

    # Weekly aggregation
    daily["week_number"] = (daily.index // 7) + 1
    weekly = daily.groupby("week_number").agg(
        weekly_aggregated_max_load=("daily_max", "max"),
        weekly_aggregated_min_load=("daily_min", "min"),
        weekly_aggregated_avg_load=("daily_avg", "mean"),
        week_start_date=("date", "first"),
    ).reset_index()

    weekly[["weekly_aggregated_max_load",
            "weekly_aggregated_min_load",
            "weekly_aggregated_avg_load"]] = (
        weekly[["weekly_aggregated_max_load",
                "weekly_aggregated_min_load",
                "weekly_aggregated_avg_load"]].round(4)
    )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    weekly.to_csv(out, index=False)
    logger.info("  ✅  Saved electricity CSV → %s  (%d rows)", out, len(weekly))
    return out.resolve()


# ═════════════════════════════════════════════════════════════
# Convenience: regenerate ALL data CSVs
# ═════════════════════════════════════════════════════════════

def regenerate_all(
    latitude: float,
    longitude: float,
    weather_csv: str | Path = "data/weather_data.csv",
    household_csv: str | Path = "data/household_data.csv",
    electricity_csv: str | Path = "data/electricity_data.csv",
    years_back: int = 5,
) -> dict[str, Path]:
    """
    Regenerate weather, household, and electricity CSVs in one call.

    Returns a dict mapping label → absolute path of each saved CSV.
    """
    logger.info("═" * 60)
    logger.info("DATA EXTRACTION – regenerating all CSVs for (%.4f, %.4f)", latitude, longitude)
    logger.info("═" * 60)

    weather_path = regenerate_weather_csv(latitude, longitude, weather_csv, years_back)
    household_path = regenerate_household_csv(latitude, longitude, household_csv)
    electricity_path = regenerate_electricity_csv(household_csv, electricity_csv)

    return {
        "weather": weather_path,
        "household": household_path,
        "electricity": electricity_path,
    }


# ── CLI quick-test ────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
    paths = regenerate_all(32.7157, -117.1611)
    for label, p in paths.items():
        print(f"  {label:>15s} → {p}")
