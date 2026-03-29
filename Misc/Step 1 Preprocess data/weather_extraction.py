"""
    Website: https://open-meteo.com/
    Create a script to extract weather data from the nearest weather station when the input is latitude and longitude.
    Extract features like temperature, irradiance, and clouds for the past 5 years.
    We extract the data for past 5 years, daily maximum, daily minimum, and daily average for temperature, irradiance, and clouds and then aggregate it weekly. For example, weekly_aggregated_max, weekly aggregated_min, and weekly_aggregated_avg for each of the features. 
    Drop the daily data and only keep the weekly aggregated data.
    Output the data in a csv file called weather_data.csv with the format mentioned in outline.md
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import os


# ─── Configuration ───────────────────────────────────────────────────────────

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Daily variables we request from Open-Meteo
# Temperature: max, min (avg computed from these two)
# Shortwave radiation (irradiance): daily sum  (we treat this as daily value to aggregate)
# Cloud cover: we request hourly cloud_cover and compute daily max/min/mean ourselves
DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "shortwave_radiation_sum",
]

HOURLY_VARS = [
    "cloud_cover",
    "shortwave_radiation",
]


# ─── Helper functions ────────────────────────────────────────────────────────

def get_date_range(years_back: int = 5) -> tuple[str, str]:
    """
    Return (start_date, end_date) strings in YYYY-MM-DD format.
    end_date is 7 days ago (to avoid incomplete data near present),
    start_date is `years_back` years before end_date.
    """
    end = datetime.now() - timedelta(days=7)
    start = end.replace(year=end.year - years_back)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def fetch_weather_data(latitude: float, longitude: float, start_date: str, end_date: str) -> dict:
    """
    Call the Open-Meteo Historical Weather API and return the JSON response.
    Fetches both daily and hourly variables needed for temperature, irradiance, and clouds.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(DAILY_VARS),
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "auto",
    }

    response = requests.get(BASE_URL, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def build_daily_dataframe(data: dict) -> pd.DataFrame:
    """
    Parse the API JSON response into a single daily DataFrame with columns:
        date, temperature_max, temperature_min, temperature_avg,
        irradiance_max, irradiance_min, irradiance_avg,
        cloud_cover_max, cloud_cover_min, cloud_cover_avg
    """
    # --- Daily data (temperature & shortwave_radiation_sum) ---
    daily = data["daily"]
    daily_df = pd.DataFrame({
        "date": pd.to_datetime(daily["time"]),
        "temperature_max": daily["temperature_2m_max"],
        "temperature_min": daily["temperature_2m_min"],
        "irradiance_daily_sum": daily["shortwave_radiation_sum"],  # MJ/m² per day
    })

    # Compute daily average temperature from max and min
    daily_df["temperature_avg"] = (
        daily_df["temperature_max"] + daily_df["temperature_min"]
    ) / 2.0

    # --- Hourly data → aggregate to daily for cloud_cover & irradiance ---
    hourly = data["hourly"]
    hourly_df = pd.DataFrame({
        "datetime": pd.to_datetime(hourly["time"]),
        "cloud_cover": hourly["cloud_cover"],
        "irradiance_hourly": hourly["shortwave_radiation"],  # W/m²
    })
    hourly_df["date"] = hourly_df["datetime"].dt.date

    # Cloud cover: daily max, min, mean from hourly %
    cloud_daily = hourly_df.groupby("date").agg(
        cloud_cover_max=("cloud_cover", "max"),
        cloud_cover_min=("cloud_cover", "min"),
        cloud_cover_avg=("cloud_cover", "mean"),
    ).reset_index()
    cloud_daily["date"] = pd.to_datetime(cloud_daily["date"])

    # Irradiance (hourly W/m²): daily max, min, mean
    irradiance_daily = hourly_df.groupby("date").agg(
        irradiance_max=("irradiance_hourly", "max"),
        irradiance_min=("irradiance_hourly", "min"),
        irradiance_avg=("irradiance_hourly", "mean"),
    ).reset_index()
    irradiance_daily["date"] = pd.to_datetime(irradiance_daily["date"])

    # Merge everything on date
    daily_df = daily_df.merge(cloud_daily, on="date", how="left")
    daily_df = daily_df.merge(irradiance_daily, on="date", how="left")

    # Drop the intermediate irradiance_daily_sum column (we now have hourly-based stats)
    daily_df.drop(columns=["irradiance_daily_sum"], inplace=True)

    return daily_df


def aggregate_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate daily data into weekly buckets.

    For each feature (temperature, irradiance, cloud_cover) we produce:
        weekly_max  – max of the daily max values in that week
        weekly_min  – min of the daily min values in that week
        weekly_avg  – mean of the daily avg values in that week

    Returns a DataFrame indexed by week_number (1, 2, 3 …).
    """
    # Assign a week number starting from 1
    daily_df = daily_df.sort_values("date").reset_index(drop=True)
    daily_df["week_number"] = (daily_df.index // 7) + 1

    weekly = daily_df.groupby("week_number").agg(
        # Temperature
        weekly_max_temperature=("temperature_max", "max"),
        weekly_min_temperature=("temperature_min", "min"),
        weekly_avg_temperature=("temperature_avg", "mean"),
        # Irradiance (W/m²)
        weekly_max_irradiance=("irradiance_max", "max"),
        weekly_min_irradiance=("irradiance_min", "min"),
        weekly_avg_irradiance=("irradiance_avg", "mean"),
        # Cloud cover (%)
        weekly_max_cloud_cover=("cloud_cover_max", "max"),
        weekly_min_cloud_cover=("cloud_cover_min", "min"),
        weekly_avg_cloud_cover=("cloud_cover_avg", "mean"),
    ).reset_index()

    # Round numeric columns for readability
    numeric_cols = weekly.select_dtypes(include="number").columns.difference(["week_number"])
    weekly[numeric_cols] = weekly[numeric_cols].round(2)

    return weekly


def save_to_csv(df: pd.DataFrame, output_dir: str, filename: str = "weather_data.csv") -> str:
    """
    Save the DataFrame to a CSV file in `output_dir` and return the full path.
    """
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    df.to_csv(path, index=False)
    return path


def extract_weather(latitude: float, longitude: float, years_back: int = 5) -> pd.DataFrame:
    """
    End-to-end extraction pipeline:
        1. Compute date range for the past `years_back` years.
        2. Fetch daily + hourly weather data from Open-Meteo.
        3. Build a daily DataFrame with max/min/avg for temperature, irradiance, cloud cover.
        4. Aggregate to weekly granularity.
        5. Save to CSV and return the weekly DataFrame.
    """
    print(f"[1/4] Computing date range for the past {years_back} years …")
    start_date, end_date = get_date_range(years_back)
    print(f"       Date range: {start_date} → {end_date}")

    print("[2/4] Fetching weather data from Open-Meteo API …")
    raw_data = fetch_weather_data(latitude, longitude, start_date, end_date)
    print(f"       Received data for coordinates ({raw_data['latitude']}, {raw_data['longitude']})")

    print("[3/4] Building daily DataFrame …")
    daily_df = build_daily_dataframe(raw_data)
    print(f"       Daily rows: {len(daily_df)}")

    print("[4/4] Aggregating to weekly data …")
    weekly_df = aggregate_weekly(daily_df)
    print(f"       Weekly rows: {len(weekly_df)}")

    # Save CSV
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "aggregated_data_op")
    csv_path = save_to_csv(weekly_df, output_dir)
    print(f"\n✅  Saved weekly weather data → {csv_path}")

    return weekly_df


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Default: San Diego, CA
    LATITUDE = 32.7157
    LONGITUDE = -117.1611

    df = extract_weather(LATITUDE, LONGITUDE, years_back=5)
    print("\nFirst 10 rows of weekly aggregated weather data:\n")
    print(df.head(10).to_string(index=False))
