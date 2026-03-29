"""
feature_engineering.py
=====================
Comprehensive feature engineering for PV-cell sizing analysis.

Reads three CSV files (electricity, weather, household), computes
domain-specific features via dedicated functions, and emits a
formatted summary ready for LLM consumption.

Usage:
    python feature_engineering.py                        # defaults
    python feature_engineering.py --elec  <path>         # override paths
"""

from __future__ import annotations

import argparse
import logging
import math
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)

# ═══════════════════════════════════════════════════════════════
#  DEFAULTS / CONSTANTS
# ═══════════════════════════════════════════════════════════════

DEFAULT_ELEC_PATH = "data/electricity_data.csv"
DEFAULT_HOUSEHOLD_PATH = "data/household_data.csv"
DEFAULT_WEATHER_PATH = "data/weather_data.csv"

# PV panel assumptions (typical 400 W residential panel)
PV_PANEL_WATT_PEAK = 400               # Wp per panel
PV_EFFICIENCY_LOSS = 0.80              # system-level derating (inverter, wiring, soiling)
PV_OPTIMAL_TEMP_LOW = 15.0             # °C – below this, panels are fine
PV_OPTIMAL_TEMP_HIGH = 35.0            # °C – above this, efficiency drops
PV_PANEL_COST = 350                    # USD per panel
PV_INSTALL_FIXED_COST = 4_000          # USD one-time installation
PV_LIFESPAN_YEARS = 25
DISCOUNT_RATE = 0.05                   # for NPV / IRR
ELECTRICITY_PRICE_PER_KWH = 0.31       # USD

# Approximate peak sun-hour to irradiance mapping
# 1 PSH ≈ 1 kWh/m² of irradiance → we derive from weekly_avg_irradiance
IRRADIANCE_TO_PSH_FACTOR = 1.0 / 1000.0   # W/m² weekly avg → approximate PSH


# ═══════════════════════════════════════════════════════════════
#  1️⃣  ELECTRICITY CONSUMPTION FEATURES
# ═══════════════════════════════════════════════════════════════

# ── 1a. Load Distribution Features ───────────────────────────

def peak_weekly_consumption(df_elec: pd.DataFrame) -> float:
    """Return the peak weekly maximum load (kWh) across the entire dataset.

    Parameters
    ----------
    df_elec : DataFrame with column ``weekly_aggregated_max_load``.

    Returns
    -------
    float : Highest recorded weekly max load.
    """
    return float(df_elec["weekly_aggregated_max_load"].max())


def percentile_95_weekly_consumption(df_elec: pd.DataFrame) -> float:
    """Return the 95th-percentile of the weekly average load.

    Captures the upper tail of typical consumption, useful for
    sizing PV + storage so the system covers most (but not all)
    demand without over-investment.

    Parameters
    ----------
    df_elec : DataFrame with column ``weekly_aggregated_avg_load``.
    """
    return float(df_elec["weekly_aggregated_avg_load"].quantile(0.95))


def min_weekly_consumption(df_elec: pd.DataFrame) -> float:
    """Return the minimum weekly minimum load across the dataset.

    Parameters
    ----------
    df_elec : DataFrame with column ``weekly_aggregated_min_load``.
    """
    return float(df_elec["weekly_aggregated_min_load"].min())


def load_variance(df_elec: pd.DataFrame) -> float:
    """Variance of the weekly average load.

    High variance indicates volatile demand which complicates PV sizing.

    Parameters
    ----------
    df_elec : DataFrame with column ``weekly_aggregated_avg_load``.
    """
    return float(df_elec["weekly_aggregated_avg_load"].var())


def load_std(df_elec: pd.DataFrame) -> float:
    """Standard deviation of the weekly average load.

    Parameters
    ----------
    df_elec : DataFrame with column ``weekly_aggregated_avg_load``.
    """
    return float(df_elec["weekly_aggregated_avg_load"].std())


def coefficient_of_variation(df_elec: pd.DataFrame) -> float:
    """Coefficient of variation (CV = std / mean) for weekly avg load.

    A CV > 0.3 suggests significant demand volatility.

    Parameters
    ----------
    df_elec : DataFrame with column ``weekly_aggregated_avg_load``.
    """
    mean = df_elec["weekly_aggregated_avg_load"].mean()
    std = df_elec["weekly_aggregated_avg_load"].std()
    return float(std / mean) if mean != 0 else 0.0


def load_iqr(df_elec: pd.DataFrame) -> float:
    """Interquartile range (IQR) of weekly average load.

    Robust measure of spread not affected by outliers.

    Parameters
    ----------
    df_elec : DataFrame with column ``weekly_aggregated_avg_load``.
    """
    q75 = df_elec["weekly_aggregated_avg_load"].quantile(0.75)
    q25 = df_elec["weekly_aggregated_avg_load"].quantile(0.25)
    return float(q75 - q25)


# ── 1b. Seasonal Strength Metrics ────────────────────────────

def seasonal_index_per_month(df_elec: pd.DataFrame) -> Dict[int, float]:
    """Seasonal index = month_avg / annual_avg for each calendar month.

    A value > 1.0 means above-average consumption that month.

    Parameters
    ----------
    df_elec : DataFrame with ``week_start_date`` (parseable) and
              ``weekly_aggregated_avg_load``.

    Returns
    -------
    dict : {month_number: seasonal_index}
    """
    df = df_elec.copy()
    df["month"] = pd.to_datetime(df["week_start_date"]).dt.month
    annual_avg = df["weekly_aggregated_avg_load"].mean()
    monthly = df.groupby("month")["weekly_aggregated_avg_load"].mean()
    return {int(m): round(float(v / annual_avg), 4) for m, v in monthly.items()}


def peak_to_trough_ratio(df_elec: pd.DataFrame) -> float:
    """Ratio of the highest monthly avg load to the lowest.

    Values near 1.0 indicate flat demand; > 2.0 indicates very seasonal.

    Parameters
    ----------
    df_elec : DataFrame with ``week_start_date`` and
              ``weekly_aggregated_avg_load``.
    """
    df = df_elec.copy()
    df["month"] = pd.to_datetime(df["week_start_date"]).dt.month
    monthly = df.groupby("month")["weekly_aggregated_avg_load"].mean()
    return float(monthly.max() / monthly.min()) if monthly.min() != 0 else float("inf")


def winter_vs_summer_ratio(df_elec: pd.DataFrame) -> float:
    """Ratio of average winter to summer weekly consumption.

    Winter = Dec-Feb (months 12, 1, 2), Summer = Jun-Aug (6, 7, 8).

    Parameters
    ----------
    df_elec : DataFrame with ``week_start_date`` and
              ``weekly_aggregated_avg_load``.
    """
    df = df_elec.copy()
    df["month"] = pd.to_datetime(df["week_start_date"]).dt.month
    winter = df.loc[df["month"].isin([12, 1, 2]), "weekly_aggregated_avg_load"].mean()
    summer = df.loc[df["month"].isin([6, 7, 8]), "weekly_aggregated_avg_load"].mean()
    return float(winter / summer) if summer != 0 else float("inf")


def consumption_trend_slope(df_elec: pd.DataFrame) -> float:
    """Slope of a linear regression of weekly avg load over time.

    Positive → consumption is growing.  Units: kWh / week.

    Parameters
    ----------
    df_elec : DataFrame with ``weekly_aggregated_avg_load`` in row order.
    """
    y = df_elec["weekly_aggregated_avg_load"].values
    x = np.arange(len(y), dtype=float)
    if len(y) < 2:
        return 0.0
    slope = float(np.polyfit(x, y, 1)[0])
    return slope


# ── 1c. Growth / Trend Signals ───────────────────────────────

