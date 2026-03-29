# Enhanced Household Electricity Usage Generator

## Overview
This script generates realistic per-household hourly electricity usage data from regional load data, incorporating 9 location-based variability factors.

## Features

### 9 Variability Factors:
1. **Longitude (Coastal-Inland Climate)**: 0.85x (coastal) to 1.25x (inland)
2. **Latitude (North-South Microclimate)**: 0.90x (north) to 1.10x (south)
3. **Elevation Proxy**: Based on lat/lon patterns (1.0-1.15x)
4. **Household Characteristics**: Home size + efficiency (0.7-1.3x combined)
5. **Neighborhood Density**: Urban apartments (0.6x) to suburban sprawl (1.4x)
6. **Economic/Home Age**: Varies by neighborhood type (0.9-1.3x)
7. **Solar Adoption** ☀️: Daylight-dependent reduction (30-60% during sun hours)
8. **EV Charging** 🔌: Nighttime charging window (3-7 kW for 3-6 hours)
9. **Multi-generational Homes**: Extended families (1.2-1.5x)

### Key Capabilities:
- ✅ Fully deterministic (same lat/lon always produces same results)
- ✅ Hourly granularity preserved from input data
- ✅ Physically realistic patterns (solar only works during day, EVs charge at night)
- ✅ Location-specific probabilities for solar/EV adoption
- ✅ Comprehensive comments explaining every factor

## Usage

### Basic Usage:
```python
# Edit these two lines in generate_household_data.py
TARGET_LAT = 32.7157   # Your target latitude
TARGET_LON = -117.1611 # Your target longitude

# Run the script
python generate_household_data.py
```

### Output:
- Filename: `household_data_{lat}_{lon}.csv`
- Format: Two columns (datetime_local, household_kw)
- One row per hour with consumption in kilowatts

## Example Locations

### Downtown San Diego (Baseline)
```python
TARGET_LAT = 32.7157
TARGET_LON = -117.1611
```
- Average: 44.45 kWh/day
- No solar, no EV

### La Jolla Coastal (Solar)
```python
TARGET_LAT = 32.8510
TARGET_LON = -117.2700
```
- Average: 40.43 kWh/day
- Solar reduces daytime usage by up to 41%

### La Jolla Affluent (Solar + EV)
```python
TARGET_LAT = 32.8550
TARGET_LON = -117.2700
```
- Average: 74.20 kWh/day
- Solar + EV charging (19:00-00:00)

## How It Works

### Input:
`San_Diego_Load_EIA_Fixed.csv` - Regional hourly load in MW

### Processing:
1. Converts regional MW to average household kW
2. Applies 7 scalar multipliers (factors 1-6, 9)
3. Applies time-dependent solar curve (factor 7)
4. Adds time-dependent EV charging (factor 8)
5. Adds small hourly noise for realism (±3%)

### Output:
Realistic hourly household consumption reflecting:
- Geographic climate variations
- Household characteristics
- Solar panel generation patterns
- EV charging schedules
- Neighborhood demographics

## Validation

The script has been tested and validated for:
- ✅ Solar reduction only during daylight (6 AM - 6 PM)
- ✅ EV charging only during nighttime window (user-specific 3-6 hours)
- ✅ Proper scaling from regional to household level
- ✅ Reproducibility (same location = same output)
- ✅ Physically realistic patterns

## Technical Details

### Solar Implementation:
- Uses sine wave approximation for daylight intensity
- Peak reduction at solar noon (12:00 PM)
- Zero impact at night
- System size varies: 40-70% peak reduction

### EV Implementation:
- Random charging start time: 18:00-23:00
- Random charging duration: 3-6 hours
- Charger power: 3-7 kW (Level 1/2 mix)
- Handles midnight wrap-around correctly

### Deterministic Randomness:
- Uses SHA256 hash of lat/lon as seed
- Different factors use seed offsets (+1000, +2000, +3000)
- Ensures reproducibility while maintaining independence

## Requirements
- Python 3.x
- pandas
- numpy
- hashlib (standard library)
