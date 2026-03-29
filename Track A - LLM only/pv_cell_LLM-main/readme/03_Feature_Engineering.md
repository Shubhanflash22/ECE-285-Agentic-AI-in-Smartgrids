# Step 3: Feature Engineering (`feature_engineering.py`)

## Overview

Feature Engineering is the **computational core** of the pipeline. It takes the 3 raw CSV data sources (electricity, weather, household) and computes **60+ domain-specific features** organised into 7 categories. The output is a structured, human-readable text summary that the LLM uses as its primary data context for PV panel sizing recommendations.

This is the **largest file** in the project at **1,631 lines of code**.

---

## Architecture Position

```
┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ electricity.csv  │  │  weather.csv     │  │  household.csv   │
│ (267 rows)       │  │  (261 rows)      │  │  (44,306 rows)   │
└────────┬────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                    │                      │
         └────────────────────┼──────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │     FEATURE ENGINEERING        │
              │                               │
              │  extract_all_features()       │
              │     ├─ 1. Electricity (15+)   │
              │     ├─ 2. Weather/Solar (12+) │
              │     ├─ 3. Household (7+)      │
              │     ├─ 4. Cross-Dataset (10+) │
              │     ├─ 5. Risk/Sensitivity(8+)│
              │     ├─ 6. EV & Budget (5+)    │
              │     └─ 7. Formatting          │
              │                               │
              │  format_for_llm(features)     │
              └───────────────┬───────────────┘
                              │
                              ▼
                   Feature-Engineered Summary
                   (structured text, ~4,000 chars)
```

---

## PV Panel Constants

The following constants define the assumptions used throughout feature engineering:

| Constant | Value | Description |
|----------|-------|-------------|
| `PV_PANEL_WATT_PEAK` | 400 Wp | Watt-peak rating per panel (typical residential) |
| `PV_EFFICIENCY_LOSS` | 0.80 (80%) | System-level derating (inverter, wiring, soiling) |
| `PV_OPTIMAL_TEMP_LOW` | 15°C | Below this, panels operate at peak efficiency |
| `PV_OPTIMAL_TEMP_HIGH` | 35°C | Above this, efficiency drops ~0.4%/°C |
| `PV_PANEL_COST` | $350/panel | Cost per panel |
| `PV_INSTALL_FIXED_COST` | $4,000 | One-time installation cost |
| `PV_LIFESPAN_YEARS` | 25 years | Expected panel lifespan |
| `DISCOUNT_RATE` | 0.05 (5%) | For NPV/IRR calculations |
| `ELECTRICITY_PRICE_PER_KWH` | $0.31/kWh | SDG&E average residential rate |
| `_EV_KWH_PER_YEAR` | 3,500 kWh | Annual EV charging consumption per vehicle |

---

## Feature Categories — Detailed Breakdown

### Category 1: Electricity Consumption Features (15 functions)

#### 1a. Load Distribution Features (7 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `peak_weekly_consumption()` | float (kW) | 7.79 kW | Highest recorded weekly max load |
| `percentile_95_weekly_consumption()` | float (kW) | 2.67 kW | 95th percentile of avg load — sizing target |
| `min_weekly_consumption()` | float (kW) | 0.32 kW | Lowest weekly minimum load |
| `load_variance()` | float | — | Variance of weekly avg load |
| `load_std()` | float (kW) | 0.23 kW | Std deviation of weekly avg load |
| `coefficient_of_variation()` | float | 0.1040 | CV = std/mean; >0.3 = high volatility |
| `load_iqr()` | float (kW) | 0.27 kW | Interquartile range — robust spread measure |

#### 1b. Seasonal Strength Metrics (4 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `seasonal_index_per_month()` | dict {month: index} | M7=1.08, M8=1.16 | Index >1.0 = above-average month |
| `peak_to_trough_ratio()` | float | 1.33 | Ratio of highest to lowest monthly avg |
| `winter_vs_summer_ratio()` | float | 0.94 | <1.0 means summer-peaking demand |
| `consumption_trend_slope()` | float (kW/week) | 0.00 | Linear regression slope over time |

#### 1c. Growth/Trend Signals (3 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `year_over_year_growth()` | dict {label: %} | 2022 vs 2021: +3.2% | Annual consumption change |
| `moving_average_trend_slope()` | float | 0.0006 kW/week | 4-week MA trend slope |
| `change_point_count()` | int | 12 | Weeks with >2σ changes (sudden shifts) |

#### 1d. Peak Load Metrics (3 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `max_single_week_spike()` | float (kW) | 7.79 kW | Largest single-week max load |
| `weeks_above_threshold()` | int | 0 | Weeks where avg > 1.5× mean |
| `consecutive_high_load_streaks()` | int | 5 weeks | Longest streak above 1.2× mean |