def year_over_year_growth(df_elec: pd.DataFrame) -> Dict[str, float]:
    """Year-over-year percentage change in total annual consumption.

    Parameters
    ----------
    df_elec : DataFrame with ``week_start_date`` and
              ``weekly_aggregated_avg_load``.

    Returns
    -------
    dict : {\"2022_vs_2021\": pct_change, …}
    """
    df = df_elec.copy()
    df["year"] = pd.to_datetime(df["week_start_date"]).dt.year
    annual = df.groupby("year")["weekly_aggregated_avg_load"].sum()
    result = {}
    years = sorted(annual.index)
    for prev, curr in zip(years[:-1], years[1:]):
        pct = float((annual[curr] - annual[prev]) / annual[prev] * 100)
        result[f"{curr}_vs_{prev}"] = round(pct, 2)
    return result


def moving_average_trend_slope(df_elec: pd.DataFrame, window: int = 4) -> float:
    """Slope of the 4-week (≈30-day) moving average trend line.

    Computed as a linear fit on the MA series.

    Parameters
    ----------
    df_elec : DataFrame with ``weekly_aggregated_avg_load``.
    window  : Rolling window size in weeks (default 4 ≈ 1 month).
    """
    ma = df_elec["weekly_aggregated_avg_load"].rolling(window).mean().dropna().values
    if len(ma) < 2:
        return 0.0
    x = np.arange(len(ma), dtype=float)
    return float(np.polyfit(x, ma, 1)[0])


def change_point_count(df_elec: pd.DataFrame, threshold_sigma: float = 2.0) -> int:
    """Count weeks where the week-over-week change exceeds *threshold_sigma*
    standard deviations of the diff series.

    High counts suggest sudden load shifts (new appliances, EV, etc.).

    Parameters
    ----------
    df_elec         : DataFrame with ``weekly_aggregated_avg_load``.
    threshold_sigma : Multiple of std to flag as change point.
    """
    diff = df_elec["weekly_aggregated_avg_load"].diff().dropna()
    threshold = diff.std() * threshold_sigma
    return int((diff.abs() > threshold).sum())


# ── 1d. Peak Load Metrics ────────────────────────────────────

def max_single_week_spike(df_elec: pd.DataFrame) -> float:
    """Largest single-week max-load value.

    Parameters
    ----------
    df_elec : DataFrame with ``weekly_aggregated_max_load``.
    """
    return float(df_elec["weekly_aggregated_max_load"].max())


def weeks_above_threshold(
    df_elec: pd.DataFrame, multiplier: float = 1.5
) -> int:
    """Number of weeks where avg load exceeds *multiplier* × overall mean.

    Default multiplier = 1.5.

    Parameters
    ----------
    df_elec    : DataFrame with ``weekly_aggregated_avg_load``.
    multiplier : Threshold multiplier over the mean.
    """
    mean = df_elec["weekly_aggregated_avg_load"].mean()
    return int((df_elec["weekly_aggregated_avg_load"] > mean * multiplier).sum())


def consecutive_high_load_streaks(
    df_elec: pd.DataFrame, multiplier: float = 1.2
) -> int:
    """Length of the longest consecutive streak of weeks with avg load
    above *multiplier* × mean.

    Parameters
    ----------
    df_elec    : DataFrame with ``weekly_aggregated_avg_load``.
    multiplier : Threshold multiplier over the mean.
    """
    mean = df_elec["weekly_aggregated_avg_load"].mean()
    above = (df_elec["weekly_aggregated_avg_load"] > mean * multiplier).astype(int)
    groups = above.ne(above.shift()).cumsum()
    streaks = above.groupby(groups).sum()
    return int(streaks.max()) if len(streaks) > 0 else 0


# ═══════════════════════════════════════════════════════════════
#  2️⃣  WEATHER / SOLAR POTENTIAL FEATURES
# ═══════════════════════════════════════════════════════════════

# ── 2a. Solar Energy Potential Estimation ─────────────────────

def avg_weekly_irradiance(df_weather: pd.DataFrame) -> float:
    """Average of the weekly average irradiance (W/m²).

    Higher irradiance → more PV production potential.

    Parameters
    ----------
    df_weather : DataFrame with ``weekly_avg_irradiance``.
    """
    return float(df_weather["weekly_avg_irradiance"].mean())


def annual_total_irradiance(df_weather: pd.DataFrame) -> float:
    """Sum of weekly average irradiance values across one year.

    Approximates total annual irradiance exposure.

    Parameters
    ----------
    df_weather : DataFrame with ``weekly_avg_irradiance``.
    """
    return float(df_weather["weekly_avg_irradiance"].sum())


def estimated_peak_sun_hours_daily(df_weather: pd.DataFrame) -> float:
    """Estimate average daily peak sun hours from weekly irradiance.

    PSH ≈ weekly_avg_irradiance (W/m²) / 1000 * hours_of_daylight.
    Simplified: avg irradiance / 1000 * ~5 hours (conservative).

    Parameters
    ----------
    df_weather : DataFrame with ``weekly_avg_irradiance``.
    """
    avg_irr = df_weather["weekly_avg_irradiance"].mean()
    # Simple conversion: irradiance in W/m² to PSH
    # avg irradiance over a week includes night → divide by ~200 baseline
    psh = avg_irr / 1000.0 * 8.0  # 8 daylight hours weighted
    return round(float(psh), 2)


def estimated_annual_sunlight_hours(df_weather: pd.DataFrame) -> float:
    """Estimate total annual sunlight hours from irradiance data.

    Days with avg irradiance > 50 W/m² are counted as 'sunlight days',
    scaled by irradiance intensity.

    Parameters
    ----------
    df_weather : DataFrame with ``weekly_avg_irradiance``.
    """
    psh_daily = estimated_peak_sun_hours_daily(df_weather)
    return round(psh_daily * 365, 1)


def seasonal_irradiance_index(df_weather: pd.DataFrame) -> Dict[str, float]:
    """Seasonal irradiance index: season_avg / annual_avg.

    Seasons defined by week_number ranges (Northern Hemisphere):
      Spring = weeks 13–25, Summer = 26–38, Autumn = 39–51, Winter = rest.

    Parameters
    ----------
    df_weather : DataFrame with ``week_number`` and ``weekly_avg_irradiance``.

    Returns
    -------
    dict : {\"Spring\": idx, \"Summer\": idx, …}
    """
    df = df_weather.copy()
    # Map week within each year (1-52) using modulo
    df["week_in_year"] = ((df["week_number"] - 1) % 52) + 1
    conditions = [
        df["week_in_year"].between(13, 25),
        df["week_in_year"].between(26, 38),
        df["week_in_year"].between(39, 51),
    ]
    choices = ["Spring", "Summer", "Autumn"]
    df["season"] = np.select(conditions, choices, default="Winter")
    annual_avg = df["weekly_avg_irradiance"].mean()
    seasonal = df.groupby("season")["weekly_avg_irradiance"].mean()
    return {s: round(float(v / annual_avg), 4) for s, v in seasonal.items()}


def irradiance_variance(df_weather: pd.DataFrame) -> float:
    """Variance of weekly average irradiance.

    High variance → inconsistent solar potential → harder to plan PV sizing.

    Parameters
    ----------
    df_weather : DataFrame with ``weekly_avg_irradiance``.
    """
    return float(df_weather["weekly_avg_irradiance"].var())


def temperature_irradiance_correlation(df_weather: pd.DataFrame) -> float:
    """Pearson correlation between weekly avg temperature and avg irradiance.

    Strong positive correlation means hot weather = more sun (typical).

    Parameters
    ----------
    df_weather : DataFrame with ``weekly_avg_temperature`` and
                 ``weekly_avg_irradiance``.
    """
    return float(
        df_weather["weekly_avg_temperature"].corr(
            df_weather["weekly_avg_irradiance"]
        )
    )


# ── 2b. PV Efficiency Impact Factors ─────────────────────────

def weeks_above_pv_optimal_temp(
    df_weather: pd.DataFrame, threshold: float = PV_OPTIMAL_TEMP_HIGH
) -> int:
    """Count of weeks where max temperature exceeds PV optimal threshold.

    PV efficiency drops ~0.4 %/°C above 25 °C.

    Parameters
    ----------
    df_weather : DataFrame with ``weekly_max_temperature``.
    threshold  : Temperature above which PV efficiency degrades (default 35 °C).
    """
    return int((df_weather["weekly_max_temperature"] > threshold).sum())


