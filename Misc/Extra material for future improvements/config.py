"""
Configuration File for Solar Modeling Framework
═══════════════════════════════════════════════

This file contains all adjustable parameters for the simulation.
Modify these values to customize the analysis without editing core code.

Usage:
    from config import CONFIG
    
    system_losses = CONFIG['SYSTEM']['total_losses']
"""

# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM PARAMETERS
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM = {
    # Inverter
    "inverter_efficiency": 0.96,  # Modern string inverter (96%)
    "dc_ac_ratio": 1.20,          # DC oversizing factor (1.2x = 120% DC/AC)
    
    # System Losses (PVWatts defaults)
    "soiling_loss": 0.02,         # Dust, pollen (2%)
    "shading_loss": 0.03,         # Trees, structures (3%)
    "mismatch_loss": 0.02,        # Module variation (2%)
    "wiring_loss": 0.02,          # Resistive losses (2%)
    "connection_loss": 0.005,     # Plug/junction (0.5%)
    "age_loss": 0.015,            # LID + first-year (1.5%)
    "availability_loss": 0.01,    # Downtime (1%)
    
    # Physical constraints
    "roof_tilt_default": 20.0,    # degrees (San Diego optimal)
    "roof_azimuth_default": 180.0, # degrees (South = 180)
    "roof_area_max": 200.0,       # m² (typical residential)
}

# ═══════════════════════════════════════════════════════════════════════════════
# ECONOMIC PARAMETERS
# ═══════════════════════════════════════════════════════════════════════════════

ECONOMICS = {
    # Installation costs (2025 estimates)
    "installation_fixed": 4000.0,         # USD (base labor + permits)
    "installation_per_watt": 2.50,        # USD/W (scalable BOS + labor)
    
    # Incentives (current as of 2025)
    "federal_itc": 0.30,                  # 30% ITC through 2032
    "ca_sgip_per_kwh": 200.0,             # California SGIP ($/kWh for batteries)
    "ca_nem3_avg_export": 0.075,          # NEM 3.0 average export rate ($/kWh)
    
    # Ongoing costs
    "annual_maintenance": 150.0,          # USD/year
    "inverter_replacement_year": 15,      # Typical lifespan
    "inverter_replacement_cost": 2500.0,  # USD
    
    # Financial projections
    "rate_escalation": 0.045,             # 4.5% annual utility rate increase
    "discount_rate": 0.05,                # 5% real discount rate for NPV
    
    # Insurance and tax
    "insurance_increase": 0.0015,         # 0.15% of system value per year
    "property_tax_exempt": True,          # CA exempts solar from property tax
}

# ═══════════════════════════════════════════════════════════════════════════════
# REGIONAL CONSTANTS (SAN DIEGO)
# ═══════════════════════════════════════════════════════════════════════════════

REGIONAL = {
    # Data paths
    "regional_load_path": "San_Diego_Load_EIA_Fixed.csv",
    "tou_tariff_dir": ".",  # Directory containing tou_*.csv files
    
    # Demographics
    "total_customers": 1_040_149,  # SDGE residential meters
    
    # Geographic references
    "coastal_lon_ref": -117.25,
    "city_center_lat": 32.7157,
    "city_center_lon": -117.1611,
    
    # Validation bounds
    "lat_min": 32.53,
    "lat_max": 33.22,
    "lon_min": -117.26,
    "lon_max": -116.90,
}

# ═══════════════════════════════════════════════════════════════════════════════
# WEATHER API
# ═══════════════════════════════════════════════════════════════════════════════

WEATHER = {
    "api_base_url": "https://archive-api.open-meteo.com/v1/archive",
    "api_timeout": 60,  # seconds
    "retry_attempts": 3,
}

# ═══════════════════════════════════════════════════════════════════════════════
# BATTERY DISPATCH
# ═══════════════════════════════════════════════════════════════════════════════

BATTERY = {
    # Discharge trigger ($/kWh)
    "on_peak_threshold": 0.40,  # Discharge when rate >= $0.40/kWh
    
    # Never charge from grid in NEM 3.0 economics
    "charge_from_grid": False,
    
    # Depth of discharge safety margin
    "dod_safety_margin": 0.05,  # Keep 5% buffer beyond rated DoD
}

# ═══════════════════════════════════════════════════════════════════════════════
# SIMULATION SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