---

### Category 2: Weather / Solar Potential Features (12 functions)

#### 2a. Solar Energy Potential Estimation (7 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `avg_weekly_irradiance()` | float (W/m²) | 219.82 W/m² | Average solar irradiance |
| `annual_total_irradiance()` | float (W/m²) | — | Sum of weekly irradiance |
| `estimated_peak_sun_hours_daily()` | float (hrs) | 1.76 hrs | PSH from irradiance data |
| `estimated_annual_sunlight_hours()` | float (hrs) | 642.40 hrs | Total annual sunlight hours |
| `seasonal_irradiance_index()` | dict {season: index} | Spring=1.36, Summer=0.99 | Seasonal solar variation |
| `irradiance_variance()` | float | 4,768.42 | Variance — inconsistency measure |
| `temperature_irradiance_correlation()` | float | 0.5699 | Pearson correlation temp↔irradiance |

#### 2b. PV Efficiency Impact Factors (3 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `weeks_above_pv_optimal_temp()` | int | 1 | Weeks > 35°C (efficiency drops) |
| `cloudy_week_frequency()` | float (%) | 9.58% | Fraction of weeks > 70% cloud cover |
| `sunlight_consistency_score()` | float | 0.3141 | CV of irradiance (lower = more consistent) |

#### 2c. Production Alignment Metrics (3 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `consumption_irradiance_correlation()` | float | -0.4587 | Negative = consumption peaks when sun is low |
| `lag_correlation()` | dict {lag: corr} | lag0=-0.459, lag1=-0.411 | Cross-correlation at weekly lags |
| `monthly_production_to_consumption_ratio()` | dict {month: ratio} | — | PV production ÷ consumption per month |

---

### Category 3: Household Data Features (7 functions)

#### 3a. Normalized Metrics (4 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `kwh_per_occupant()` | float (kWh) | 13.44 kWh/person/day | Consumption per person |
| `kwh_per_sqm()` | float (kWh) | 0.3584 kWh/m²/day | Consumption per unit area |
| `electricity_cost_per_occupant()` | float ($) | $4.17/person/day | Cost per occupant |
| `electricity_cost_per_sqm()` | float ($) | $0.1111/m²/day | Cost per square metre |

#### 3b. Cost Structure (1 function)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `effective_cost_per_kwh()` | float ($) | $0.31/kWh | Current tariff rate |

#### 3c. Financial Health (3 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `annual_electricity_expenditure()` | float ($) | $6,083.46/year | Annual electricity bill |
| `projected_5yr_electricity_cost()` | float ($) | $32,297.89 | 5-year projection with 3% annual increase |
| `household_annual_kwh()` | float (kWh) | 19,624.05 kWh/year | Total annual consumption |

---

### Category 4: Cross-Dataset Derived Features (10 functions)

#### 4a. Self-Sufficiency Metrics (4 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `estimated_annual_production_per_panel()` | float (kWh) | 154.05 kWh | Annual yield per 400W panel |
| `panels_needed_for_offset()` | int | 128 (100%), 90 (70%), 64 (50%) | Panel count for target offset |
| `overproduction_months()` | int | 12 | Months where PV > consumption |
| `underproduction_months()` | int | 0 | Months where PV < consumption |

**Production Formula:**

```
daily_kwh_per_panel = avg_irradiance × 6_hrs × (400W/1000) × 0.80
annual_kwh = daily_kwh × 365
```

#### 4b. Payback Analysis Features (5 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `break_even_years()` | float (yrs) | 15.70 years | Simple payback period |
| `npv_10_years()` | float ($) | -$3,322.54 | Net present value over 10 years |
| `irr_estimate()` | float | 6.78% | Internal rate of return (bisection method) |
| `roi_percent()` | float (%) | 132.15% | Total ROI over 25-year lifespan |
| `payback_vs_lifespan()` | dict | 15.7 yr / 25 yr → 9.3 yr profit | Payback compared to panel life |

**System Cost Formula:**

```
total_cost = $4,000 (fixed) + num_panels × $350
```

#### 4c. Grid Dependency Metrics (3 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `nighttime_load_ratio()` | float (%) | 70.23% | Consumption before 8 AM or after 6 PM |
| `pct_consumption_outside_peak_sun()` | float (%) | 85.76% | Consumption outside 10 AM – 3 PM |
| `base_load_vs_variable_load()` | dict | base=1.29 kW (57.3%), variable=0.96 kW | Always-on vs. variable demand |

---