def cloudy_week_frequency(df_weather: pd.DataFrame, cloud_threshold: float = 70.0) -> float:
    """Fraction of weeks where average cloud cover exceeds *cloud_threshold* %.

    High cloudy frequency lowers effective PV yield.

    Parameters
    ----------
    df_weather      : DataFrame with ``weekly_avg_cloud_cover``.
    cloud_threshold : Percentage threshold to consider a week 'cloudy'.
    """
    total = len(df_weather)
    cloudy = (df_weather["weekly_avg_cloud_cover"] > cloud_threshold).sum()
    return round(float(cloudy / total), 4) if total else 0.0


def sunlight_consistency_score(df_weather: pd.DataFrame) -> float:
    """Irradiance consistency = std / mean of weekly avg irradiance.

    Lower is better (more predictable solar).

    Parameters
    ----------
    df_weather : DataFrame with ``weekly_avg_irradiance``.
    """
    mean = df_weather["weekly_avg_irradiance"].mean()
    std = df_weather["weekly_avg_irradiance"].std()
    return round(float(std / mean), 4) if mean else 0.0


# ── 2c. Production Alignment Metrics ─────────────────────────

def consumption_irradiance_correlation(
    df_elec: pd.DataFrame, df_weather: pd.DataFrame
) -> float:
    """Pearson correlation between weekly avg load and weekly avg irradiance.

    Negative → consumption peaks when sun is low (winter) → PV helps less
    without storage.

    Parameters
    ----------
    df_elec    : Electricity DataFrame (265 rows).
    df_weather : Weather DataFrame (261 rows).
    """
    min_len = min(len(df_elec), len(df_weather))
    elec = df_elec["weekly_aggregated_avg_load"].iloc[:min_len].reset_index(drop=True)
    irr = df_weather["weekly_avg_irradiance"].iloc[:min_len].reset_index(drop=True)
    return round(float(elec.corr(irr)), 4)


def lag_correlation(
    df_elec: pd.DataFrame, df_weather: pd.DataFrame, max_lag: int = 4
) -> Dict[int, float]:
    """Cross-correlation at lags 0 .. max_lag weeks.

    Positive lag means consumption lags irradiance.

    Parameters
    ----------
    df_elec    : Electricity DataFrame.
    df_weather : Weather DataFrame.
    max_lag    : Maximum lag in weeks to test.

    Returns
    -------
    dict : {lag_weeks: correlation}
    """
    min_len = min(len(df_elec), len(df_weather))
    elec = df_elec["weekly_aggregated_avg_load"].iloc[:min_len].reset_index(drop=True)
    irr = df_weather["weekly_avg_irradiance"].iloc[:min_len].reset_index(drop=True)
    result = {}
    for lag in range(max_lag + 1):
        if lag == 0:
            result[lag] = round(float(elec.corr(irr)), 4)
        else:
            result[lag] = round(float(elec.iloc[lag:].reset_index(drop=True).corr(
                irr.iloc[:-lag].reset_index(drop=True)
            )), 4)
    return result


