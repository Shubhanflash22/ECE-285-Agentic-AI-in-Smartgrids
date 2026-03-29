# ═════════════════════════════════════════════════════════════════════════════
#  SAN DIEGO COORDINATE BOUNDARIES
# ═════════════════════════════════════════════════════════════════════════════
#
#  1. RECOMMENDED RESIDENTIAL RANGE (Best for this simulation)
#     --------------------------------------------------------
#     Latitude  (Min):  32.53  (Border / San Ysidro)
#     Latitude  (Max):  33.22  (Fallbrook / North County)
#     Longitude (Min): -117.26 (Coast / La Jolla) -> "West"
#     Longitude (Max): -116.90 (Alpine / Foothills) -> "East"
#
#  2. ABSOLUTE COUNTY LIMITS (Physical Borders)
#     --------------------------------------------------------
#     Latitude  (Min):  32.53  (Mexico Border)
#     Latitude  (Max):  33.51  (Riverside County Line)
#     Longitude (Min): -117.60 (San Onofre State Beach)
#     Longitude (Max): -116.08 (Imperial County Line / Borrego Desert)
#
# ═════════════════════════════════════════════════════════════════════════════

"""
Enhanced Household Electricity Usage Generator

This script takes regional hourly electricity load data (MW) and generates
realistic per-household hourly usage data (kW) for a specific location.

The script applies 9 different variability factors based on latitude/longitude
to create realistic, location-specific usage patterns while maintaining
reproducibility through seeded randomness.

Input: San_Diego_Load_EIA_Fixed.csv (Regional hourly load in MW)
Output: household_data_{lat}_{lon}.csv (Per-household hourly usage in kW)
"""

import pandas as pd
import numpy as np
import os
import hashlib

# ═════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════════

INPUT_FILENAME = r"C:\Users\shubh\Desktop\Hard disk\College(PG)\Academics at UCSD\Y1Q2\ECE 285 - Spec Topic - Signal & Image Robotics - Smartgrids\Project\San_Diego_Load_EIA_Fixed.csv"

# Target Location (Change these to generate data for different households)
TARGET_LAT = 32.7157   # Example: Downtown San Diego
TARGET_LON = -117.1609 # Example: Downtown San Diego

# Regional Constants
TOTAL_CUSTOMERS = 1040149	  # Approximate SDGE residential meters

# Geographic Reference Points
COASTAL_LON_REF = -117.25        # Reference longitude for coastal baseline
CITY_CENTER_LAT = 32.7157        # Downtown San Diego latitude
CITY_CENTER_LON = -117.1611      # Downtown San Diego longitude

# ═════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def get_output_filename(lat, lon):
    """
    Generates output filename based on coordinates.
    
    Args:
        lat: Latitude
        lon: Longitude
    
    Returns:
        Filename string like "household_data_32.72_-117.16.csv"
    """
    return f"household_data_{lat:.2f}_{lon:.2f}.csv"


def generate_location_seed(lat, lon):
    """
    Creates a deterministic integer seed based on lat/lon coordinates.
    
    This ensures that:
    1. Same location always produces same "random" characteristics
    2. Different locations produce different but reproducible characteristics
    
    Args:
        lat: Latitude
        lon: Longitude
    
    Returns:
        Integer seed for random number generator
    """
    loc_str = f"{lat}_{lon}"
    # Create SHA256 hash and convert to integer seed
    hash_obj = hashlib.sha256(loc_str.encode('utf-8'))
    return int(hash_obj.hexdigest(), 16) % (2**32)