SIMULATION = {
    # Logging
    "log_level": "INFO",  # DEBUG, INFO, WARNING, ERROR
    "log_file": "solar_model.log",
    
    # Performance
    "cache_weather_data": True,
    "cache_load_data": True,
    
    # Export
    "enable_export": True,
    "export_dir": "./simulation_results",
    "export_formats": ["json", "csv"],
}

# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION RANGES
# ═══════════════════════════════════════════════════════════════════════════════

VALIDATION = {
    # Annual consumption (kWh)
    "annual_consumption_min": 3000,
    "annual_consumption_max": 30000,
    
    # Peak load (kW)
    "peak_load_min": 1.0,
    "peak_load_max": 15.0,
    
    # Solar capacity factor (%)
    "capacity_factor_min": 0.15,
    "capacity_factor_max": 0.25,
    
    # Financial metrics
    "npv_reasonable_max": 100000,  # USD
    "irr_reasonable_max": 0.50,    # 50%
    "payback_reasonable_max": 30,  # years
}

# ═══════════════════════════════════════════════════════════════════════════════
# SENSITIVITY ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

SENSITIVITY = {
    # Parameters to vary
    "params_to_test": [
        "rate_escalation",
        "discount_rate",
        "panel_degradation",
        "system_losses",
        "federal_itc",
    ],
    
    # Variation ranges (multiplicative factors)
    "variation_low": 0.85,   # -15%
    "variation_high": 1.15,  # +15%
    
    # Number of samples for Monte Carlo
    "monte_carlo_samples": 1000,
}

# ═══════════════════════════════════════════════════════════════════════════════
# PANEL DATABASE (Can be extended)
# ═══════════════════════════════════════════════════════════════════════════════

PANEL_DEFAULTS = {
    "wattage": 0.400,          # kW
    "efficiency": 0.20,        # 20%
    "cost": 300,               # USD
    "degradation_rate": 0.005, # 0.5%/year
    "temp_coefficient": -0.0035, # per °C
    "area": 1.7,               # m²
    "warranty_years": 25,
}

# ═══════════════════════════════════════════════════════════════════════════════
# BATTERY DATABASE (Can be extended)
# ═══════════════════════════════════════════════════════════════════════════════

BATTERY_DEFAULTS = {
    "capacity_kwh": 10.0,
    "cost": 10000,
    "round_trip_efficiency": 0.90,
    "depth_of_discharge": 0.90,
    "max_charge_rate": 5.0,     # kW
    "max_discharge_rate": 5.0,  # kW
    "cycle_life": 6000,
    "warranty_years": 10,
}

# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

# Combine all configs into single dictionary for easy import
CONFIG = {
    "SYSTEM": SYSTEM,
    "ECONOMICS": ECONOMICS,
    "REGIONAL": REGIONAL,
    "WEATHER": WEATHER,
    "BATTERY": BATTERY,
    "SIMULATION": SIMULATION,
    "VALIDATION": VALIDATION,
    "SENSITIVITY": SENSITIVITY,
    "PANEL_DEFAULTS": PANEL_DEFAULTS,
    "BATTERY_DEFAULTS": BATTERY_DEFAULTS,
}

# ═══════════════════════════════════════════════════════════════════════════════
# NOTES FOR USERS
# ═══════════════════════════════════════════════════════════════════════════════

"""
COMMON CUSTOMIZATIONS:

1. Adjust rate escalation (more conservative or aggressive):
   ECONOMICS["rate_escalation"] = 0.035  # 3.5% instead of 4.5%

2. Change discount rate (different investment perspective):
   ECONOMICS["discount_rate"] = 0.08  # 8% for higher opportunity cost

3. Update installation costs (market changes):
   ECONOMICS["installation_per_watt"] = 2.25  # Falling costs

4. Modify system losses (better installation quality):
   SYSTEM["soiling_loss"] = 0.01  # More frequent cleaning

5. Change battery dispatch trigger (optimize for your rates):
   BATTERY["on_peak_threshold"] = 0.35  # Lower threshold

6. Enable more logging (debugging):
   SIMULATION["log_level"] = "DEBUG"

7. Add custom panel or battery:
   - Edit SOLAR_PANELS or BATTERY_SYSTEMS in Back_end_calc_enhanced.py
   - Or create new entries in these defaults
"""