def monthly_production_to_consumption_ratio(
    df_elec: pd.DataFrame, df_weather: pd.DataFrame, num_panels: int = 10
) -> Dict[int, float]:
    """Estimated monthly PV production / consumption ratio.

    Production per panel ≈ irradiance × panel_Wp × efficiency × hours.

    Parameters
    ----------
    df_elec    : Electricity DataFrame with ``week_start_date`` and avg load.
    df_weather : Weather DataFrame with ``weekly_avg_irradiance``.
    num_panels : Number of panels assumed for the estimate.

    Returns
    -------
    dict : {month: ratio}
    """
    df_e = df_elec.copy()
    df_e["month"] = pd.to_datetime(df_e["week_start_date"]).dt.month
    monthly_consumption = df_e.groupby("month")["weekly_aggregated_avg_load"].mean()

    df_w = df_weather.copy()
    # Assign months using a similar week-to-month mapping
    df_w["week_in_year"] = ((df_w["week_number"] - 1) % 52) + 1
    df_w["month"] = ((df_w["week_in_year"] - 1) // 4.33).astype(int).clip(0, 11) + 1
    monthly_irr = df_w.groupby("month")["weekly_avg_irradiance"].mean()

    result = {}
    for month in range(1, 13):
        irr = monthly_irr.get(month, 0)
        # Weekly production per panel (kWh): irradiance * 7 * daylight_hrs / 1000 * panel_kWp * efficiency
        weekly_prod_per_panel = irr * 7 * 6 / 1000.0 * (PV_PANEL_WATT_PEAK / 1000.0) * PV_EFFICIENCY_LOSS
        total_prod = weekly_prod_per_panel * num_panels
        cons = monthly_consumption.get(month, 1)
        result[int(month)] = round(float(total_prod / cons), 4) if cons else 0.0
    return result


# ═══════════════════════════════════════════════════════════════
#  3️⃣  HOUSEHOLD DATA FEATURES
# ═══════════════════════════════════════════════════════════════

def _household_daily_stats(df_household: pd.DataFrame) -> pd.DataFrame:
    """Helper: aggregate hourly household data to daily totals (kWh).

    Parameters
    ----------
    df_household : DataFrame with ``datetime_local`` and ``household_kw``.

    Returns
    -------
    DataFrame with columns ``date`` and ``daily_kwh``.
    """
    df = df_household.copy()
    df["datetime_local"] = pd.to_datetime(df["datetime_local"])
    df["date"] = df["datetime_local"].dt.date
    daily = df.groupby("date")["household_kw"].sum().reset_index()
    daily.columns = ["date", "daily_kwh"]
    return daily


# ── 3a. Normalized Metrics ────────────────────────────────────

def kwh_per_occupant(df_household: pd.DataFrame, occupants: int = 4) -> float:
    """Average daily kWh per household occupant.

    Parameters
    ----------
    df_household : Hourly household DataFrame.
    occupants    : Number of people in the household.
    """
    daily = _household_daily_stats(df_household)
    avg_daily = daily["daily_kwh"].mean()
    return round(float(avg_daily / occupants), 2) if occupants else 0.0


def kwh_per_sqm(df_household: pd.DataFrame, house_sqm: float = 150.0) -> float:
    """Average daily kWh per square metre of house area.

    Parameters
    ----------
    df_household : Hourly household DataFrame.
    house_sqm    : House area in square metres.
    """
    daily = _household_daily_stats(df_household)
    avg_daily = daily["daily_kwh"].mean()
    return round(float(avg_daily / house_sqm), 4) if house_sqm else 0.0


def electricity_cost_per_occupant(
    df_household: pd.DataFrame,
    occupants: int = 4,
    price_per_kwh: float = ELECTRICITY_PRICE_PER_KWH,
) -> float:
    """Average daily electricity cost per occupant (USD).

    Parameters
    ----------
    df_household  : Hourly household DataFrame.
    occupants     : Number of occupants.
    price_per_kwh : Cost per kWh in USD.
    """
    daily = _household_daily_stats(df_household)
    avg_daily_cost = daily["daily_kwh"].mean() * price_per_kwh
    return round(float(avg_daily_cost / occupants), 2) if occupants else 0.0


def electricity_cost_per_sqm(
    df_household: pd.DataFrame,
    house_sqm: float = 150.0,
    price_per_kwh: float = ELECTRICITY_PRICE_PER_KWH,
) -> float:
    """Average daily electricity cost per square metre (USD).

    Parameters
    ----------
    df_household  : Hourly household DataFrame.
    house_sqm     : House area in square metres.
    price_per_kwh : Cost per kWh in USD.
    """
    daily = _household_daily_stats(df_household)
    avg_daily_cost = daily["daily_kwh"].mean() * price_per_kwh
    return round(float(avg_daily_cost / house_sqm), 4) if house_sqm else 0.0


# ── 3b. Cost Structure Features ──────────────────────────────

def effective_cost_per_kwh(
    df_household: pd.DataFrame,
    price_per_kwh: float = ELECTRICITY_PRICE_PER_KWH,
) -> float:
    """Effective cost per kWh (simply the tariff rate used).

    If a more complex tariff structure is available, this function can
    be extended to compute total_bill / total_kwh.

    Parameters
    ----------
    df_household  : Hourly household DataFrame (used for context).
    price_per_kwh : Flat tariff rate.
    """
    return round(float(price_per_kwh), 4)


# ── 3c. Financial Health Metrics ──────────────────────────────

def annual_electricity_expenditure(
    df_household: pd.DataFrame,
    price_per_kwh: float = ELECTRICITY_PRICE_PER_KWH,
) -> float:
    """Estimated annual electricity spend (USD).

    Parameters
    ----------
    df_household  : Hourly household DataFrame.
    price_per_kwh : Tariff rate.
    """
    daily = _household_daily_stats(df_household)
    total_kwh = daily["daily_kwh"].sum()
    n_days = len(daily)
    if n_days == 0:
        return 0.0
    annual_kwh = total_kwh / n_days * 365
    return round(float(annual_kwh * price_per_kwh), 2)


def projected_5yr_electricity_cost(
    df_household: pd.DataFrame,
    price_per_kwh: float = ELECTRICITY_PRICE_PER_KWH,
    annual_price_increase: float = 0.03,
) -> float:
    """Projected total electricity cost over 5 years assuming an annual
    price increase.

    Parameters
    ----------
    df_household          : Hourly household DataFrame.
    price_per_kwh         : Starting tariff rate.
    annual_price_increase : Year-over-year price escalation (default 3 %).
    """
    daily = _household_daily_stats(df_household)
    total_kwh = daily["daily_kwh"].sum()
    n_days = len(daily)
    if n_days == 0:
        return 0.0
    annual_kwh = total_kwh / n_days * 365

    total = 0.0
    price = price_per_kwh
    for _ in range(5):
        total += annual_kwh * price
        price *= (1 + annual_price_increase)
    return round(total, 2)


def household_annual_kwh(df_household: pd.DataFrame) -> float:
    """Estimate total annual kWh from the household hourly data.

    Parameters
    ----------
    df_household : Hourly household DataFrame.
    """
    daily = _household_daily_stats(df_household)
    total = daily["daily_kwh"].sum()
    n_days = len(daily)
    return round(float(total / n_days * 365), 2) if n_days else 0.0


# ═══════════════════════════════════════════════════════════════
#  4️⃣  CROSS-DATASET DERIVED FEATURES
# ═══════════════════════════════════════════════════════════════

# ── 4a. Self-Sufficiency Metrics ──────────────────────────────

def estimated_annual_production_per_panel(df_weather: pd.DataFrame) -> float:
    """Estimated annual kWh production for one PV panel.

    Uses avg weekly irradiance, panel Wp, and system efficiency.

    Parameters
    ----------
    df_weather : Weather DataFrame with ``weekly_avg_irradiance``.

    Returns
    -------
    float : kWh per panel per year.
    """
    avg_irr = df_weather["weekly_avg_irradiance"].mean()
    # Daily production: irradiance (W/m²) * daylight_hours / 1000 * panel_kWp * efficiency
    daily_kwh = avg_irr * 6 / 1000.0 * (PV_PANEL_WATT_PEAK / 1000.0) * PV_EFFICIENCY_LOSS
    annual = daily_kwh * 365
    return round(float(annual), 2)


def panels_needed_for_offset(
    df_household: pd.DataFrame, df_weather: pd.DataFrame, offset_pct: float = 1.0
) -> int:
    """Number of PV panels to offset *offset_pct* of annual household consumption.

    Parameters
    ----------
    df_household : Hourly household DataFrame.
    df_weather   : Weather DataFrame.
    offset_pct   : Fraction to offset (1.0 = 100 %, 0.7 = 70 %).

    Returns
    -------
    int : Number of panels (rounded up).
    """
    annual_kwh = household_annual_kwh(df_household)
    prod_per_panel = estimated_annual_production_per_panel(df_weather)
    if prod_per_panel <= 0:
        return 0
    return int(math.ceil(annual_kwh * offset_pct / prod_per_panel))


def overproduction_months(
    df_elec: pd.DataFrame, df_weather: pd.DataFrame, num_panels: int = 10
) -> int:
    """Count of months where estimated PV production exceeds consumption.

    Parameters
    ----------
    df_elec    : Electricity DataFrame.
    df_weather : Weather DataFrame.
    num_panels : Number of panels installed.

    Returns
    -------
    int : Number of months with surplus.
    """
    ratios = monthly_production_to_consumption_ratio(df_elec, df_weather, num_panels)
    return sum(1 for r in ratios.values() if r > 1.0)


def underproduction_months(
    df_elec: pd.DataFrame, df_weather: pd.DataFrame, num_panels: int = 10
) -> int:
    """Count of months where estimated PV production is below consumption.

    Parameters
    ----------
    df_elec    : Electricity DataFrame.
    df_weather : Weather DataFrame.
    num_panels : Number of panels installed.

    Returns
    -------
    int : Number of months with deficit.
    """
    ratios = monthly_production_to_consumption_ratio(df_elec, df_weather, num_panels)
    return sum(1 for r in ratios.values() if r < 1.0)


# ── 4b. Payback Analysis Features ────────────────────────────

def _system_cost(num_panels: int) -> float:
    """Total upfront cost = fixed install + per-panel cost."""
    return PV_INSTALL_FIXED_COST + num_panels * PV_PANEL_COST


def break_even_years(
    df_household: pd.DataFrame,
    df_weather: pd.DataFrame,
    num_panels: int = 10,
    price_per_kwh: float = ELECTRICITY_PRICE_PER_KWH,
) -> float:
    """Simple payback period in years.

    Parameters
    ----------
    df_household  : Hourly household DataFrame.
    df_weather    : Weather DataFrame.
    num_panels    : Panels to install.
    price_per_kwh : Electricity tariff.

    Returns
    -------
    float : Payback years (inf if production is zero).
    """
    annual_prod = estimated_annual_production_per_panel(df_weather) * num_panels
    annual_savings = annual_prod * price_per_kwh
    cost = _system_cost(num_panels)
    return round(float(cost / annual_savings), 2) if annual_savings > 0 else float("inf")


def npv_10_years(
    df_household: pd.DataFrame,
    df_weather: pd.DataFrame,
    num_panels: int = 10,
    price_per_kwh: float = ELECTRICITY_PRICE_PER_KWH,
    discount_rate: float = DISCOUNT_RATE,
    price_escalation: float = 0.03,
) -> float:
    """Net present value over 10 years.

    Parameters
    ----------
    df_household     : Hourly household DataFrame.
    df_weather       : Weather DataFrame.
    num_panels       : Panels to install.
    price_per_kwh    : Starting electricity price.
    discount_rate    : Annual discount rate.
    price_escalation : Annual electricity price increase.
    """
    cost = _system_cost(num_panels)
    annual_prod = estimated_annual_production_per_panel(df_weather) * num_panels
    npv = -cost
    price = price_per_kwh
    for yr in range(1, 11):
        savings = annual_prod * price
        npv += savings / ((1 + discount_rate) ** yr)
        price *= (1 + price_escalation)
    return round(float(npv), 2)


def irr_estimate(
    df_weather: pd.DataFrame,
    num_panels: int = 10,
    price_per_kwh: float = ELECTRICITY_PRICE_PER_KWH,
    price_escalation: float = 0.03,
    years: int = 25,
) -> float:
    """Approximate internal rate of return via bisection.

    Parameters
    ----------
    df_weather       : Weather DataFrame.
    num_panels       : Panels to install.
    price_per_kwh    : Starting tariff.
    price_escalation : Annual price increase.
    years            : Analysis horizon.

    Returns
    -------
    float : IRR as a decimal (0.08 = 8 %).
    """
    cost = _system_cost(num_panels)
    annual_prod = estimated_annual_production_per_panel(df_weather) * num_panels

    def _npv_at(rate: float) -> float:
        npv = -cost
        price = price_per_kwh
        for yr in range(1, years + 1):
            savings = annual_prod * price
            npv += savings / ((1 + rate) ** yr)
            price *= (1 + price_escalation)
        return npv

    lo, hi = -0.5, 2.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _npv_at(mid) > 0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 4)


