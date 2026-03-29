# Step 2: Data Extraction (`data_extractor.py`)

## Overview

The Data Extraction step is **Step 0** of the pipeline — it runs **before** feature engineering and is responsible for regenerating all 3 CSV data sources from scratch based on the configured latitude/longitude. This ensures that every pipeline run uses **fresh, location-specific data** rather than stale pre-existing files.

---

## Architecture Position

```
                    ┌─────────────────────┐
                    │   WorkflowConfig     │
                    │  (lat, lon, paths)   │
                    └─────────┬───────────┘
                              │
                              ▼
         ┌────────────────────────────────────────────┐
         │           DATA EXTRACTOR                    │
         │                                            │
         │   ┌──────────────────────────────────┐     │
         │   │  regenerate_weather_csv()         │     │
         │   │  Open-Meteo API → weather_data.csv│     │
         │   └──────────────────────────────────┘     │
         │                                            │
         │   ┌──────────────────────────────────┐     │
         │   │  regenerate_household_csv()       │     │
         │   │  EIA Regional CSV → household.csv │     │
         │   └──────────────────────────────────┘     │
         │                                            │
         │   ┌──────────────────────────────────┐     │
         │   │  regenerate_electricity_csv()     │     │
         │   │  household.csv → electricity.csv  │     │
         │   └──────────────────────────────────┘     │
         └────────────────────────────────────────────┘
                              │
                              ▼
                   3 CSV files ready for
                   Feature Engineering
```

---

## Files Involved

| File | Role | Lines of Code |
|------|------|---------------|
| `data_extractor.py` | Orchestration wrapper — calls extraction scripts | 221 lines |
| `data_extraction/weather_data.py` | Open-Meteo API client for weather data | 215 lines |
| `data_extraction/Household_electricity_data/household_extraction_per_house.py` | EIA regional load → per-household generator | 748 lines |
| `data_extraction/Household_electricity_data/San_Diego_Load_EIA_Fixed.csv` | Source: EIA regional hourly load data (MW) | ~44,000 rows |

---

## Three Extraction Functions

### 2.1 Weather Data Extraction (`regenerate_weather_csv()`)