### Category 5: Risk & Sensitivity Features (8 functions)

#### 5a. Sensitivity Analysis (3 functions)

| Function | Output | San Diego Values | Purpose |
|----------|--------|-----------------|---------|
| `roi_under_price_change()` | dict | baseline=132.15%, +10%=155.37%, -10%=108.94% | ROI sensitivity to tariff changes |
| `roi_under_irradiance_change()` | dict | sun+10%=155.36%, sun-10%=108.93% | ROI sensitivity to sunlight variation |
| `roi_under_consumption_growth()` | dict | growth_0%=132.15%, growth_2%=132.15% | ROI under demand growth |

#### 5b. Stability Metrics (3 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `consumption_volatility_score()` | float | 0.1040 | CV of electricity demand |
| `sunlight_volatility_score()` | float | 0.3141 | CV of solar irradiance |
| `combined_risk_score()` | float | 0.2090 | Average of consumption + sunlight volatility |

---

### Category 6: EV & Budget Features (2 functions)

| Function | Output | San Diego Value | Purpose |
|----------|--------|----------------|---------|
| `ev_annual_charging_kwh()` | float (kWh) | 3,500 kWh (1 EV) | Additional EV charging demand |
| `panels_within_budget()` | dict | max=31, cost=$14,850, prod=4,775.55 kWh | Budget-constrained analysis |

**Budget Analysis Output (San Diego, $15,000 budget):**

| Metric | Value |
|--------|-------|
| Max panels within budget | 31 |
| Total system cost | $14,850 |
| Annual production | 4,775.55 kWh |
| Annual savings | $1,480.42 |
| Break-even (at budget) | 10.03 years |

---

## Output: Feature-Engineered Summary

### `format_for_llm()` Function

Converts the nested feature dictionary into a **clean, structured text block** (~4,000 characters) with 7 sections:

1. **📊 ELECTRICITY CONSUMPTION SUMMARY** — 20+ metrics
2. **☀️ SOLAR POTENTIAL SUMMARY** — 12+ metrics
3. **🏠 HOUSEHOLD SUMMARY** — 7 metrics
4. **⚡ PV SIZING & FINANCIAL ANALYSIS** — 14+ metrics
5. **🔌 GRID DEPENDENCY** — 4 metrics
6. **⚠️ RISK & SENSITIVITY** — 8 metrics
7. **🚗 EV & BUDGET SUMMARY** — 9 metrics

**Total:** ~75 individual metrics per location

### Sample Output (San Diego)

```
================================================================
  FEATURE-ENGINEERED SUMMARY FOR LLM
================================================================

📊 ELECTRICITY CONSUMPTION SUMMARY
────────────────────────────────────────
  Annual household consumption    : 19,624.05 kWh
  Avg daily consumption           : 53.76 kWh
  Avg weekly load                 : 2.25 kW
  Peak weekly max load            : 7.79 kW
  ...

☀️  SOLAR POTENTIAL SUMMARY
────────────────────────────────────────
  Avg weekly irradiance           : 219.82 W/m²
  Est daily peak sun hours        : 1.76 hrs
  ...

⚡ PV SIZING & FINANCIAL ANALYSIS
────────────────────────────────────────
  Est annual production / panel    : 154.05 kWh
  Panels for 100% offset          : 128
  Break-even                      : 15.70 years
  ROI (25 yr)                     : 132.15%
  ...

🚗 EV & BUDGET SUMMARY
────────────────────────────────────────
  Total annual kWh (house + EV)   : 23,124.05 kWh
  Max panels within budget        : 31
  Break-even (at budget)          : 10.03 years
================================================================
```

---

## Execution Flow

```python
# Called by pipeline.py
features = extract_all_features(
    df_elec, df_weather, df_household,
    num_panels=10, occupants=4, house_sqm=150.0,
    price_per_kwh=0.31, num_evs=1, pv_budget=15000.0,
)
# Returns nested dict with ~75 values

feature_context = format_for_llm(features)
# Returns formatted string (~4,000 chars)
```

---

## CLI Standalone Usage

Feature engineering can also be run independently:

```bash
python feature_engineering.py \
  --elec data/electricity_data.csv \
  --weather data/weather_data.csv \
  --household data/household_data.csv \
  --panels 10 --occupants 4 --sqm 150 --price 0.31 \
  --output outputs/feature_outputs.txt
```

---

## Dependencies

- `pandas>=2.0.0` — DataFrame operations, groupby, rolling averages
- `numpy` — Linear regression (`polyfit`), quantiles, statistical operations
- `math` — `ceil()` for panel count rounding
- Python `pathlib` (stdlib) — output path handling