def roi_percent(
    df_weather: pd.DataFrame,
    num_panels: int = 10,
    price_per_kwh: float = ELECTRICITY_PRICE_PER_KWH,
    price_escalation: float = 0.03,
    years: int = 25,
) -> float:
    """Total return on investment over *years* as a percentage.

    ROI = (total savings − cost) / cost × 100.

    Parameters
    ----------
    df_weather       : Weather DataFrame.
    num_panels       : Panels to install.
    price_per_kwh    : Starting tariff.
    price_escalation : Annual price increase.
    years            : Horizon.
    """
    cost = _system_cost(num_panels)
    annual_prod = estimated_annual_production_per_panel(df_weather) * num_panels
    total_savings = 0.0
    price = price_per_kwh
    for _ in range(years):
        total_savings += annual_prod * price
        price *= (1 + price_escalation)
    return round(float((total_savings - cost) / cost * 100), 2) if cost else 0.0


def payback_vs_lifespan(
    df_household: pd.DataFrame,
    df_weather: pd.DataFrame,
    num_panels: int = 10,
    price_per_kwh: float = ELECTRICITY_PRICE_PER_KWH,
) -> Dict[str, float]:
    """Compare payback period against panel lifespan.

    Parameters
    ----------
    df_household  : Hourly household DataFrame.
    df_weather    : Weather DataFrame.
    num_panels    : Panels to install.
    price_per_kwh : Tariff.

    Returns
    -------
    dict : {\"payback_years\", \"lifespan_years\", \"years_of_profit\"}
    """
    pb = break_even_years(df_household, df_weather, num_panels, price_per_kwh)
    return {
        "payback_years": pb,
        "lifespan_years": float(PV_LIFESPAN_YEARS),
        "years_of_profit": round(float(PV_LIFESPAN_YEARS - pb), 2) if pb != float("inf") else 0.0,
    }


# ── 4c. Grid Dependency Metrics ──────────────────────────────

def nighttime_load_ratio(df_household: pd.DataFrame) -> float:
    """Fraction of total consumption occurring outside peak sunlight hours
    (before 8 AM or after 6 PM).

    Parameters
    ----------
    df_household : Hourly household DataFrame.
    """
    df = df_household.copy()
    df["datetime_local"] = pd.to_datetime(df["datetime_local"])
    df["hour"] = df["datetime_local"].dt.hour
    total = df["household_kw"].sum()
    night = df.loc[(df["hour"] < 8) | (df["hour"] >= 18), "household_kw"].sum()
    return round(float(night / total), 4) if total else 0.0


def base_load_vs_variable_load(df_household: pd.DataFrame) -> Dict[str, float]:
    """Split consumption into base load and variable load.

    Base load ≈ 10th-percentile hourly reading (always-on appliances).
    Variable load = total − base.

    Parameters
    ----------
    df_household : Hourly household DataFrame.

    Returns
    -------
    dict : {\"base_load_kw\", \"variable_load_kw\", \"base_load_pct\"}
    """
    base = float(df_household["household_kw"].quantile(0.10))
    mean = float(df_household["household_kw"].mean())
    variable = mean - base
    return {
        "base_load_kw": round(base, 3),
        "variable_load_kw": round(variable, 3),
        "base_load_pct": round(float(base / mean * 100), 1) if mean else 0.0,
    }


def pct_consumption_outside_peak_sun(df_household: pd.DataFrame) -> float:
    """Percentage of consumption outside peak sunlight (10 AM – 3 PM).

    Parameters
    ----------
    df_household : Hourly household DataFrame.
    """
    df = df_household.copy()
    df["datetime_local"] = pd.to_datetime(df["datetime_local"])
    df["hour"] = df["datetime_local"].dt.hour
    total = df["household_kw"].sum()
    outside = df.loc[(df["hour"] < 10) | (df["hour"] >= 15), "household_kw"].sum()
    return round(float(outside / total * 100), 2) if total else 0.0


# ═══════════════════════════════════════════════════════════════
#  5️⃣  RISK & SENSITIVITY FEATURES
# ═══════════════════════════════════════════════════════════════

# ── 5a. Sensitivity Analysis ─────────────────────────────────

def roi_under_price_change(
    df_weather: pd.DataFrame,
    num_panels: int = 10,
    base_price: float = ELECTRICITY_PRICE_PER_KWH,
    delta_pct: float = 0.10,
) -> Dict[str, float]:
    """ROI under ±delta_pct electricity price change.

    Parameters
    ----------
    df_weather  : Weather DataFrame.
    num_panels  : Panels.
    base_price  : Baseline tariff.
    delta_pct   : Price variation (default ±10 %).

    Returns
    -------
    dict : {\"roi_price_up\", \"roi_price_down\", \"roi_baseline\"}
    """
    return {
        "roi_baseline": roi_percent(df_weather, num_panels, base_price),
        "roi_price_up": roi_percent(df_weather, num_panels, base_price * (1 + delta_pct)),
        "roi_price_down": roi_percent(df_weather, num_panels, base_price * (1 - delta_pct)),
    }


def roi_under_irradiance_change(
    df_weather: pd.DataFrame,
    num_panels: int = 10,
    delta_pct: float = 0.10,
) -> Dict[str, float]:
    """ROI under ±delta_pct sunlight variability.

    Simulates by scaling irradiance up/down, recalculating ROI.

    Parameters
    ----------
    df_weather : Weather DataFrame.
    num_panels : Panels.
    delta_pct  : Irradiance variation (default ±10 %).

    Returns
    -------
    dict : {\"roi_sun_up\", \"roi_sun_down\", \"roi_baseline\"}
    """
    baseline = roi_percent(df_weather, num_panels)
    # scale irradiance
    df_up = df_weather.copy()
    df_up["weekly_avg_irradiance"] = df_up["weekly_avg_irradiance"] * (1 + delta_pct)
    df_down = df_weather.copy()
    df_down["weekly_avg_irradiance"] = df_down["weekly_avg_irradiance"] * (1 - delta_pct)
    return {
        "roi_baseline": baseline,
        "roi_sun_up": roi_percent(df_up, num_panels),
        "roi_sun_down": roi_percent(df_down, num_panels),
    }


def roi_under_consumption_growth(
    df_weather: pd.DataFrame,
    num_panels: int = 10,
    growth_rates: Optional[List[float]] = None,
) -> Dict[str, float]:
    """ROI under different consumption growth scenarios.

    Since PV savings scale with the *price* and not directly with consumption
    (fixed panel output), we model consumption growth as requiring additional
    grid power, reducing effective offset.

    Parameters
    ----------
    df_weather   : Weather DataFrame.
    num_panels   : Panels.
    growth_rates : List of annual growth rates to test.
    """
    if growth_rates is None:
        growth_rates = [0.0, 0.02, 0.05]
    result = {}
    for g in growth_rates:
        label = f"growth_{int(g*100)}pct"
        # Under higher consumption, effective savings fraction shrinks,
        # but absolute savings stay the same (capped by panel output).
        result[label] = roi_percent(df_weather, num_panels)
    return result


# ── 5b. Stability Metrics ────────────────────────────────────

def consumption_volatility_score(df_elec: pd.DataFrame) -> float:
    """Consumption volatility: coefficient of variation of weekly avg load.

    Parameters
    ----------
    df_elec : Electricity DataFrame.
    """
    return coefficient_of_variation(df_elec)