**Source:** [Open-Meteo Historical Weather API](https://open-meteo.com/)

**Process:**

1. Compute date range: `(today - 7 days - 5 years)` → `(today - 7 days)`
2. Fetch daily + hourly data from Open-Meteo for the given lat/lon
3. Build daily DataFrame with max/min/avg for temperature, irradiance, cloud cover
4. Aggregate daily → weekly (7-day buckets)
5. Save as `data/weather_data.csv`

**API Parameters:**

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `latitude` | e.g., `32.7157` | Location coordinate |
| `longitude` | e.g., `-117.1611` | Location coordinate |
| `daily` | `temperature_2m_max`, `temperature_2m_min`, `shortwave_radiation_sum` | Daily weather variables |
| `hourly` | `cloud_cover`, `shortwave_radiation` | Hourly variables for daily aggregation |
| `timezone` | `auto` | Local timezone |
| `years_back` | `5` | Historical data span |

**Output CSV Schema (`weather_data.csv`):**

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `week_number` | int | — | Sequential week index (1, 2, 3, …) |
| `weekly_max_temperature` | float | °C | Highest daily max temp in the week |
| `weekly_min_temperature` | float | °C | Lowest daily min temp in the week |
| `weekly_avg_temperature` | float | °C | Mean of daily avg temps |
| `weekly_max_irradiance` | float | W/m² | Highest hourly irradiance recorded |
| `weekly_min_irradiance` | float | W/m² | Lowest hourly irradiance (typically 0) |
| `weekly_avg_irradiance` | float | W/m² | Mean hourly irradiance across the week |
| `weekly_max_cloud_cover` | float | % | Max cloud cover percentage |
| `weekly_min_cloud_cover` | float | % | Min cloud cover percentage |
| `weekly_avg_cloud_cover` | float | % | Mean cloud cover |

**Typical Output:** ~261–263 rows (5 years × ~52 weeks/year)

**Sample Data (San Diego):**

| week | max_temp | min_temp | avg_temp | max_irr | avg_irr | avg_cloud |
|------|----------|----------|----------|---------|---------|-----------|
| 1 | 25.1°C | 5.6°C | 13.38°C | 801 W/m² | 203.69 W/m² | 18.52% |
| 17 | 32.0°C | 10.9°C | 20.44°C | 1040 W/m² | 343.80 W/m² | 31.11% |
| 28 | 36.8°C | 15.4°C | 25.14°C | 939 W/m² | 280.23 W/m² | 31.48% |

---

### 2.2 Household Data Extraction (`regenerate_household_csv()`)

**Source:** EIA Regional Load Data (`San_Diego_Load_EIA_Fixed.csv`)

**Process:**

1. Load regional hourly MW data (~1,040,149 SDG&E residential meters)
2. Divide by total customer count to get per-household baseline kW
3. Apply 9 location-specific variability factors based on lat/lon:
   - Coastal proximity effect
   - Elevation-based adjustment
   - Urban heat island factor
   - Seasonal amplification
   - Time-of-day patterns
   - And 4 others
4. Generate deterministic random seed from `SHA256(lat_lon)` → reproducible output
5. Output hourly per-household kW data

**Key Constants:**

| Constant | Value | Description |
|----------|-------|-------------|
| `TOTAL_CUSTOMERS` | 1,040,149 | Approximate SDG&E residential meters |
| `COASTAL_LON_REF` | -117.25 | Longitude reference for coastal baseline |
| `CITY_CENTER_LAT` | 32.7157 | Downtown San Diego latitude |
| `CITY_CENTER_LON` | -117.1611 | Downtown San Diego longitude |

**Output CSV Schema (`household_data.csv`):**

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `datetime_local` | datetime | — | Hourly timestamp (local timezone) |
| `household_kw` | float | kW | Per-household electricity demand |

**Typical Output:** ~44,306 rows (5 years × 365.25 days × 24 hours)

**Sample Data:**

| datetime_local | household_kw |
|---------------|-------------|
| 2020-12-31 16:00 | 3.195 kW |
| 2020-12-31 17:00 | 4.112 kW |
| 2021-01-01 02:00 | 3.326 kW |
| 2021-01-01 14:00 | 2.062 kW |

**Reproducibility:** Same (lat, lon) → same SHA256 seed → identical output every time.

---

### 2.3 Electricity Data Extraction (`regenerate_electricity_csv()`)

**Source:** The household CSV generated in step 2.2

**Process:**

1. Read `household_data.csv` with hourly timestamps
2. Aggregate to **daily** stats: `daily_max`, `daily_min`, `daily_avg`
3. Aggregate daily → **weekly** (7-day buckets):
   - `weekly_aggregated_max_load` = max of daily maxes
   - `weekly_aggregated_min_load` = min of daily mins
   - `weekly_aggregated_avg_load` = mean of daily averages
4. Round to 4 decimal places
5. Save as `data/electricity_data.csv`

**Output CSV Schema (`electricity_data.csv`):**

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `week_number` | int | — | Sequential week index (1, 2, 3, …) |
| `weekly_aggregated_max_load` | float | kW | Peak load in the week |
| `weekly_aggregated_min_load` | float | kW | Minimum load in the week |
| `weekly_aggregated_avg_load` | float | kW | Average load across the week |
| `week_start_date` | date | — | First day of the week |

**Typical Output:** ~267 rows (5 years × ~52 weeks + partial weeks)

**Sample Data (San Diego):**

| week | max_load | min_load | avg_load | start_date |
|------|----------|----------|----------|------------|
| 1 | 4.839 kW | 1.982 kW | 3.5136 kW | 2020-12-31 |
| 28 | 5.572 kW | 2.814 kW | 3.9107 kW | 2021-07-08 |
| 52 | 4.750 kW | 1.370 kW | 3.1924 kW | 2021-12-23 |

---

## Convenience Function: `regenerate_all()`

Orchestrates all 3 extractions in a single call:

```python
regenerate_all(
    latitude=32.7157,
    longitude=-117.1611,
    weather_csv="data/weather_data.csv",
    household_csv="data/household_data.csv",
    electricity_csv="data/electricity_data.csv",
    years_back=5,
)
```

**Returns:** `dict[str, Path]` mapping `"weather"`, `"household"`, `"electricity"` → absolute file paths.

**Execution Order (dependency chain):**

```
1. regenerate_weather_csv()     → weather_data.csv       (independent)
2. regenerate_household_csv()   → household_data.csv     (independent)
3. regenerate_electricity_csv() → electricity_data.csv   (depends on #2)
```

---

## Data Volume Summary

| CSV File | Rows | Columns | Granularity | Time Span |
|----------|------|---------|-------------|-----------|
| `weather_data.csv` | ~261 | 10 | Weekly | 5 years |
| `household_data.csv` | ~44,306 | 2 | Hourly | 5 years |
| `electricity_data.csv` | ~267 | 5 | Weekly | 5 years |

**Total data points generated per location:** ~44,306 hourly + ~528 weekly ≈ **44,834 data points**

---

## Batch Context

During the 30-location batch run, `regenerate_all()` is called **30 times** — once per location. Each call:

- Makes **1 HTTP request** to Open-Meteo API (weather)
- Reads **1 local CSV** (`San_Diego_Load_EIA_Fixed.csv`) and applies location-specific transforms (household)
- Aggregates the household data (electricity)
- **Overwrites** `data/weather_data.csv`, `data/household_data.csv`, and `data/electricity_data.csv`

The 30 locations span the San Diego County area:

| Metric | Value |
|--------|-------|
| Latitude range | 32.5839 (Imperial Beach) → 33.3764 (Fallbrook) |
| Longitude range | -117.3795 (Oceanside) → -116.7664 (Alpine) |
| Total locations | 30 |

---

## Error Handling

| Error | Condition | Recovery |
|-------|-----------|----------|
| `FileNotFoundError` | `San_Diego_Load_EIA_Fixed.csv` missing | Fatal — cannot generate household data |
| `requests.ConnectionError` | Open-Meteo API unreachable | Fatal — cannot generate weather data |
| `HTTPError` | Open-Meteo returns non-200 status | Fatal — `raise_for_status()` |

---

## Dependencies

- `pandas>=2.0.0` — CSV reading, datetime parsing, aggregation
- `numpy` — numerical operations in household variability factors
- `requests>=2.31.0` — Open-Meteo API calls
- `hashlib` (stdlib) — deterministic seed generation for household data