def load_regional_data(filepath):
    """
    Loads regional MW load data and converts to average per-household kW.
    
    This is the baseline before applying any location-specific factors.
    
    Args:
        filepath: Path to CSV file with regional load data
    
    Returns:
        DataFrame with columns: datetime_local, avg_household_kw
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Could not find {filepath}")

    print(f"[1/5] Loading regional load from {filepath}...")
    df = pd.read_csv(filepath)
    
    # Parse timestamp and convert UTC -> Pacific Time
    df['datetime_utc'] = pd.to_datetime(df['Timestamp_UTC'])
    df['datetime_local'] = (df['datetime_utc']
                           .dt.tz_localize('UTC')
                           .dt.tz_convert('America/Los_Angeles'))
    
    # Downscale from regional MW to average household kW
    # Formula: (Regional_MW * 1000 kW/MW) / Number_of_Households
    df['avg_household_kw'] = (df['MW_Load'] * 1000) / TOTAL_CUSTOMERS
    
    return df[['datetime_local', 'avg_household_kw']].copy()


# ═════════════════════════════════════════════════════════════════════════════
# VARIABILITY FACTOR FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def calculate_longitude_factor(lon):
    """
    FACTOR 1: Longitude (East-West) - Distance from Coast
    
    San Diego's climate varies dramatically from coast to inland:
    - Coastal areas: Cooler, less AC needed (0.85-0.95x)
    - Mid-distance: Moderate climate (0.95-1.05x)
    - Inland areas: Hotter, more AC needed (1.05-1.25x)
    
    Args:
        lon: Longitude (negative values, e.g., -117.25)
    
    Returns:
        Multiplier based on distance from coast
    """
    # Calculate distance from coastal reference
    # More negative = further west (closer to ocean)
    # Less negative = further east (more inland)
    distance_from_coast = lon - COASTAL_LON_REF
    
    # Define climate zones
    if distance_from_coast >= 0.15:  # Very inland (e.g., -117.10 or higher)
        return 1.25
    elif distance_from_coast >= 0.10:  # Inland
        return 1.05 + (distance_from_coast - 0.10) * 4.0  # Linear 1.05->1.25
    elif distance_from_coast >= 0:  # Mid-distance
        return 0.95 + distance_from_coast * 1.0  # Linear 0.95->1.05
    elif distance_from_coast >= -0.05:  # Near coast
        return 0.90 + (distance_from_coast + 0.05) * 1.0  # Linear 0.90->0.95
    else:  # Very coastal
        return 0.85


def calculate_latitude_factor(lat):
    """
    FACTOR 2: Latitude (North-South) - Microclimates
    
    North-South variation in San Diego creates temperature gradients:
    - South (closer to border): Warmer (1.05-1.10x)
    - Central: Moderate (0.95-1.05x)
    - North: Slightly cooler (0.90-1.00x)
    
    Args:
        lat: Latitude
    
    Returns:
        Multiplier based on latitude
    """
    if lat < 32.60:  # Far south (Chula Vista, Imperial Beach)
        return 1.10
    elif lat < 32.70:  # South (Downtown, National City)
        return 1.05
    elif lat < 32.85:  # Central (Mission Valley, La Jolla)
        return 1.00
    elif lat < 32.95:  # North (Del Mar, Carmel Valley)
        return 0.95
    else:  # Far north (Encinitas, Carlsbad)
        return 0.90


def calculate_elevation_factor(lat, lon):
    """
    FACTOR 3: Elevation Proxy
    
    Elevation affects temperature and usage patterns:
    - Low elevation coastal: Mild temperatures
    - Higher elevation inland: More extreme temperatures
    
    We proxy elevation using lat/lon patterns:
    - Inland + North often = higher elevation
    
    Args:
        lat: Latitude
        lon: Longitude
    
    Returns:
        Multiplier based on estimated elevation
    """
    # Inland distance (0 to ~0.4 for San Diego)
    inland_factor = max(0, lon - COASTAL_LON_REF)
    
    # Northern areas tend to have more elevation variation
    north_factor = max(0, lat - 32.70) * 2
    
    # Combined elevation proxy (0 to ~1.0)
    elevation_proxy = inland_factor + north_factor
    
    # Higher elevation = more temperature variation = more energy use
    # Range: 1.0 (sea level) to 1.15 (high elevation)
    return 1.0 + (elevation_proxy * 0.15)


def calculate_household_characteristics(seed):
    """
    FACTOR 4: Household Characteristics
    
    Different homes have different intrinsic usage patterns:
    - Home size: Small apartment (0.7x) to large house (1.3x)
    - Efficiency: New efficient home (0.8x) to old inefficient (1.2x)
    
    Args:
        seed: Random seed for reproducibility
    
    Returns:
        Combined multiplier for household characteristics
    """
    rng = np.random.RandomState(seed)
    
    # Home size factor (0.7 to 1.3)
    # Distribution skewed toward average (1.0)
    size_factor = rng.normal(1.0, 0.15)
    size_factor = np.clip(size_factor, 0.7, 1.3)
    
    # Efficiency factor (0.8 to 1.2)
    # Better efficiency = lower multiplier
    efficiency_factor = rng.normal(1.0, 0.1)
    efficiency_factor = np.clip(efficiency_factor, 0.8, 1.2)
    
    # Combined characteristic
    return size_factor * efficiency_factor


def calculate_density_factor(lat, lon):
    """
    FACTOR 5: Neighborhood Density Factor
    
    Housing density affects home size and thus energy usage:
    - Urban core: High-density apartments/condos (0.6-0.8x)
    - Suburban: Single-family homes (0.9-1.1x)
    - Suburban sprawl: Large homes on big lots (1.1-1.4x)
    
    We calculate this based on distance from city center.
    
    Args:
        lat: Latitude
        lon: Longitude
    
    Returns:
        Multiplier based on neighborhood density
    """
    # Calculate distance from downtown San Diego
    lat_diff = lat - CITY_CENTER_LAT
    lon_diff = lon - CITY_CENTER_LON
    distance_from_center = np.sqrt(lat_diff**2 + lon_diff**2)
    
    if distance_from_center < 0.03:  # ~2 miles - Urban core
        return 0.7
    elif distance_from_center < 0.08:  # ~5 miles - Inner suburbs
        return 0.9
    elif distance_from_center < 0.15:  # ~10 miles - Outer suburbs
        return 1.1
    else:  # Far suburbs / sprawl
        return 1.3


def calculate_economic_age_factor(lat, lon):
    """
    FACTOR 6: Economic/Home Age Proxy
    
    Different neighborhoods have different home ages and economic profiles:
    - Coastal affluent: Newer homes, better insulation, but larger (1.0-1.2x)
    - Inland newer developments: Efficient modern homes (0.9-1.1x)
    - Older urban areas: Less efficient older homes (1.1-1.3x)
    
    Args:
        lat: Latitude
        lon: Longitude
    
    Returns:
        Multiplier based on economic/age characteristics
    """
    # Coastal areas (west of -117.20)
    is_coastal = lon < -117.20
    
    # Northern areas (above 32.80) - often affluent
    is_north = lat > 32.80
    
    # Urban core
    lat_diff = lat - CITY_CENTER_LAT
    lon_diff = lon - CITY_CENTER_LON
    distance_from_center = np.sqrt(lat_diff**2 + lon_diff**2)
    is_urban_core = distance_from_center < 0.05
    
    # Logic for different area types
    if is_coastal and is_north:  # La Jolla, Del Mar - affluent newer
        return 1.15
    elif is_coastal and not is_north:  # Coastal but south - mixed
        return 1.05
    elif is_urban_core:  # Older urban neighborhoods
        return 1.25
    elif lon > -117.00:  # Far inland - newer developments
        return 0.95
    else:  # General inland/suburban
        return 1.10


def apply_solar_profile(df, lat, lon, seed):
    """
    FACTOR 7: Solar Adoption with Daylight Curve
    
    Some households have solar panels, which reduce grid consumption DURING DAYLIGHT.
    Probability varies by neighborhood (income proxy + sun exposure).
    
    If household has solar:
    - Reduces consumption during daylight hours (6 AM - 6 PM)
    - Peak reduction at noon (up to 40-70% reduction)
    - No effect at night (solar doesn't work without sunlight!)
    
    Args:
        df: DataFrame with datetime_local column
        lat: Latitude
        lon: Longitude
        seed: Random seed for reproducibility
    
    Returns:
        Array of hourly multipliers (1.0 at night, <1.0 during day if solar)
    """
    rng = np.random.RandomState(seed + 1000)  # Offset seed for independence
    
    # Determine solar probability based on location
    is_coastal = lon < -117.20
    is_north = lat > 32.80
    is_affluent_area = is_coastal and is_north
    
    # Calculate distance from center for density proxy
    lat_diff = lat - CITY_CENTER_LAT
    lon_diff = lon - CITY_CENTER_LON
    distance_from_center = np.sqrt(lat_diff**2 + lon_diff**2)
    is_urban_core = distance_from_center < 0.05
    
    # Solar adoption probabilities
    if is_affluent_area:  # La Jolla, Del Mar
        solar_prob = 0.35
    elif is_coastal or (lon > -117.00):  # Coastal or inland suburbs
        solar_prob = 0.20
    elif is_urban_core:  # Urban apartments
        solar_prob = 0.05
    else:  # General areas
        solar_prob = 0.15
    
    # Determine if household has solar
    has_solar = rng.random() < solar_prob
    
    if not has_solar:
        # No solar: multiplier is 1.0 everywhere
        return np.ones(len(df))
    
    print("   -> House has Solar! Applying daylight curve.")
    
    # ─── Create Daylight-Based Solar Generation Curve ───────────────────────
    
    # Extract hour of day from timestamps
    hours = df['datetime_local'].dt.hour.values
    
    # Solar generation follows a bell curve during daylight hours
    # Peak at noon (12:00), active from 6 AM to 6 PM
    # Using sine wave approximation: sin((hour - 6) * π / 12)
    solar_intensity = np.clip(np.sin((hours - 6) * np.pi / 12), 0, 1)
    
    # Explicitly mask out nighttime hours (before 6 AM and after 6 PM)
    solar_intensity[(hours < 6) | (hours > 18)] = 0
    
    # Determine system size (how much it reduces peak load at noon)
    # 0.4 means 60% reduction at peak, 0.7 means 30% reduction at peak
    max_reduction = rng.uniform(0.4, 0.7)
    
    # Calculate hourly multiplier
    # At noon with max solar: multiplier = 1.0 - (1.0 * max_reduction)
    # At night with no solar: multiplier = 1.0 - (0.0 * max_reduction) = 1.0
    hourly_multipliers = 1.0 - (solar_intensity * (1.0 - max_reduction))
    
    return hourly_multipliers


def apply_ev_charging(df, lat, lon, seed):
    """
    FACTOR 8: EV Charging Pattern with Nighttime Schedule
    
    Some households have electric vehicles, which increases electricity usage
    DURING SPECIFIC CHARGING HOURS (typically at night).
    
    EV adoption varies by neighborhood income/environmental consciousness.
    
    If household has EV:
    - Adds charging load during a 3-6 hour window (typically 6 PM - 2 AM)
    - Charging power: 3-7 kW (Level 1 or Level 2 charger)
    - No charging during non-charging hours
    
    Args:
        df: DataFrame with datetime_local column
        lat: Latitude
        lon: Longitude
        seed: Random seed for reproducibility
    
    Returns:
        Array of additional kW to add (0 during non-charging, 3-7 during charging)
    """
    rng = np.random.RandomState(seed + 2000)  # Offset seed for independence
    
    # Determine EV probability based on location
    is_coastal = lon < -117.20
    is_north = lat > 32.80
    is_affluent_area = is_coastal and is_north
    
    # Calculate distance from center for density proxy
    lat_diff = lat - CITY_CENTER_LAT
    lon_diff = lon - CITY_CENTER_LON
    distance_from_center = np.sqrt(lat_diff**2 + lon_diff**2)
    is_urban_core = distance_from_center < 0.05
    
    # EV adoption probabilities
    if is_affluent_area:  # Affluent coastal/north
        ev_prob = 0.30
    elif is_coastal or (lon > -117.05 and lat > 32.75):  # Coastal or nice suburbs
        ev_prob = 0.15
    elif is_urban_core:  # Urban core
        ev_prob = 0.10
    else:  # General areas
        ev_prob = 0.08
    
    # Determine if household has EV
    has_ev = rng.random() < ev_prob
    
    if not has_ev:
        # No EV: 0 kW added at all hours
        return np.zeros(len(df))
    
    print("   -> House has EV! Applying charging schedule.")
    
    # ─── Create Charging Schedule ───────────────────────────────────────────
    
    # Random charging start time between 18:00 (6 PM) and 23:00 (11 PM)
    # Most people plug in when they get home from work
    start_hour = rng.randint(18, 24)
    
    # Random charging duration between 3 and 6 hours
    # Enough to fully charge a typical daily commute (30-50 miles)
    duration = rng.randint(3, 7)
    
    # Extract hour of day from timestamps
    hours = df['datetime_local'].dt.hour.values
    
    # Calculate end hour (may wrap around midnight)
    end_hour = (start_hour + duration) % 24
    
    # Create boolean mask for charging hours
    if start_hour < end_hour:
        # Charging happens within same day (e.g., 18:00 to 22:00)
        is_charging = (hours >= start_hour) & (hours < end_hour)
    else:
        # Charging wraps around midnight (e.g., 22:00 to 02:00)
        is_charging = (hours >= start_hour) | (hours < end_hour)
    
    # Determine charger power
    # Level 1 (120V): ~1.4 kW
    # Level 2 (240V): 3.3-7.7 kW
    # Most households have Level 2, some have Level 1
    charger_power = rng.uniform(3.0, 7.0)
    
    # Create load array: charger_power during charging hours, 0 otherwise
    ev_load = np.where(is_charging, charger_power, 0.0)
    
    return ev_load


def calculate_multigenerational_factor(lat, lon, seed):
    """
    FACTOR 9: Multi-generational Home Factor
    
    Some households have extended families (multi-generational living),
    which increases overall consumption.
    
    This is more common in certain demographics and neighborhoods.
    
    Args:
        lat: Latitude
        lon: Longitude
        seed: Random seed for reproducibility
    
    Returns:
        Multiplier for household size (1.0 to 1.5x)
    """
    rng = np.random.RandomState(seed + 3000)  # Offset seed for independence
    
    # More common in south/central urban areas and some inland areas
    is_south = lat < 32.75
    
    # Calculate distance from center
    lat_diff = lat - CITY_CENTER_LAT
    lon_diff = lon - CITY_CENTER_LON
    distance_from_center = np.sqrt(lat_diff**2 + lon_diff**2)
    is_urban = distance_from_center < 0.10
    
    # Multi-generational probability
    if is_south and is_urban:  # South urban areas
        multigenerational_prob = 0.25
    elif is_urban:  # Other urban areas
        multigenerational_prob = 0.15
    else:  # Suburban areas
        multigenerational_prob = 0.10
    
    # Determine if multi-generational
    is_multigenerational = rng.random() < multigenerational_prob
    
    if is_multigenerational:
        # Increase usage by 20-50%
        size_factor = rng.uniform(1.20, 1.50)
        return size_factor
    else:
        return 1.0


# ═════════════════════════════════════════════════════════════════════════════
# MAIN PROCESSING FUNCTION
# ═════════════════════════════════════════════════════════════════════════════

def apply_all_variability_factors(df, lat, lon):
    """
    Applies all 9 variability factors to transform regional average
    into household-specific consumption.
    
    This function is the core of the model, combining:
    1. Geographic factors (lat/lon/elevation) - SCALAR
    2. Household characteristics - SCALAR
    3. Neighborhood factors - SCALAR
    4. Technology adoption (solar/EV) - TIME-DEPENDENT ARRAYS
    5. Demographic factors - SCALAR
    
    Args:
        df: DataFrame with avg_household_kw column
        lat: Target latitude
        lon: Target longitude
    
    Returns:
        DataFrame with new household_kw column
    """
    print(f"[2/5] Applying variability factors for location ({lat}, {lon})...")
    
    # Generate deterministic seed for this location
    seed = generate_location_seed(lat, lon)
    
    # ─── Calculate SCALAR multiplicative factors ────────────────────────────
    
    print("  • Factor 1: Longitude (coastal-inland climate)")
    lon_factor = calculate_longitude_factor(lon)
    
    print("  • Factor 2: Latitude (north-south microclimate)")
    lat_factor = calculate_latitude_factor(lat)
    
    print("  • Factor 3: Elevation proxy")
    elevation_factor = calculate_elevation_factor(lat, lon)
    
    print("  • Factor 4: Household characteristics")
    household_factor = calculate_household_characteristics(seed)
    
    print("  • Factor 5: Neighborhood density")
    density_factor = calculate_density_factor(lat, lon)
    
    print("  • Factor 6: Economic/home age")
    economic_factor = calculate_economic_age_factor(lat, lon)
    
    print("  • Factor 9: Multi-generational home")
    multigenerational_factor = calculate_multigenerational_factor(lat, lon, seed)
    
    # ─── Calculate TIME-DEPENDENT ARRAY factors ─────────────────────────────
    
    print("  • Factor 7: Solar adoption (Daylight Curve)")
    solar_multiplier_array = apply_solar_profile(df, lat, lon, seed)
    
    print("  • Factor 8: EV charging (Nighttime Schedule)")
    ev_load_array = apply_ev_charging(df, lat, lon, seed)
    
    # ─── Apply all factors ───────────────────────────────────────────────────
    
    # Step 1: Combine all SCALAR multipliers (Factors 1-6, 9)
    base_scalar_multiplier = (
        lon_factor *
        lat_factor *
        elevation_factor *
        household_factor *
        density_factor *
        economic_factor *
        multigenerational_factor
    )
    
    print(f"  • Combined scalar multiplier: {base_scalar_multiplier:.3f}")
    
    # Step 2: Apply scalar multiplier to baseline
    df['household_kw'] = df['avg_household_kw'] * base_scalar_multiplier
    
    # Step 3: Apply solar (TIME-DEPENDENT array multiplication)
    # Solar array is 1.0 at night, <1.0 during day
    df['household_kw'] = df['household_kw'] * solar_multiplier_array
    
    # Step 4: Add EV charging (TIME-DEPENDENT array addition)
    # EV load is 0 kW most hours, 3-7 kW during charging window
    df['household_kw'] = df['household_kw'] + ev_load_array
    
    # Check if solar or EV arrays are not all 1.0 or 0.0 (meaning they're active)
    has_solar_active = not np.allclose(solar_multiplier_array, 1.0)
    has_ev_active = not np.allclose(ev_load_array, 0.0)
    
    if has_solar_active:
        avg_solar_reduction = (1.0 - solar_multiplier_array.mean()) * 100
        print(f"  • Solar: Average reduction of {avg_solar_reduction:.1f}% across all hours")
    
    if has_ev_active:
        avg_ev_addition = ev_load_array.mean()
        print(f"  • EV: Average addition of {avg_ev_addition:.2f} kW across all hours")
    
    # Ensure no negative values (shouldn't happen, but safety check)
    df['household_kw'] = df['household_kw'].clip(lower=0)
    
    # ─── Add small hourly noise for realism ──────────────────────────────────
    
    print("  • Adding hourly noise for realism...")
    rng = np.random.RandomState(seed)
    hourly_noise = rng.normal(1.0, 0.03, size=len(df))  # ±3% noise
    df['household_kw'] = df['household_kw'] * hourly_noise
    
    return df


def create_hourly_output(df):
    """
    Creates final hourly output with proper formatting.
    
    Args:
        df: DataFrame with datetime_local and household_kw
    
    Returns:
        Cleaned DataFrame ready for export
    """
    print("[3/5] Formatting hourly output...")
    
    # Select and rename columns
    output_df = df[['datetime_local', 'household_kw']].copy()
    
    # Round kW values to 3 decimal places
    output_df['household_kw'] = output_df['household_kw'].round(3)
    
    # Remove timezone info for cleaner CSV output
    output_df['datetime_local'] = output_df['datetime_local'].dt.tz_localize(None)
    
    return output_df


def generate_summary_stats(df):
    """
    Generates and displays summary statistics for the household data.
    
    Args:
        df: DataFrame with household_kw column
    """
    print("[4/5] Generating summary statistics...")
    
    stats = {
        'Average hourly usage (kW)': df['household_kw'].mean(),
        'Peak hourly usage (kW)': df['household_kw'].max(),
        'Minimum hourly usage (kW)': df['household_kw'].min(),
        'Daily average usage (kWh)': df['household_kw'].sum() / (len(df) / 24),
        'Total hours of data': len(df),
        'Total days of data': len(df) / 24
    }
    
    print("\n" + "="*60)
    print("HOUSEHOLD USAGE SUMMARY")
    print("="*60)
    for key, value in stats.items():
        print(f"{key:.<50} {value:.2f}")
    print("="*60 + "\n")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═════════════════════════════════════════════════════════════════════════════

def main():
    """
    Main execution function that orchestrates the entire process.
    """
    print("\n" + "="*60)
    print("HOUSEHOLD ELECTRICITY USAGE GENERATOR")
    print("="*60)
    print(f"Target Location: ({TARGET_LAT}, {TARGET_LON})")
    print("="*60 + "\n")
    
    # 1. Load regional data and convert to household baseline
    hourly_df = load_regional_data(INPUT_FILENAME)
    
    # 2. Apply all 9 variability factors
    hourly_df = apply_all_variability_factors(hourly_df, TARGET_LAT, TARGET_LON)
    
    # 3. Format output
    output_df = create_hourly_output(hourly_df)
    
    # 4. Generate summary statistics
    generate_summary_stats(output_df)
    
    # 5. Save to CSV
    print("[5/5] Saving output file...")
    output_file = get_output_filename(TARGET_LAT, TARGET_LON)
    base_dir = r"C:\Users\shubh\Desktop\Hard disk\College(PG)\Academics at UCSD\Y1Q2\ECE 285 - Spec Topic - Signal & Image Robotics - Smartgrids\Project"
    output_df.to_csv(os.path.join(base_dir, output_file), index=False)

    
    print("\n✅ SUCCESS!")
    print(f"Generated household data saved to: {output_file}")
    print("\nFirst 10 rows:")
    print(output_df.head(10).to_string(index=False))
    print("\nLast 10 rows:")
    print(output_df.tail(10).to_string(index=False))
    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    main()