def sunlight_volatility_score(df_weather: pd.DataFrame) -> float:
    """Sunlight volatility: coefficient of variation of weekly avg irradiance.

    Parameters
    ----------
    df_weather : Weather DataFrame.
    """
    return sunlight_consistency_score(df_weather)


def combined_risk_score(df_elec: pd.DataFrame, df_weather: pd.DataFrame) -> float:
    """Combined risk = average of consumption and sunlight volatility.

    Range roughly 0 – 1; higher → riskier investment.

    Parameters
    ----------
    df_elec    : Electricity DataFrame.
    df_weather : Weather DataFrame.
    """
    cv = consumption_volatility_score(df_elec)
    sv = sunlight_volatility_score(df_weather)
    return round(float((cv + sv) / 2), 4)


# ═══════════════════════════════════════════════════════════════
#  6️⃣  EV & BUDGET FEATURES
# ═══════════════════════════════════════════════════════════════

# Average EV energy consumption: ~3.5 miles/kWh, ~12,000 miles/year per EV
_EV_KWH_PER_YEAR = 3_500  # kWh / year per EV (conservative estimate)


def ev_annual_charging_kwh(num_evs: int) -> float:
    """Estimated additional annual electricity consumption from EVs.

    Assumes ~3,500 kWh/year per EV based on an average of 12,000 miles/year
    at ~3.5 miles/kWh efficiency with charging overhead.

    Parameters
    ----------
    num_evs : Number of electric vehicles in the household.

    Returns
    -------
    float : Additional kWh per year for EV charging.
    """
    return round(float(num_evs * _EV_KWH_PER_YEAR), 2)


def panels_within_budget(
    pv_budget: float,
    df_weather: pd.DataFrame,
    price_per_kwh: float = ELECTRICITY_PRICE_PER_KWH,
) -> Dict[str, Any]:
    """Calculate the maximum number of panels purchasable within budget,
    along with the resulting production and financial metrics.

    Budget covers both per-panel cost and fixed installation cost.
    If budget is below fixed install cost, zero panels are returned.

    Parameters
    ----------
    pv_budget     : Total available budget in USD.
    df_weather    : Weather DataFrame for production estimate.
    price_per_kwh : Electricity tariff.

    Returns
    -------
    dict : max_panels, total_cost_usd, annual_production_kwh,
           annual_savings_usd, break_even_years
    """
    remaining = pv_budget - PV_INSTALL_FIXED_COST
    max_panels = max(0, int(remaining // PV_PANEL_COST))
    total_cost = PV_INSTALL_FIXED_COST + max_panels * PV_PANEL_COST if max_panels > 0 else 0.0
    annual_prod = estimated_annual_production_per_panel(df_weather) * max_panels
    annual_savings = annual_prod * price_per_kwh
    be_years = round(float(total_cost / annual_savings), 2) if annual_savings > 0 else float("inf")

    return {
        "max_panels": max_panels,
        "total_cost_usd": round(total_cost, 2),
        "annual_production_kwh": round(annual_prod, 2),
        "annual_savings_usd": round(annual_savings, 2),
        "break_even_years": be_years,
    }


# ═══════════════════════════════════════════════════════════════
#  7️⃣  EXTRACTION & FORMATTING
# ═══════════════════════════════════════════════════════════════

def extract_all_features(
    df_elec: pd.DataFrame,
    df_weather: pd.DataFrame,
    df_household: pd.DataFrame,
    num_panels: int = 10,
    occupants: int = 4,
    house_sqm: float = 150.0,
    price_per_kwh: float = ELECTRICITY_PRICE_PER_KWH,
    num_evs: int = 0,
    pv_budget: float = 10000.0,
) -> Dict[str, Any]:
    """Run every feature function and return a nested dict of results.

    Parameters
    ----------
    df_elec       : Electricity weekly DataFrame.
    df_weather    : Weather weekly DataFrame.
    df_household  : Household hourly DataFrame.
    num_panels    : Assumed panel count for cross-dataset features.
    occupants     : Number of household occupants.
    house_sqm     : House area in m².
    price_per_kwh : Tariff rate (USD / kWh).

    Returns
    -------
    dict : Hierarchically structured feature dictionary.
    """
    daily_hh = _household_daily_stats(df_household)
    annual_hh_kwh = household_annual_kwh(df_household)

    panels_100 = panels_needed_for_offset(df_household, df_weather, 1.0)
    panels_70 = panels_needed_for_offset(df_household, df_weather, 0.7)
    panels_50 = panels_needed_for_offset(df_household, df_weather, 0.5)

    features: Dict[str, Any] = {
        # ── 1. Electricity ───────────────────────────────
        "electricity": {
            "load_distribution": {
                "peak_weekly_max_load_kw": peak_weekly_consumption(df_elec),
                "p95_weekly_avg_load_kw": percentile_95_weekly_consumption(df_elec),
                "min_weekly_min_load_kw": min_weekly_consumption(df_elec),
                "load_variance": round(load_variance(df_elec), 2),
                "load_std": round(load_std(df_elec), 2),
                "coefficient_of_variation": round(coefficient_of_variation(df_elec), 4),
                "iqr": round(load_iqr(df_elec), 2),
            },
            "seasonal": {
                "seasonal_index": seasonal_index_per_month(df_elec),
                "peak_to_trough_ratio": round(peak_to_trough_ratio(df_elec), 4),
                "winter_vs_summer_ratio": round(winter_vs_summer_ratio(df_elec), 4),
                "consumption_trend_slope_kw_per_week": round(consumption_trend_slope(df_elec), 4),
            },
            "growth": {
                "yoy_growth_pct": year_over_year_growth(df_elec),
                "ma_trend_slope": round(moving_average_trend_slope(df_elec), 4),
                "change_points_2sigma": change_point_count(df_elec),
            },
            "peak_load": {
                "max_single_week_spike_kw": max_single_week_spike(df_elec),
                "weeks_above_1_5x_mean": weeks_above_threshold(df_elec, 1.5),
                "longest_high_load_streak_weeks": consecutive_high_load_streaks(df_elec),
            },
            "annual_avg_weekly_load_kw": round(float(df_elec["weekly_aggregated_avg_load"].mean()), 2),
            "household_annual_kwh": annual_hh_kwh,
            "household_avg_daily_kwh": round(float(daily_hh["daily_kwh"].mean()), 2),
        },

        # ── 2. Weather / Solar ───────────────────────────
        "weather_solar": {
            "solar_potential": {
                "avg_weekly_irradiance_wm2": round(avg_weekly_irradiance(df_weather), 2),
                "annual_total_irradiance_wm2": round(annual_total_irradiance(df_weather), 2),
                "est_daily_peak_sun_hours": estimated_peak_sun_hours_daily(df_weather),
                "est_annual_sunlight_hours": estimated_annual_sunlight_hours(df_weather),
                "seasonal_irradiance_index": seasonal_irradiance_index(df_weather),
                "irradiance_variance": round(irradiance_variance(df_weather), 2),
                "temp_irradiance_correlation": temperature_irradiance_correlation(df_weather),
            },
            "pv_efficiency": {
                "weeks_above_optimal_temp": weeks_above_pv_optimal_temp(df_weather),
                "cloudy_week_frequency": cloudy_week_frequency(df_weather),
                "sunlight_consistency_score": sunlight_consistency_score(df_weather),
            },
            "alignment": {
                "consumption_irradiance_corr": consumption_irradiance_correlation(df_elec, df_weather),
                "lag_correlations": lag_correlation(df_elec, df_weather),
                "monthly_prod_to_cons_ratio": monthly_production_to_consumption_ratio(
                    df_elec, df_weather, num_panels
                ),
            },
        },

        # ── 3. Household ─────────────────────────────────
        "household": {
            "normalized": {
                "kwh_per_occupant": kwh_per_occupant(df_household, occupants),
                "kwh_per_sqm": kwh_per_sqm(df_household, house_sqm),
                "cost_per_occupant_usd": electricity_cost_per_occupant(df_household, occupants, price_per_kwh),
                "cost_per_sqm_usd": electricity_cost_per_sqm(df_household, house_sqm, price_per_kwh),
            },
            "cost_structure": {
                "effective_cost_per_kwh": effective_cost_per_kwh(df_household, price_per_kwh),
            },
            "financial": {
                "annual_expenditure_usd": annual_electricity_expenditure(df_household, price_per_kwh),
                "projected_5yr_cost_usd": projected_5yr_electricity_cost(df_household, price_per_kwh),
            },
        },

        # ── 4. Cross-dataset ─────────────────────────────
        "cross_dataset": {
            "self_sufficiency": {
                "est_annual_prod_per_panel_kwh": estimated_annual_production_per_panel(df_weather),
                "panels_for_100pct_offset": panels_100,
                "panels_for_70pct_offset": panels_70,
                "panels_for_50pct_offset": panels_50,
                "overproduction_months": overproduction_months(df_elec, df_weather, num_panels),
                "underproduction_months": underproduction_months(df_elec, df_weather, num_panels),
            },
            "payback": {
                "break_even_years": break_even_years(df_household, df_weather, num_panels, price_per_kwh),
                "npv_10yr_usd": npv_10_years(df_household, df_weather, num_panels, price_per_kwh),
                "irr": irr_estimate(df_weather, num_panels, price_per_kwh),
                "roi_pct": roi_percent(df_weather, num_panels, price_per_kwh),
                "payback_vs_lifespan": payback_vs_lifespan(df_household, df_weather, num_panels, price_per_kwh),
            },
            "grid_dependency": {
                "nighttime_load_ratio": nighttime_load_ratio(df_household),
                "pct_outside_peak_sun": pct_consumption_outside_peak_sun(df_household),
                "base_vs_variable_load": base_load_vs_variable_load(df_household),
            },
        },

        # ── 5. Risk & Sensitivity ────────────────────────
        "risk_sensitivity": {
            "price_sensitivity": roi_under_price_change(df_weather, num_panels, price_per_kwh),
            "irradiance_sensitivity": roi_under_irradiance_change(df_weather, num_panels),
            "consumption_growth_sensitivity": roi_under_consumption_growth(df_weather, num_panels),
            "stability": {
                "consumption_volatility": consumption_volatility_score(df_elec),
                "sunlight_volatility": sunlight_volatility_score(df_weather),
                "combined_risk_score": combined_risk_score(df_elec, df_weather),
            },
        },

        # ── 6. EV & Budget ───────────────────────────────
        "ev_and_budget": {
            "num_evs": num_evs,
            "ev_annual_charging_kwh": ev_annual_charging_kwh(num_evs),
            "total_annual_kwh_with_ev": round(
                annual_hh_kwh + ev_annual_charging_kwh(num_evs), 2
            ),
            "pv_budget_usd": pv_budget,
            "budget_analysis": panels_within_budget(pv_budget, df_weather, price_per_kwh),
        },
    }

    return features


# ─────────────────────────────────────────────────────────────
# Formatted LLM-ready summary
# ─────────────────────────────────────────────────────────────

def format_for_llm(features: Dict[str, Any]) -> str:
    """Convert the features dict into a clean, structured text block
    suitable for injection into an LLM prompt.

    Parameters
    ----------
    features : Output of :func:`extract_all_features`.

    Returns
    -------
    str : Multi-section summary string.
    """
    e = features["electricity"]
    ws = features["weather_solar"]
    h = features["household"]
    cd = features["cross_dataset"]
    rs = features["risk_sensitivity"]

    # helpers
    def _fmt(val, unit="", decimals=2):
        if isinstance(val, float):
            return f"{val:,.{decimals}f}{unit}"
        return f"{val}{unit}"

    # seasonal index formatted
    si = e["seasonal"]["seasonal_index"]
    si_lines = "  ".join(f"M{m}={v:.2f}" for m, v in sorted(si.items()))

    prod_per_panel = cd["self_sufficiency"]["est_annual_prod_per_panel_kwh"]
    nighttime = cd["grid_dependency"]["nighttime_load_ratio"]
    base_var = cd["grid_dependency"]["base_vs_variable_load"]
    pvl = cd["payback"]["payback_vs_lifespan"]

    lines = []
    lines.append("=" * 64)
    lines.append("  FEATURE-ENGINEERED SUMMARY FOR LLM")
    lines.append("=" * 64)

    # ── Electricity ───────────────────────────────────────
    lines.append("")
    lines.append("📊 ELECTRICITY CONSUMPTION SUMMARY")
    lines.append("─" * 40)
    lines.append(f"  Annual household consumption    : {_fmt(e['household_annual_kwh'])} kWh")
    lines.append(f"  Avg daily consumption           : {_fmt(e['household_avg_daily_kwh'])} kWh")
    lines.append(f"  Avg weekly load                 : {_fmt(e['annual_avg_weekly_load_kw'])} kW")
    lines.append(f"  Peak weekly max load            : {_fmt(e['load_distribution']['peak_weekly_max_load_kw'])} kW")
    lines.append(f"  95th-percentile weekly avg load  : {_fmt(e['load_distribution']['p95_weekly_avg_load_kw'])} kW")
    lines.append(f"  Min weekly min load             : {_fmt(e['load_distribution']['min_weekly_min_load_kw'])} kW")
    lines.append(f"  Load std deviation              : {_fmt(e['load_distribution']['load_std'])} kW")
    lines.append(f"  Coefficient of variation        : {_fmt(e['load_distribution']['coefficient_of_variation'], decimals=4)}")
    lines.append(f"  Interquartile range             : {_fmt(e['load_distribution']['iqr'])} kW")
    lines.append(f"  Peak-to-trough ratio            : {_fmt(e['seasonal']['peak_to_trough_ratio'], decimals=2)}")
    lines.append(f"  Winter / Summer ratio            : {_fmt(e['seasonal']['winter_vs_summer_ratio'], decimals=2)}")
    lines.append(f"  Consumption trend slope          : {_fmt(e['seasonal']['consumption_trend_slope_kw_per_week'])} kW/week")
    lines.append(f"  Seasonal indices                : {si_lines}")
    yoy = e["growth"]["yoy_growth_pct"]
    if yoy:
        yoy_str = ", ".join(f"{k}: {v:+.1f}%" for k, v in yoy.items())
        lines.append(f"  Year-over-year growth           : {yoy_str}")
    lines.append(f"  Moving-avg trend slope          : {_fmt(e['growth']['ma_trend_slope'], decimals=4)} kW/week")
    lines.append(f"  Change points (2σ)              : {e['growth']['change_points_2sigma']}")
    lines.append(f"  Max single-week spike           : {_fmt(e['peak_load']['max_single_week_spike_kw'])} kW")
    lines.append(f"  Weeks > 1.5× mean              : {e['peak_load']['weeks_above_1_5x_mean']}")
    lines.append(f"  Longest high-load streak        : {e['peak_load']['longest_high_load_streak_weeks']} weeks")

    # ── Weather / Solar ───────────────────────────────────
    lines.append("")
    lines.append("☀️  SOLAR POTENTIAL SUMMARY")
    lines.append("─" * 40)
    sp = ws["solar_potential"]
    lines.append(f"  Avg weekly irradiance           : {_fmt(sp['avg_weekly_irradiance_wm2'])} W/m²")
    lines.append(f"  Est daily peak sun hours        : {_fmt(sp['est_daily_peak_sun_hours'])} hrs")
    lines.append(f"  Est annual sunlight hours       : {_fmt(sp['est_annual_sunlight_hours'])} hrs")
    sir = sp["seasonal_irradiance_index"]
    sir_str = "  ".join(f"{s}={v:.2f}" for s, v in sorted(sir.items()))
    lines.append(f"  Seasonal irradiance index       : {sir_str}")
    lines.append(f"  Irradiance variance             : {_fmt(sp['irradiance_variance'])}")
    lines.append(f"  Temp ↔ irradiance correlation    : {_fmt(sp['temp_irradiance_correlation'], decimals=4)}")
    pv_eff = ws["pv_efficiency"]
    lines.append(f"  Weeks above PV optimal temp     : {pv_eff['weeks_above_optimal_temp']}")
    lines.append(f"  Cloudy-week frequency           : {_fmt(pv_eff['cloudy_week_frequency'] * 100)}%")
    lines.append(f"  Sunlight consistency (CV)       : {_fmt(pv_eff['sunlight_consistency_score'], decimals=4)}")
    al = ws["alignment"]
    lines.append(f"  Consumption ↔ irradiance corr    : {_fmt(al['consumption_irradiance_corr'], decimals=4)}")
    lag = al["lag_correlations"]
    lag_str = ", ".join(f"lag{k}={v:.3f}" for k, v in lag.items())
    lines.append(f"  Lag correlations                : {lag_str}")

    # ── Household ─────────────────────────────────────────
    lines.append("")
    lines.append("🏠 HOUSEHOLD SUMMARY")
    lines.append("─" * 40)
    n = h["normalized"]
    lines.append(f"  kWh per occupant (daily)        : {_fmt(n['kwh_per_occupant'])} kWh")
    lines.append(f"  kWh per m² (daily)              : {_fmt(n['kwh_per_sqm'], decimals=4)} kWh")
    lines.append(f"  Cost per occupant (daily)       : ${_fmt(n['cost_per_occupant_usd'])}")
    lines.append(f"  Cost per m² (daily)             : ${_fmt(n['cost_per_sqm_usd'], decimals=4)}")
    lines.append(f"  Effective cost per kWh           : ${_fmt(h['cost_structure']['effective_cost_per_kwh'], decimals=4)}")
    lines.append(f"  Annual electricity spend         : ${_fmt(h['financial']['annual_expenditure_usd'])}")
    lines.append(f"  Projected 5-year cost            : ${_fmt(h['financial']['projected_5yr_cost_usd'])}")

    # ── Cross-dataset / PV Sizing ─────────────────────────
    lines.append("")
    lines.append("⚡ PV SIZING & FINANCIAL ANALYSIS")
    lines.append("─" * 40)
    ss = cd["self_sufficiency"]
    lines.append(f"  Est annual production / panel    : {_fmt(prod_per_panel)} kWh")
    lines.append(f"  Panels for 100% offset          : {ss['panels_for_100pct_offset']}")
    lines.append(f"  Panels for 70% offset           : {ss['panels_for_70pct_offset']}")
    lines.append(f"  Panels for 50% offset           : {ss['panels_for_50pct_offset']}")
    lines.append(f"  Overproduction months            : {ss['overproduction_months']}")
    lines.append(f"  Underproduction months           : {ss['underproduction_months']}")
    pb = cd["payback"]
    lines.append(f"  Panel cost                      : ${PV_PANEL_COST} / panel")
    lines.append(f"  Installation fixed cost          : ${PV_INSTALL_FIXED_COST:,}")
    lines.append(f"  Break-even                      : {_fmt(pb['break_even_years'])} years")
    lines.append(f"  NPV (10 yr)                     : ${_fmt(pb['npv_10yr_usd'])}")
    lines.append(f"  IRR                             : {_fmt(pb['irr'] * 100)}%")
    lines.append(f"  ROI (25 yr)                     : {_fmt(pb['roi_pct'])}%")
    lines.append(f"  Payback vs lifespan             : {pvl['payback_years']:.1f} yr payback / {pvl['lifespan_years']:.0f} yr life → {pvl['years_of_profit']:.1f} yr profit")

    # ── Grid Dependency ───────────────────────────────────
    lines.append("")
    lines.append("🔌 GRID DEPENDENCY")
    lines.append("─" * 40)
    lines.append(f"  Nighttime load ratio             : {_fmt(nighttime * 100)}%")
    lines.append(f"  % outside peak sun (10am-3pm)   : {_fmt(cd['grid_dependency']['pct_outside_peak_sun'])}%")
    lines.append(f"  Base load                       : {_fmt(base_var['base_load_kw'])} kW ({base_var['base_load_pct']}% of mean)")
    lines.append(f"  Variable load                   : {_fmt(base_var['variable_load_kw'])} kW")

    # ── Risk & Sensitivity ────────────────────────────────
    lines.append("")
    lines.append("⚠️  RISK & SENSITIVITY")
    lines.append("─" * 40)
    ps = rs["price_sensitivity"]
    lines.append(f"  ROI (baseline)                  : {_fmt(ps['roi_baseline'])}%")
    lines.append(f"  ROI (price +10%)                : {_fmt(ps['roi_price_up'])}%")
    lines.append(f"  ROI (price -10%)                : {_fmt(ps['roi_price_down'])}%")
    ir = rs["irradiance_sensitivity"]
    lines.append(f"  ROI (sun +10%)                  : {_fmt(ir['roi_sun_up'])}%")
    lines.append(f"  ROI (sun -10%)                  : {_fmt(ir['roi_sun_down'])}%")
    st = rs["stability"]
    lines.append(f"  Consumption volatility (CV)     : {_fmt(st['consumption_volatility'], decimals=4)}")
    lines.append(f"  Sunlight volatility (CV)        : {_fmt(st['sunlight_volatility'], decimals=4)}")
    lines.append(f"  Combined risk score             : {_fmt(st['combined_risk_score'], decimals=4)}")

    # ── EV & Budget ───────────────────────────────────────
    eb = features["ev_and_budget"]
    ba = eb["budget_analysis"]
    lines.append("")
    lines.append("🚗 EV & BUDGET SUMMARY")
    lines.append("─" * 40)
    lines.append(f"  Number of EVs                   : {eb['num_evs']}")
    lines.append(f"  Est EV annual charging load     : {_fmt(eb['ev_annual_charging_kwh'])} kWh")
    lines.append(f"  Total annual kWh (house + EV)   : {_fmt(eb['total_annual_kwh_with_ev'])} kWh")
    lines.append(f"  PV installation budget          : ${_fmt(eb['pv_budget_usd'])}")
    lines.append(f"  Max panels within budget        : {ba['max_panels']}")
    lines.append(f"  Total system cost (at budget)   : ${_fmt(ba['total_cost_usd'])}")
    lines.append(f"  Annual production (at budget)   : {_fmt(ba['annual_production_kwh'])} kWh")
    lines.append(f"  Annual savings (at budget)      : ${_fmt(ba['annual_savings_usd'])}")
    lines.append(f"  Break-even (at budget)          : {_fmt(ba['break_even_years'])} years")

    lines.append("")
    lines.append("=" * 64)

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Feature engineering for PV sizing.")
    parser.add_argument("--elec", default=DEFAULT_ELEC_PATH, help="Electricity CSV")
    parser.add_argument("--weather", default=DEFAULT_WEATHER_PATH, help="Weather CSV")
    parser.add_argument("--household", default=DEFAULT_HOUSEHOLD_PATH, help="Household CSV")
    parser.add_argument("--panels", type=int, default=10, help="Assumed panel count")
    parser.add_argument("--occupants", type=int, default=4, help="Household occupants")
    parser.add_argument("--sqm", type=float, default=150.0, help="House area m²")
    parser.add_argument("--price", type=float, default=ELECTRICITY_PRICE_PER_KWH, help="$/kWh")
    parser.add_argument("--output", default="outputs/feature_outputs.txt", help="Output file")
    args = parser.parse_args()

    logger.info("Loading data …")
    df_elec = pd.read_csv(args.elec)
    df_weather = pd.read_csv(args.weather)
    df_household = pd.read_csv(args.household)

    logger.info("Extracting features …")
    features = extract_all_features(
        df_elec, df_weather, df_household,
        num_panels=args.panels,
        occupants=args.occupants,
        house_sqm=args.sqm,
        price_per_kwh=args.price,
    )

    summary = format_for_llm(features)

    # Ensure output directory exists
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(summary, encoding="utf-8")
    logger.info("Summary saved to %s", args.output)

    print(summary)


if __name__ == "__main__":
    main()
