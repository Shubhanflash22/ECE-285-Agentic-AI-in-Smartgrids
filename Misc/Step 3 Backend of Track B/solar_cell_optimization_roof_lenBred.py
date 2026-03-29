"""
===============================================
AI-driven residential photovoltaic and storage system engineering design
for San Diego / SDG&E customers.

Mathematical foundation
-----------------------
Cell:   I_c = P_c / V_c
Panel:  V_panel = n_s * V_c,   I_panel = n_p * I_c,   P_panel = n_s*n_p*P_c
Array:  P_array = N_s*N_p*n_s*n_p*P_c * (G(t)/G_ref) * PR

Financial model (10-year)
--------------------------
Traditional: Cost(y) = Cost(y-1) * (1 + inflation_rate)
NPV = sum_t[(Revenue_t - OM_t)/(1+r)^t] - Capital

Optimizer (scipy / HiGHS MILP — full 8760-h)
---------------------------------------------
Jointly optimises:
  - Panels  (integer decision variable)
  - BatCap  (continuous kWh)
  - Import(t), Export(t), Charge(t), Discharge(t), SOC(t)  for every hour
All in one solve — NOT simulation-after-sizing.

Variable layout  (total 5T + 3)
  idx 0        : Panels
  idx 1        : BatCap
  idx 2..T+1   : Import(t)
  idx T+2..2T+1: Export(t)
  idx 2T+2..3T+1: Charge(t)
  idx 3T+2..4T+1: Discharge(t)
  idx 4T+2..5T+2: SOC(t)   [T+1 values]

Script sections
---------------
1.  Imports
2.  File paths, catalogs, physical/financial constants
3.  User profile
4.  Helper functions
    4A  _load_household_profile_from_eia()   EIA 5-yr averaged load
    4B  _build_annual_load_profile()         Synthetic fallback
    4C  _fetch_irradiance()                  Open-Meteo API
    4D  _build_hourly_tariffs()              SDG&E TOU CSVs
    4E  _irradiance_shape_factor()           Sine daylight model
    4F  _build_hourly_pv_output()            8760-h AC generation
    4G  _select_panel() / _select_battery()  Catalog lookups
    4H  _run_dispatch_simulation()           Rule-based sim (for economics)
    4I  _compute_economics()                 10-year NPV model
5.  Core MILP optimizer    optimize_energy_system_milp()
6.  Master orchestrator    recommend_residential_energy_system()
7.  Main entry point
"""


# =============================================================================
# SECTION 1 -- IMPORTS
# =============================================================================
# pip install pandas numpy requests scipy
# (pulp is no longer required)

import hashlib
import math
import os
import time
import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import csc_matrix

warnings.filterwarnings("ignore")


# =============================================================================
# SECTION 2 -- FILE PATHS, CATALOGS AND PHYSICAL CONSTANTS
# =============================================================================

# -- 2A  File paths -----------------------------------------------------------
# TOU CSV files and EIA load file must sit in the same folder as this script.
# Edit the paths below if you keep them elsewhere.
_HERE = os.path.dirname(os.path.abspath(__file__))

TOU_DR_PATH  = r"C:\Users\shubh\Desktop\Hard disk\College(PG)\Academics at UCSD\Y1Q2\ECE 285 - Spec Topic - Signal & Image Robotics - Smartgrids\Project\Step 1 Preprocess data\Tariff Data\TOU-DR\tou_dr_daily_2021_2025.csv"
TOU_DR1_PATH = r"C:\Users\shubh\Desktop\Hard disk\College(PG)\Academics at UCSD\Y1Q2\ECE 285 - Spec Topic - Signal & Image Robotics - Smartgrids\Project\Step 1 Preprocess data\Tariff Data\TOU-DR1\tou_dr1_daily_2021_2025.csv"
TOU_DR2_PATH = r"C:\Users\shubh\Desktop\Hard disk\College(PG)\Academics at UCSD\Y1Q2\ECE 285 - Spec Topic - Signal & Image Robotics - Smartgrids\Project\Step 1 Preprocess data\Tariff Data\TOU-DR2\tou_dr2_daily_2021_2025.csv"
EIA_LOAD_PATH = r"C:\Users\shubh\Desktop\Hard disk\College(PG)\Academics at UCSD\Y1Q2\ECE 285 - Spec Topic - Signal & Image Robotics - Smartgrids\Project\Step 1 Preprocess data\San_Diego_Load_EIA_Fixed.csv"

# SDG&E total meter count — used to downscale grid MW → per-household kW.
# Includes commercial + industrial, so EIA-derived kWh will be too high
# for a single home unless you supply annual_consumption_kwh as an override.
SDGE_TOTAL_CUSTOMERS = 1_040_149

# Geographic reference points
COASTAL_LON_REF = -117.25    # coastal/inland split longitude
CITY_CENTER_LAT =  32.7157   # downtown SD
CITY_CENTER_LON = -117.1611

DEFAULT_RATE_PLAN = "TOU_DR"

# -- 2B  Solar panel catalog (EnergySage 2025 San Diego) ----------------------
# cost_per_wp_usd : fully installed $/Wp  (labour + inverter already included)
# degradation_rate: annual power loss fraction
SOLAR_PANEL_CATALOG = [
    {"manufacturer": "REC Group",      "model": "Alpha Pure",
     "efficiency_percent": 21.9, "cost_per_wp_usd": 0.83, "temp_coeff_pct_per_C": -0.26,
     "voc_v": 49.1, "isc_a": 10.41, "vmp_v": 41.8, "imp_a": 9.69,
     "panel_power_w": 405, "panel_area_m2": 1.85,
     "cells_in_series": 66, "cells_in_parallel": 2, "degradation_rate": 0.0025},
    
    {"manufacturer": "JA Solar",       "model": "DeepBlue 3.0",
     "efficiency_percent": 20.2, "cost_per_wp_usd": 0.45, "temp_coeff_pct_per_C": -0.35,
     "voc_v": 36.98, "isc_a": 13.7, "vmp_v": 30.84, "imp_a": 12.81,
     "panel_power_w": 395, "panel_area_m2": 1.95,
     "cells_in_series": 54, "cells_in_parallel": 2, "degradation_rate": 0.0061},
    
    {"manufacturer": "Trina Solar",    "model": "Vertex S",
     "efficiency_percent": 20.8, "cost_per_wp_usd": 0.32, "temp_coeff_pct_per_C": -0.34,
     "voc_v": 41.2, "isc_a": 12.28, "vmp_v": 34.2, "imp_a": 11.7,
     "panel_power_w": 400, "panel_area_m2": 1.92,
     "cells_in_series": 60, "cells_in_parallel": 2, "degradation_rate": 0.0055},
    
    {"manufacturer": "Canadian Solar", "model": "TOPHiKu7",
     "efficiency_percent": 23.2, "cost_per_wp_usd": 0.16, "temp_coeff_pct_per_C": -0.29,
     "voc_v": 48.7, "isc_a": 18.69, "vmp_v": 40.8, "imp_a": 17.67,
     "panel_power_w": 720, "panel_area_m2": 3.11,
     "cells_in_series": 66, "cells_in_parallel": 2, "degradation_rate": 0.004},
    
    {"manufacturer": "Silfab Solar",   "model": "Prime",
     "efficiency_percent": 22.6, "cost_per_wp_usd": 0.53, "temp_coeff_pct_per_C": -0.36,
     "voc_v": 38.97, "isc_a": 14.22, "vmp_v": 33.41, "imp_a": 13.17,
     "panel_power_w": 440, "panel_area_m2": 1.94,
     "cells_in_series": 54, "cells_in_parallel": 2, "degradation_rate": 0.005},
    
    {"manufacturer": "Jinko Solar",    "model": "Tiger Neo",
     "efficiency_percent": 22.53, "cost_per_wp_usd": 0.45, "temp_coeff_pct_per_C": -0.29,
     "voc_v": 39.38, "isc_a": 13.86, "vmp_v": 32.81, "imp_a": 13.41,
     "panel_power_w": 440, "panel_area_m2": 1.95,
     "cells_in_series": 54, "cells_in_parallel": 2, "degradation_rate": 0.004},
    
    {"manufacturer": "LONGi Solar",    "model": "Hi-MO 6",
     "efficiency_percent": 22.3, "cost_per_wp_usd": 0.3, "temp_coeff_pct_per_C": -0.29,
     "voc_v": 39.33, "isc_a": 14.22, "vmp_v": 33.04, "imp_a": 13.17,
     "panel_power_w": 435, "panel_area_m2": 1.95,
     "cells_in_series": 54, "cells_in_parallel": 2, "degradation_rate": 0.004},
    
    {"manufacturer": "Maxeon Solar",   "model": "Maxeon 7",
     "efficiency_percent": 24.1, "cost_per_wp_usd": 3.5, "temp_coeff_pct_per_C": -0.27,
     "voc_v": 83.0, "isc_a": 6.6, "vmp_v": 71.4, "imp_a": 6.23,
     "panel_power_w": 445, "panel_area_m2": 1.85,
     "cells_in_series": 112, "cells_in_parallel": 1, "degradation_rate": 0.0025},
    
    {"manufacturer": "Aiko Solar",     "model": "Neostar 2P",
     "efficiency_percent": 24.3, "cost_per_wp_usd": 0.55, "temp_coeff_pct_per_C": -0.26,
     "voc_v": 41.36, "isc_a": 14.41, "vmp_v": 34.92, "imp_a": 13.9,
     "panel_power_w": 485, "panel_area_m2": 1.99,
     "cells_in_series": 54, "cells_in_parallel": 2, "degradation_rate": 0.0035},
]


# -- 2C  Battery catalog -------------------------------------------------------
# cost_usd = fully installed price per unit.
# Units are stacked automatically when more kWh capacity is required.
BATTERY_CATALOG = [
    {"manufacturer": "Tesla",     "model": "Powerwall 3",
     "usable_capacity_kwh": 13.5, "nominal_voltage_v": "52 - 92 (DC)",
     "max_charge_power_kw": 5.0,  "max_discharge_power_kw": 11.5,
     "round_trip_efficiency_pct": 97.5, "cycle_life": None,
     "cost_usd": 15400, "annual_degradation_rate": 0.02},
    
    {"manufacturer": "Enphase",   "model": "IQ Battery 5P",
     "usable_capacity_kwh": 5.0,  "nominal_voltage_v": "48.0 (Internal)",
     "max_charge_power_kw": 3.84, "max_discharge_power_kw": 3.84,
     "round_trip_efficiency_pct": 96.0, "cycle_life": 6000,
     "cost_usd": 8500, "annual_degradation_rate": 0.015},
    
    {"manufacturer": "Generac",   "model": "PWRcell M6",
     "usable_capacity_kwh": 18.0, "nominal_voltage_v": "360 - 420",
     "max_charge_power_kw": 10.5, "max_discharge_power_kw": 10.5,
     "round_trip_efficiency_pct": 96.5, "cycle_life": None,
     "cost_usd": 11500, "annual_degradation_rate": 0.02},
    
    {"manufacturer": "SolarEdge", "model": "Home Battery",
     "usable_capacity_kwh": 4.6,  "nominal_voltage_v": "44.8 - 56.5",
     "max_charge_power_kw": 2.825,"max_discharge_power_kw": 4.096,
     "round_trip_efficiency_pct": 94.5, "cycle_life": None,
     "cost_usd": 12500, "annual_degradation_rate": 0.03},
    
    {"manufacturer": "Panasonic", "model": "EverVolt H",
     "usable_capacity_kwh": 13.5, "nominal_voltage_v": "153.6",
     "max_charge_power_kw": 8.3,  "max_discharge_power_kw": 8.3,
     "round_trip_efficiency_pct": 94.0, "cycle_life": 6000,
     "cost_usd": 17500, "annual_degradation_rate": 0.025},
]


# -- 2D  Physical and financial constants -------------------------------------
G_REF_W_M2            = 1000.0   # STC reference irradiance (W/m²)
PR_PERFORMANCE_RATIO   = 0.80    # soiling + wiring + mismatch losses

INSTALLATION_COST_RATE   = 0.10   # labour = 10% of hardware
FEDERAL_ITC_RATE         = 0.30   # 30% Federal ITC (2025)
UTILITY_INFLATION_RATE   = 0.06   # SDG&E annual escalation
DISCOUNT_RATE            = 0.07   # NPV discount rate
O_AND_M_COST_PER_W_YR    = 0.005  # cleaning + insurance ($/W/yr)
NEM_EXPORT_CREDIT        = 0.10   # NEM 3.0 avoided-cost credit ($/kWh)
INVERTER_REPLACEMENT_YR  = 10
INVERTER_REPLACEMENT_USD = 2000
ANALYSIS_YEARS           = 10
SDGE_DAILY_FIXED_FEE     = 0.345  # SDG&E daily minimum charge ($/day)

# Annuity factor: converts lump-sum capital → equivalent annual payment
# r*(1+r)^n / ((1+r)^n - 1)  at r=7%, n=10
_r = DISCOUNT_RATE; _n = ANALYSIS_YEARS
ANNUITY_FACTOR = _r * (1 + _r)**_n / ((1 + _r)**_n - 1)   # ≈ 0.1424

# Battery $/kWh proxy used inside the MILP budget constraint.
# Cheapest catalog unit on a $/kWh basis: Powerwall 3 = $11,500 / 13.5 kWh
BAT_COST_PER_KWH_PROXY = 852.0

# -- 2E  MILP battery physics constants ---------------------------------------
MILP_ETA_C         = 0.975   # charge round-trip efficiency
MILP_ETA_D         = 0.975   # discharge round-trip efficiency
MILP_C_RATE        = 0.50    # max charge/discharge = 50% of capacity per hour
MILP_SOC_MIN_FRAC  = 0.10    # depth-of-discharge floor (10%)
MILP_SOC_INIT_FRAC = 0.50    # initial SOC = 50% of capacity

# -- 2F  EV charging assumptions ----------------------------------------------
EV_CHARGE_START_HOUR = 22    # 10 PM
EV_CHARGE_END_HOUR   = 6     # 6 AM
EV_CHARGER_POWER_KW  = 7.2   # Level 2 EVSE
EV_DAILY_ENERGY_KWH  = 14.0  # kWh per EV per day

# -- 2G  Open-Meteo API -------------------------------------------------------
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"


# =============================================================================
# SECTION 3 -- USER PROFILE
# =============================================================================
"""
Edit USER_PROFILE to model your household.

annual_consumption_kwh
    ALWAYS supply this from your SDG&E bill.  The EIA data covers all meter
    types (commercial + industrial), so the raw downscaled kWh will be
    ~17,000+/yr — far too high for a single-family home.
    Setting this to e.g. 7500.0 preserves the real temporal SHAPE of the
    EIA load (when people use power) while rescaling the magnitude to match
    your actual usage.  Set to None only if you want to use the raw EIA value.
"""

USER_PROFILE = {
    # Location — drives all 9 EIA variability factors
    "latitude":               32.7157,
    "longitude":             -117.1611,

    # Your actual annual kWh from your SDG&E bill (strongly recommended).
    # Set to None to auto-derive from raw EIA data (will be too high — see note above).
    "annual_consumption_kwh": 18000.0,

    # Financial + physical constraints
    "budget_usd":             50000.0,
    "roof_area_m2":           15.0,
    "roof_length_m":          3.0,  
    "roof_width_m":           5.0,   

    # SDG&E rate plan
    "rate_plan":              "TOU_DR",   # "TOU_DR" | "TOU_DR1" | "TOU_DR2"

    # Panel preference (None = auto best efficiency/cost ratio)
    "panel_brand":            None,

    # Optional — only used if EIA file is missing and synthetic fallback is used
    "num_evs":                0,
    "num_people":             3,
    "num_daytime_occupants":  1,
}


# =============================================================================
# SECTION 4 -- HELPER / INTERNAL FUNCTIONS
# =============================================================================

# -- 4A  EIA load loader -------------------------------------------------------

def _load_household_profile_from_eia(latitude: float, longitude: float,
                                      annual_kwh_override: float | None = None,
                                      num_evs: int = 0,
                                      num_people: int = 3,
                                      num_daytime_occupants: int = 1
                                      ) -> tuple:
    """
    Build a real 8760-h household load profile (kW) from EIA regional data.

    Method
    ------
    1. Load San_Diego_Load_EIA_Fixed.csv (hourly MW UTC).
       Localise to America/Los_Angeles.
       Downscale: avg_kw = MW_Load * 1000 / SDGE_TOTAL_CUSTOMERS.

    2. Average across ALL full years (>= 8000 rows) by hour-of-year position.
       WHY: No single year reaches exactly 8760 rows due to DST transitions
       (the old code's ">= 8760" check always failed, falling back to the
       partial 2026 year with only 579 hours, then tiling it 15× — which
       inflated the load to ~24,000 kWh/yr).
       Averaging 5 years gives better coverage (8644/8760 slots from all 5
       years) and smooths out single-year weather anomalies.

    3. Apply 9 location-based variability factors (from household_extraction_per_house.py):
         F1 Longitude  coastal 0.85x → inland 1.25x
         F2 Latitude   south 1.10x, north 0.90x
         F3 Elevation  inland/north proxy 1.0–1.15x
         F4 Household  size × efficiency 0.7–1.3x
         F5 Density    urban 0.7x → suburban 1.3x
         F6 Economic   home age + income 0.95–1.25x
         F7 Solar      daylight sine reduction (probabilistic)
         F8 EV         nighttime load addition (probabilistic)
         F9 Multi-gen  extended family 1.2–1.5x (probabilistic)

    4. Add ±3% hourly noise (deterministic from lat/lon seed).

    5. Rescale to annual_kwh_override if supplied — this is the recommended
       path.  Supply your real SDG&E annual kWh so the shape is real and the
       magnitude is correct.

    Returns
    -------
    (hourly_kw: list[float], annual_kwh: float)

    Raises
    ------
    FileNotFoundError if EIA_LOAD_PATH does not exist.
    """
    if not os.path.exists(EIA_LOAD_PATH):
        raise FileNotFoundError(
            f"EIA file not found at {EIA_LOAD_PATH}\n"
            "Place San_Diego_Load_EIA_Fixed.csv in the same folder as this script,\n"
            "or set annual_consumption_kwh in USER_PROFILE to use the synthetic fallback."
        )

    # ── Step 1: Load, localise, downscale ─────────────────────────────────────
    df = pd.read_csv(EIA_LOAD_PATH)
    df["dt_utc"]   = pd.to_datetime(df["Timestamp_UTC"])
    df["dt_local"] = df["dt_utc"].dt.tz_localize("UTC").dt.tz_convert("America/Los_Angeles")
    df["kw"]       = df["MW_Load"] * 1000.0 / SDGE_TOTAL_CUSTOMERS
    df["year"]     = df["dt_local"].dt.year
    df["doy"]      = df["dt_local"].dt.dayofyear
    df["hour"]     = df["dt_local"].dt.hour
    df["hoy"]      = ((df["doy"] - 1) * 24 + df["hour"]).clip(0, 8759)

    # ── Step 2: Average across full years by HOY position ─────────────────────
    full_years = df["year"].value_counts()
    full_years = full_years[full_years >= 8000].index.tolist()
    df_full    = df[df["year"].isin(full_years)]
    avg_hoy    = (df_full.groupby("hoy")["kw"]
                         .mean()
                         .reindex(range(8760))
                         .interpolate(method="linear")
                         .ffill().bfill())
    profile = avg_hoy.values.copy()   # shape (8760,)

    # ── Step 3: 9 variability factors ─────────────────────────────────────────
    loc_seed  = int(hashlib.sha256(f"{latitude}_{longitude}".encode()).hexdigest(), 16) % (2**32)
    rng_hh    = np.random.RandomState(loc_seed)
    rng_sol   = np.random.RandomState(loc_seed + 1000)
    rng_ev    = np.random.RandomState(loc_seed + 2000)
    rng_mg    = np.random.RandomState(loc_seed + 3000)

    # F1: Longitude (coastal–inland)
    dc = longitude - COASTAL_LON_REF
    if   dc >= 0.15:            f1 = 1.25
    elif dc >= 0.10:            f1 = 1.05 + (dc - 0.10) * 4.0
    elif dc >= 0:               f1 = 0.95 + dc * 1.0
    elif dc >= -0.05:           f1 = 0.90 + (dc + 0.05) * 1.0
    else:                       f1 = 0.85

    # F2: Latitude (north–south)
    if   latitude < 32.60:     f2 = 1.10
    elif latitude < 32.70:     f2 = 1.05
    elif latitude < 32.85:     f2 = 1.00
    elif latitude < 32.95:     f2 = 0.95
    else:                      f2 = 0.90

    # F3: Elevation proxy
    f3 = 1.0 + (max(0, longitude - COASTAL_LON_REF) + max(0, latitude - 32.70) * 2.0) * 0.15

    # F4: Household size × efficiency
    f4 = 0.70 + 0.10 * min(num_people, 6)

    # F5: Neighbourhood density
    dist_c = math.sqrt((latitude - CITY_CENTER_LAT)**2 + (longitude - CITY_CENTER_LON)**2)
    if   dist_c < 0.03:        f5 = 0.7
    elif dist_c < 0.08:        f5 = 0.9
    elif dist_c < 0.15:        f5 = 1.1
    else:                      f5 = 1.3

    # F6: Economic / home age
    is_coastal    = longitude    < -117.20
    is_north      = latitude     >  32.80
    is_urban_core = dist_c       <   0.05
    if   is_coastal and is_north: f6 = 1.15
    elif is_coastal:              f6 = 1.05
    elif is_urban_core:           f6 = 1.25
    elif longitude > -117.00:     f6 = 0.95
    else:                         f6 = 1.10

    # F9: Multi-generational (scalar, before time-array ops)
    is_south = latitude < 32.75
    is_urban = dist_c   < 0.10
    mg_prob  = 0.25 if (is_south and is_urban) else (0.15 if is_urban else 0.10)
    f9 = rng_mg.uniform(1.20, 1.50) if rng_mg.random() < mg_prob else 1.0

    profile *= f1 * f2 * f3 * f4 * f5 * f6 * f9

    # F7: Solar adoption (time-dependent daylight reduction)
    is_affluent = is_coastal and is_north
    sol_prob = (0.35 if is_affluent
                else 0.20 if (is_coastal or longitude > -117.00)
                else 0.05 if is_urban_core else 0.15)
    if rng_sol.random() < sol_prob:
        hrs       = np.arange(8760) % 24
        intensity = np.clip(np.sin((hrs - 6) * np.pi / 12), 0, 1)
        intensity[(hrs < 6) | (hrs > 18)] = 0
        max_red   = rng_sol.uniform(0.4, 0.7)
        profile  *= 1.0 - intensity * (1.0 - max_red)
        print(f"    [EIA] Solar adopted  (midday reduction {(1-max_red)*100:.0f}%)")

    # F8: EV charging (time-dependent nighttime load)
    if num_evs > 0:
        hrs = np.arange(8760) % 24
        # Assuming Level 2 charging (7.2 kW) starting at 10 PM
        start_h = 22
        # Calculate how many hours are needed to deliver 14 kWh per EV
        hours_needed = int(np.ceil((14.0 * num_evs) / 7.2))
        end_h = (start_h + hours_needed) % 24
        
        is_chg = ((hrs >= start_h) | (hrs < end_h)) if start_h >= end_h \
                 else ((hrs >= start_h) & (hrs < end_h))
                 
        profile += np.where(is_chg, 7.2 * num_evs, 0.0)
        print(f"    [EIA] Added {num_evs} EV(s) charging overnight.")

    # F10: Daytime Occupants (Work from Home / Stay at Home)
    if num_daytime_occupants > 0:
        hrs = np.arange(8760) % 24
        daytime_mask = (hrs >= 9) & (hrs < 17)
        occupancy_multiplier = 1.0 + (0.05 * num_daytime_occupants)
        profile = np.where(daytime_mask, profile * occupancy_multiplier, profile)
        print(f"    [EIA] Adjusted daytime load for {num_daytime_occupants} occupant(s).")

    # ±3% noise (deterministic)
    profile *= np.random.RandomState(loc_seed).normal(1.0, 0.03, size=8760)
    profile  = np.clip(profile, 0, None)

    # ── Step 5: Rescale to known annual total ---------------------------------
    prof_sum = float(profile.sum())
    if annual_kwh_override is not None and annual_kwh_override > 0 and prof_sum > 0:
        profile *= annual_kwh_override / prof_sum
        ann_kwh  = annual_kwh_override
        print(f"    [EIA] Rescaled to {ann_kwh:,.0f} kWh/yr (from USER_PROFILE override)")
    else:
        ann_kwh = round(prof_sum, 1)

    print(f"    [EIA] Full years averaged: {sorted(full_years)}")
    print(f"    [EIA] Annual total: {ann_kwh:,.0f} kWh  |  Avg power: {ann_kwh/8760:.3f} kW")

    return profile.tolist(), ann_kwh


# -- 4B  Synthetic load fallback ----------------------------------------------

def _estimate_ev_hourly_demand(num_evs: int) -> list:
    """24-element hourly EV demand (kW). Overnight Level-2 charging."""
    if num_evs == 0:
        return [0.0] * 24
    if EV_CHARGE_START_HOUR < EV_CHARGE_END_HOUR:
        ch = list(range(EV_CHARGE_START_HOUR, EV_CHARGE_END_HOUR))
    else:
        ch = list(range(EV_CHARGE_START_HOUR, 24)) + list(range(0, EV_CHARGE_END_HOUR))
    ch = ch[:int(np.ceil(EV_DAILY_ENERGY_KWH / EV_CHARGER_POWER_KW))]
    p  = [0.0] * 24
    for h in ch:
        p[h] = EV_CHARGER_POWER_KW * num_evs
    return p


def _build_annual_load_profile(annual_kwh: float, num_evs: int,
                                num_people: int, num_daytime_occupants: int) -> list:
    """Synthetic 8760-h household load profile anchored to annual_kwh."""
    shape = np.array([
        0.40, 0.35, 0.32, 0.30, 0.30, 0.35,
        0.50, 0.70, 0.85, 0.80, 0.75, 0.72,
        0.70, 0.68, 0.65, 0.65, 0.70, 0.90,
        1.00, 0.95, 0.85, 0.75, 0.65, 0.50,
    ])
    ev24   = np.array(_estimate_ev_hourly_demand(num_evs))
    ev_ann = ev24.sum() * 365
    y0     = datetime(2024, 1, 1)
    raw    = []
    for h in range(8760):
        dt = y0 + timedelta(hours=h)
        sm = 1.20 if 6 <= dt.month <= 10 else (0.95 if dt.month in (3, 4, 5, 11) else 1.00)
        om = 1.0 + 0.05 * num_daytime_occupants if 9 <= dt.hour < 17 else 1.0
        ps = 0.70 + 0.10 * min(num_people, 6)
        raw.append(shape[dt.hour] * sm * om * ps)
    arr   = np.array(raw)
    scale = max(annual_kwh - ev_ann, 0.0) / arr.sum() if arr.sum() > 0 else 1.0
    return [float(raw[h] * scale + ev24[h % 24]) for h in range(8760)]


# -- 4C  Irradiance -----------------------------------------------------------

def _irradiance_shape_factor(hour_of_day: int, day_of_year: int) -> float:
    """
    Fractional G(t)/G_ref via sine-wave daylight model.
    sunset varies seasonally: 18 + 2*sin(2π*(doy-80)/365).
    Returns 0 outside daylight hours.
    """
    sunrise = 6.0
    sunset  = 18.0 + 2.0 * np.sin(2.0 * np.pi * (day_of_year - 80) / 365.0)
    if hour_of_day < sunrise or hour_of_day >= sunset:
        return 0.0
    return max(0.0, np.sin(np.pi * (hour_of_day - sunrise) / (sunset - sunrise)))


def _fetch_irradiance(latitude: float, longitude: float) -> float:
    """
    Mean annual GHI (kWh/m²/yr) from Open-Meteo 5-year archive.
    API field: shortwave_radiation_sum (MJ/m²/day) → divide by 3.6 → kWh/m²/day → ×365.
    Falls back to SD average 2080 kWh/m²/yr on any failure.
    """
    try:
        end    = datetime.now() - timedelta(days=7)
        start  = end.replace(year=end.year - 5)
        params = {"latitude": latitude, "longitude": longitude,
                  "start_date": start.strftime("%Y-%m-%d"),
                  "end_date":   end.strftime("%Y-%m-%d"),
                  "daily": "shortwave_radiation_sum", "timezone": "auto"}
        r = requests.get(OPEN_METEO_URL, params=params, timeout=60)
        r.raise_for_status()
        vals = [v for v in r.json()["daily"]["shortwave_radiation_sum"] if v is not None]
        if not vals:
            raise ValueError("empty response")
        return round(np.mean(vals) / 3.6 * 365, 1)
    except Exception as e:
        print(f"  [WARNING] Irradiance API failed ({e}). Using SD default 2080 kWh/m²/yr.")
        return 2080.0


# -- 4D  Tariffs --------------------------------------------------------------

def _build_hourly_tariffs(rate_plan: str, year: int = 2024) -> list:
    """
    8760 hourly SDG&E TOU prices ($/kWh).

    Period mapping (all plans):
        On-Peak        16:00–21:00 every day
        Super-Off-Peak 00:00–06:00 + Mar/Apr 10:00–14:00
        Off-Peak       all other hours
    """
    if rate_plan in ("TOU_DR", "TOU_DR1"):
        path = TOU_DR_PATH if rate_plan == "TOU_DR" else TOU_DR1_PATH
        df   = pd.read_csv(path, parse_dates=["date"])
        lk   = df[df["date"].dt.year == year].set_index("date")[
               ["on_peak_$/kwh", "off_peak_$/kwh", "super_off_peak_$/kwh"]]
        use_daily = True
    elif rate_plan == "TOU_DR2":
        df        = pd.read_csv(TOU_DR2_PATH, parse_dates=["start_date", "end_date"])
        lk        = df[df["year"] == year].copy()
        use_daily = False
    else:
        raise ValueError(f"Unknown rate_plan '{rate_plan}'. Use TOU_DR, TOU_DR1, or TOU_DR2.")

    out = []
    y0  = datetime(year, 1, 1)
    for h in range(8760):
        dt    = y0 + timedelta(hours=h)
        hr, mo = dt.hour, dt.month
        on_p  = (16 <= hr < 21)
        sup_p = (hr < 6) or (mo in (3, 4) and 10 <= hr < 14)
        if use_daily:
            dk = pd.Timestamp(dt.date())
            if dk not in lk.index:
                dk = min(lk.index, key=lambda d: abs((d - dk).days))
            row = lk.loc[dk]
            out.append(float(row["on_peak_$/kwh"] if on_p else
                             (row["super_off_peak_$/kwh"] if sup_p else row["off_peak_$/kwh"])))
        else:
            is_sum = (6 <= mo <= 10)
            seg    = None
            ts     = pd.Timestamp(dt.date())
            for _, s in lk.iterrows():
                if s["start_date"] <= ts <= s["end_date"]:
                    seg = s; break
            if seg is None:
                out.append(0.38); continue
            col = ("summer_on_peak_$/kwh" if is_sum else "winter_on_peak_$/kwh") if on_p \
                  else ("summer_off_peak_$/kwh" if is_sum else "winter_off_peak_$/kwh")
            out.append(float(seg[col]))
    return out


# -- 4E  Irradiance shape + PV output ----------------------------------------

def _build_hourly_pv_output(panel: dict, n_panels: int,
                             irradiance_kwh_m2_yr: float) -> list:
    """
    8760-h AC PV output (kW).
    P_array(t) = n_panels * panel_kw * shape(t) * PR.
    Normalised so annual sum = n_panels * panel_kw * irradiance * PR.
    """
    pkw  = panel["panel_power_w"] / 1000.0
    raw  = [n_panels * pkw * _irradiance_shape_factor(h % 24, (h // 24) % 365 + 1) * PR_PERFORMANCE_RATIO
            for h in range(8760)]
    tgt  = n_panels * pkw * irradiance_kwh_m2_yr * PR_PERFORMANCE_RATIO
    tot  = sum(raw)
    if tot > 0:
        raw = [v * tgt / tot for v in raw]
    return raw


# -- 4F  Hardware selection ---------------------------------------------------

def _select_panel(panel_brand) -> dict:
    """None → best efficiency/cost ratio. String → exact manufacturer match."""
    if panel_brand is None:
        return max(SOLAR_PANEL_CATALOG, key=lambda p: p["efficiency_percent"] / p["cost_per_wp_usd"])
    m = [p for p in SOLAR_PANEL_CATALOG if p["manufacturer"].lower() == panel_brand.lower()]
    if not m:
        raise ValueError(f"Brand '{panel_brand}' not found. "
                         f"Available: {[p['manufacturer'] for p in SOLAR_PANEL_CATALOG]}")
    return m[0]


def _select_battery(required_kwh: float):
    """Most cost-effective unit >= required_kwh. Returns None if required_kwh <= 0.5."""
    if required_kwh <= 0.5:
        return None
    cands = [b for b in BATTERY_CATALOG if b["usable_capacity_kwh"] >= required_kwh]
    if not cands:
        cands = BATTERY_CATALOG   # fallback: stack the largest unit
    return min(cands, key=lambda b: b["cost_usd"] / b["usable_capacity_kwh"])


# -- 4G  Dispatch simulation (rule-based, used only for economics) ------------

def _run_dispatch_simulation(hourly_load_kw: list, hourly_pv_kw: list,
                              hourly_tariffs: list, battery) -> dict:
    """
    Rule-based 8760-h dispatch.  Used ONLY to obtain import_cost_usd and
    export_credit_usd for _compute_economics().  The MILP already computes
    optimal annual import/export totals; this fills in the dollar-weighted
    cost breakdown that the financial model needs.

    Surplus hour:  charge battery first, then export remainder.
    Deficit hour:  discharge battery first, then import remainder.
    """
    has_b = battery is not None
    cap   = battery["usable_capacity_kwh"]       if has_b else 0.0
    maxc  = battery["max_charge_power_kw"]       if has_b else 0.0
    maxd  = battery["max_discharge_power_kw"]    if has_b else 0.0
    eta   = battery["round_trip_efficiency_pct"] / 100.0 if has_b else 1.0
    soc   = cap * 0.5

    tot_imp = tot_exp = imp_cost = exp_cred = bat_cyc = 0.0
    soc_s   = []

    for h in range(8760):
        net = hourly_load_kw[h] - hourly_pv_kw[h]
        if net < 0:          # surplus
            sur  = -net
            ckw  = min(maxc, (cap - soc) / eta) if has_b else 0.0
            ckw  = min(sur, ckw)
            soc += ckw * eta
            bat_cyc += ckw
            export = sur - ckw
            gbuy   = 0.0
        else:                # deficit
            dkw  = min(maxd, soc) if has_b else 0.0
            dkw  = min(net, dkw)
            soc -= dkw
            gbuy   = net - dkw
            export = 0.0
        soc      = max(0.0, min(cap, soc))
        tot_imp += gbuy;  tot_exp  += export
        imp_cost += gbuy  * hourly_tariffs[h]
        exp_cred += export * NEM_EXPORT_CREDIT
        soc_s.append(soc)

    return {"annual_import_kwh":  round(tot_imp,  1),
            "annual_export_kwh":  round(tot_exp,  1),
            "import_cost_usd":    round(imp_cost, 2),
            "export_credit_usd":  round(exp_cred, 2),
            "battery_kwh_cycled": round(bat_cyc,  1),
            "soc_series":         soc_s}


# -- 4H  Economics ------------------------------------------------------------

def _compute_economics(dispatch: dict, panel: dict, n_panels: int,
                        battery, battery_units: int,
                        annual_load_kwh: float, avg_tariff: float,
                        with_battery: bool) -> dict:
    """
    10-year NPV financial model.

    Year 0 capex:  gross = (pv + battery) * (1 + install_rate)
                   net   = gross * (1 - ITC)

    Years 1–10:    Traditional bill grows at utility_inflation.
                   Solar bill uses degraded PV, inflated tariff, O&M, inverter.
                   Net savings discounted at DISCOUNT_RATE.

    Payback = first year cumulative savings >= net_capex.
    NPV     = -net_capex + sum(savings / (1+r)^y).
    """
    array_w  = n_panels * panel["panel_power_w"]
    pv_cost  = array_w * panel["cost_per_wp_usd"]
    bat_cost = (battery["cost_usd"] * battery_units) if battery else 0.0
    hw       = pv_cost + bat_cost
    install  = hw * INSTALLATION_COST_RATE
    gross    = hw + install
    net_cap  = gross * (1.0 - FEDERAL_ITC_RATE)

    fixed_ann = SDGE_DAILY_FIXED_FEE * 365
    trad_y1   = annual_load_kwh * avg_tariff + fixed_ann
    solar_y1  = dispatch["import_cost_usd"] - dispatch["export_credit_usd"] + fixed_ann

    cumul = 0.0; payback = None; npv = -net_cap; rows = []
    for y in range(1, ANALYSIS_YEARS + 1):
        inf  = (1 + UTILITY_INFLATION_RATE) ** (y - 1)
        disc = (1 + DISCOUNT_RATE) ** y
        trad = trad_y1 * inf
        scl  = (1 - panel["degradation_rate"]) ** (y - 1)
        imp  = annual_load_kwh - (annual_load_kwh - dispatch["annual_import_kwh"]) * scl
        exp  = dispatch["annual_export_kwh"] * scl
        sol  = imp * avg_tariff * inf - exp * NEM_EXPORT_CREDIT + fixed_ann
        om   = O_AND_M_COST_PER_W_YR * array_w * inf
        inv  = INVERTER_REPLACEMENT_USD if y == INVERTER_REPLACEMENT_YR else 0.0
        tot_sol = sol + om + inv
        sav  = trad - tot_sol
        cumul += sav
        if payback is None and cumul >= net_cap:
            payback = y
        npv += sav / disc
        rows.append({"year": y,
                     "trad_bill_usd":     round(trad,    2),
                     "solar_total_usd":   round(tot_sol, 2),
                     "net_savings_usd":   round(sav,     2),
                     "cumulative_savings":round(cumul,   2)})

    sav_y1 = trad_y1 - solar_y1 - O_AND_M_COST_PER_W_YR * array_w
    return {
        "scenario":                                   "with_battery" if with_battery else "pv_only",
        "total_pv_cost_usd":                          round(pv_cost,   2),
        "total_battery_cost_usd":                     round(bat_cost,  2),
        "total_installation_cost_usd":                round(install,   2),
        "gross_capex_usd":                            round(gross,     2),
        "net_capex_after_itc_usd":                    round(net_cap,   2),
        "annual_grid_energy_import_kwh":              dispatch["annual_import_kwh"],
        "annual_grid_energy_export_kwh":              dispatch["annual_export_kwh"],
        "annual_electricity_bill_with_system_usd":    round(solar_y1,  2),
        "annual_electricity_bill_without_system_usd": round(trad_y1,   2),
        "annual_savings_usd":                         round(sav_y1,    2),
        "simple_payback_years":                       payback if payback else float("inf"),
        "npv_usd":                                    round(npv,       2),
        "ten_year_breakdown":                         rows,
    }


# =============================================================================
# SECTION 5 -- CORE MILP OPTIMIZER  (scipy / HiGHS)
# =============================================================================

def optimize_energy_system_milp(
    panel: dict,
    irradiance_kwh_m2_yr: float,
    hourly_load_kw: list,
    hourly_tariffs: list,
    roof_area_m2: float,
    budget_usd: float,
    force_battery: bool,
    annual_kwh: float,
) -> dict:
    """
    Full-year (8760-h) MILP that JOINTLY optimises panel count, battery
    capacity, and all hourly dispatch variables in one solve.

    Replaces the old PuLP optimize_energy_system() which:
      - only used a 672-h seasonal sample (not the full year)
      - separately simulated dispatch AFTER sizing (sub-optimal)
      - had a broken battery cost proxy ($800/kWh vs actual $852/kWh)

    Solver: scipy.optimize.milp → HiGHS (commercial-grade, free)
    Typical solve time: 5–15 s for the 8760-h problem.

    Objective
    ---------
    min  (Panels*panel_cost + BatCap*bat_cost) * (1-ITC) * annuity_factor
       + Σ_t [ Import(t) * Price_buy(t) ]
       - Σ_t [ Export(t) * NEM_credit   ]

    Constraints
    -----------
    C1  Energy balance    Load(t) = PV(t)+Discharge(t)+Import(t)-Charge(t)-Export(t)
    C2  SOC dynamics      SOC(t+1) = SOC(t) + η_c*Charge(t) - Discharge(t)/η_d
    C0  SOC initial       SOC(0) = BatCap * soc_init_frac
    C3  SOC upper         SOC(t) ≤ BatCap
    C4  SOC lower (DoD)   SOC(t) ≥ soc_min_frac * BatCap
    C5  Charge limit      Charge(t) ≤ c_rate * BatCap
    C6  Discharge limit   Discharge(t) ≤ c_rate * BatCap
    C7  Export limit      Export(t) ≤ PV(t)
    C8  Roof area         Panels * panel_area ≤ roof_area
    C9  Budget            (Panels*panel_cost + BatCap*bat_cost)*1.10 ≤ budget

    Parameters
    ----------
    panel               : dict   catalog entry from SOLAR_PANEL_CATALOG
    irradiance_kwh_m2_yr: float  annual GHI kWh/m²/yr (Open-Meteo)
    hourly_load_kw      : list   8760 hourly demand values (kW)
    hourly_tariffs      : list   8760 hourly TOU buy prices ($/kWh)
    roof_area_m2        : float  usable roof area
    budget_usd          : float  gross pre-ITC capital budget
    force_battery       : bool   True → BatCap ≥ 5 kWh enforced
    annual_kwh          : float  annual load total (informational)

    Returns
    -------
    dict with keys:
        n_panels            int
        battery_kwh_optimal float  (kWh)
        status              str    "Optimal" | "Time limit — best feasible returned" | ...
        objective_value     float  annualised cost ($/yr)
        solve_time_s        float
        annual_import_kwh   float  from optimal dispatch
        annual_export_kwh   float  from optimal dispatch
        soc_series          list   8760 SOC values (kWh) for plotting
    """
    t0 = time.time()

    T          = len(hourly_load_kw)                          # should be 8760
    panel_kw   = panel["panel_power_w"] / 1000.0
    panel_area = panel["panel_area_m2"]
    panel_cost = panel["panel_power_w"] * panel["cost_per_wp_usd"]
    max_panels = int(roof_area_m2 / panel_area)

    # ── Irradiance shape normalised to correct annual total ───────────────────
    raw_shapes = np.array([
        _irradiance_shape_factor(h % 24, (h // 24) % 365 + 1)
        for h in range(T)
    ])
    raw_sum    = raw_shapes.sum()
    target_sum = irradiance_kwh_m2_yr * PR_PERFORMANCE_RATIO
    irr_h      = raw_shapes * (target_sum / raw_sum) if raw_sum > 0 else raw_shapes

    Load = np.array(hourly_load_kw, dtype=float)
    Pbuy = np.array(hourly_tariffs, dtype=float)

    # ── Variable index layout ─────────────────────────────────────────────────
    n_vars = 5 * T + 3
    I_P   = 0
    I_B   = 1
    I_IMP = np.arange(2,         T + 2)      # Import(0..T-1)
    I_EXP = np.arange(T + 2,   2*T + 2)      # Export(0..T-1)
    I_CHG = np.arange(2*T + 2, 3*T + 2)      # Charge(0..T-1)
    I_DIS = np.arange(3*T + 2, 4*T + 2)      # Discharge(0..T-1)
    I_SOC = np.arange(4*T + 2, 5*T + 3)      # SOC(0..T)  — T+1 values

    print(f"    MILP: {n_vars:,} variables, {T} hours", flush=True)

    # ── Objective vector ──────────────────────────────────────────────────────
    c_obj           = np.zeros(n_vars)
    c_obj[I_P]      = panel_cost          * (1 - FEDERAL_ITC_RATE) * ANNUITY_FACTOR
    c_obj[I_B]      = BAT_COST_PER_KWH_PROXY * (1 - FEDERAL_ITC_RATE) * ANNUITY_FACTOR
    c_obj[I_IMP]    = Pbuy
    c_obj[I_EXP]    = -NEM_EXPORT_CREDIT

    # ── Variable bounds ───────────────────────────────────────────────────────
    lb = np.zeros(n_vars)
    ub = np.full(n_vars, np.inf)
    ub[I_P]   = max_panels
    ub[I_B]   = 50.0
    ub[I_SOC] = 200.0   # tightened per-hour by C3
    if force_battery:
        lb[I_B] = 5.0
    bounds = Bounds(lb=lb, ub=ub)

    # ── Integrality (1 = integer, 0 = continuous) ─────────────────────────────
    integrality      = np.zeros(n_vars)
    integrality[I_P] = 1   # Panels must be a whole number

    # ── Build sparse constraint matrix (COO → CSC) ────────────────────────────
    rs, cs, ds = [], [], []    # row, col, data for COO
    lo_c, hi_c = [], []        # per-row lower / upper bounds
    ridx = [0]                 # mutable row counter

    def _add(entries, lo, hi):
        for col, val in entries:
            rs.append(ridx[0]); cs.append(col); ds.append(val)
        lo_c.append(lo); hi_c.append(hi)
        ridx[0] += 1

    def eq(entries, rhs): _add(entries, rhs, rhs)
    def le(entries, rhs): _add(entries, -np.inf, rhs)

    # C1  Energy balance (equality, every hour)
    for t in range(T):
        pvc = panel_kw * irr_h[t]
        eq([(I_P,        pvc),
            (I_IMP[t],   1.0),
            (I_EXP[t],  -1.0),
            (I_CHG[t],  -1.0),
            (I_DIS[t],   1.0)], Load[t])

    # C2  SOC dynamics (equality, every hour)
    for t in range(T):
        eq([(I_SOC[t],    -1.0),
            (I_SOC[t+1],   1.0),
            (I_CHG[t],    -MILP_ETA_C),
            (I_DIS[t],     1.0 / MILP_ETA_D)], 0.0)

    # C0  SOC initial condition
    eq([(I_SOC[0], 1.0), (I_B, -MILP_SOC_INIT_FRAC)], 0.0)

    # C3  SOC upper bound
    for t in range(T + 1):
        le([(I_SOC[t],  1.0), (I_B, -1.0)], 0.0)

    # C4  SOC lower bound (DoD floor)
    for t in range(T + 1):
        le([(I_SOC[t], -1.0), (I_B, MILP_SOC_MIN_FRAC)], 0.0)

    # C5  Charge power limit
    for t in range(T):
        le([(I_CHG[t], 1.0), (I_B, -MILP_C_RATE)], 0.0)

    # C6  Discharge power limit
    for t in range(T):
        le([(I_DIS[t], 1.0), (I_B, -MILP_C_RATE)], 0.0)

    # C7  Export ≤ PV generated
    for t in range(T):
        le([(I_EXP[t], 1.0), (I_P, -panel_kw * irr_h[t])], 0.0)

    # C8  Roof area
    le([(I_P, panel_area)], roof_area_m2)

    # C9  Budget  (hardware * 1.10 ≤ budget)
    le([(I_P, panel_cost          * (1 + INSTALLATION_COST_RATE)),
        (I_B, BAT_COST_PER_KWH_PROXY * (1 + INSTALLATION_COST_RATE))], budget_usd)

    n_con = ridx[0]
    print(f"    Constraints: {n_con:,}   sparse nnz: {len(ds):,}", flush=True)

    A_sparse   = csc_matrix((np.array(ds), (np.array(rs), np.array(cs))),
                             shape=(n_con, n_vars))
    constraint = LinearConstraint(A_sparse, lb=np.array(lo_c), ub=np.array(hi_c))

    # ── Solve ─────────────────────────────────────────────────────────────────
    print("    Calling HiGHS solver ...", flush=True)
    result = milp(
        c=c_obj,
        constraints=constraint,
        integrality=integrality,
        bounds=bounds,
        options={"disp": False, "time_limit": 300, "mip_rel_gap": 0.005},
    )
    solve_time = round(time.time() - t0, 2)

    STATUS = {0: "Optimal",
              1: "Iteration limit",
              2: "Infeasible",
              3: "Unbounded",
              4: "Infeasible or unbounded",
              5: "Numerical error",
              6: "Time limit — best feasible returned"}

    if result.status in (0, 6) and result.x is not None:
        x        = result.x
        n_panels = max(1, int(round(x[I_P])))
        bat_kwh  = max(0.0, round(x[I_B], 3))
        return {
            "n_panels":            n_panels,
            "battery_kwh_optimal": bat_kwh,
            "status":              STATUS.get(result.status, f"Code {result.status}"),
            "objective_value":     round(result.fun, 4),
            "solve_time_s":        solve_time,
            "annual_import_kwh":   round(float(x[I_IMP].sum()), 1),
            "annual_export_kwh":   round(float(x[I_EXP].sum()), 1),
            "soc_series":          x[I_SOC][1:].tolist(),
        }
    else:
        print(f"    [WARNING] {STATUS.get(result.status, result.status)} — using roof-limit fallback.")
        return {
            "n_panels":            max(1, int(roof_area_m2 // panel_area)),
            "battery_kwh_optimal": 5.0 if force_battery else 0.0,
            "status":              f"Fallback ({STATUS.get(result.status, result.status)})",
            "objective_value":     0.0,
            "solve_time_s":        solve_time,
            "annual_import_kwh":   round(float(Load.sum()), 1),
            "annual_export_kwh":   0.0,
            "soc_series":          [],
        }


# =============================================================================
# SECTION 6 -- MASTER ORCHESTRATOR
# =============================================================================

def recommend_residential_energy_system(user_profile: dict) -> dict:
    """
    Full pipeline:
      validate → irradiance → tariffs → load → select panel →
      MILP (PV-only) → MILP (PV+Battery) → dispatch sim → 10-yr economics

    Required keys: latitude, longitude, budget_usd
    Optional keys: annual_consumption_kwh, roof_area_m2, rate_plan,
                   panel_brand, num_evs, num_people, num_daytime_occupants

    Returns
    -------
    dict with top-level keys:
        solar_cell_spec, panel_configuration,
        pv_only       {array_configuration, battery_configuration, economic_summary},
        with_battery  {array_configuration, battery_configuration, economic_summary},
        solver_metadata
    """
    print("\n" + "=" * 65)
    print("  Residential Energy System Recommendation  (dual-run MILP)")
    print("=" * 65)

    # -- Step 1: Validate ------------------------------------------------------
    print("\n[1/9] Validating user profile ...")
    for k in ["latitude", "longitude", "budget_usd"]:
        if k not in user_profile:
            raise KeyError(f"Missing required key in user_profile: '{k}'")
    lat  = float(user_profile["latitude"])
    lon  = float(user_profile["longitude"])
    bud  = float(user_profile["budget_usd"])
    roof = float(user_profile.get("roof_area_m2", 40.0))
    rp   = str(user_profile.get("rate_plan", DEFAULT_RATE_PLAN))
    br   = user_profile.get("panel_brand", None)
    akwh_raw = user_profile.get("annual_consumption_kwh", None)
    akwh     = float(akwh_raw) if akwh_raw is not None else None
    nevs = int(user_profile.get("num_evs", 0))
    nppl = int(user_profile.get("num_people", 3))
    nday = int(user_profile.get("num_daytime_occupants", 1))
    print(f"    ({lat}, {lon}) | budget ${bud:,.0f} | roof {roof} m² | plan {rp}")

    # -- Step 2: Irradiance ----------------------------------------------------
    print("[2/9] Fetching irradiance from Open-Meteo ...")
    irr = _fetch_irradiance(lat, lon)
    print(f"    Annual GHI: {irr} kWh/m²/yr")

    # -- Step 3: Tariffs -------------------------------------------------------
    print(f"[3/9] Building SDG&E tariff schedule ({rp}) ...")
    tars = _build_hourly_tariffs(rp, year=2024)
    avgt = float(np.mean(tars))
    print(f"    Average: ${avgt:.4f}/kWh")

    # -- Step 4: Load ----------------------------------------------------------
    print("[4/9] Building 8760-h load profile ...")
    try:
        load, akwh = _load_household_profile_from_eia(lat, lon, akwh, nevs, nppl, nday)
        print(f"    Source: EIA 5-yr average  |  Annual: {akwh:,.0f} kWh")
    except FileNotFoundError as e:
        print(f"    [FALLBACK] {e}")
        if akwh is None:
            akwh = 7500.0
            print(f"    annual_consumption_kwh not set — defaulting to {akwh:,.0f} kWh")
        load = _build_annual_load_profile(akwh, nevs, nppl, nday)
        print(f"    Source: synthetic shape  |  Annual: {sum(load):,.0f} kWh")

    # -- Step 5: Panel ---------------------------------------------------------
    print("[5/9] Selecting panel ...")
    panel = _select_panel(br)
    print(f"    {panel['manufacturer']} {panel['model']}  "
          f"{panel['efficiency_percent']}%  ${panel['cost_per_wp_usd']}/Wp")

    # -- Step 5.5: Calculate True Physical Fit ("Tetris" Math) -----------------
    rl = float(user_profile.get("roof_length_m") or math.sqrt(roof * 2))
    rw = float(user_profile.get("roof_width_m")  or math.sqrt(roof / 2))
    pw = panel["panel_area_m2"] ** 0.5 * 0.75   # panel width
    ph = panel["panel_area_m2"] / pw            # panel height
    
    fit_portrait  = int(rw / pw) * int(rl / ph)
    fit_landscape = int(rw / ph) * int(rl / pw)
    true_max_panels = max(fit_portrait, fit_landscape)
    
    # Constrain the roof area so the MILP cannot mathematically buy panels that don't fit physically
    roof = true_max_panels * panel["panel_area_m2"]
    print(f"    [GEOMETRY] Max physical panels fitting on {rl}m x {rw}m roof: {true_max_panels}")
    # -- Step 6: MILP — PV only -----------------------------------------------
    print("[6/9] MILP run 1 — PV only (8760-h, HiGHS) ...")
    o1 = optimize_energy_system_milp(panel, irr, load, tars, roof, bud, False, akwh)
    print(f"    Panels: {o1['n_panels']}  Status: {o1['status']}  ({o1['solve_time_s']} s)")

    # -- Step 7: MILP — PV + Battery ------------------------------------------
    print("[7/9] MILP run 2 — PV + Battery (8760-h, HiGHS) ...")
    o2 = optimize_energy_system_milp(panel, irr, load, tars, roof, bud, True, akwh)
    print(f"    Panels: {o2['n_panels']}  Battery: {o2['battery_kwh_optimal']} kWh  "
          f"Status: {o2['status']}  ({o2['solve_time_s']} s)")

    # -- Step 8: PV output arrays (for dispatch sim) ---------------------------
    print("[8/9] Building hourly PV output arrays ...")
    pv1 = _build_hourly_pv_output(panel, o1["n_panels"], irr)
    pv2 = _build_hourly_pv_output(panel, o2["n_panels"], irr)

    # -- Step 9: Dispatch sim + economics -------------------------------------
    # The MILP gives optimal annual totals; the dispatch sim re-runs with the
    # chosen hardware to get dollar-weighted import_cost / export_credit needed
    # by _compute_economics().
    print("[9/9] Dispatch simulation + 10-year financials ...")
    d1  = _run_dispatch_simulation(load, pv1, tars, None)
    ec1 = _compute_economics(d1, panel, o1["n_panels"], None, 0, akwh, avgt, False)

    bs = _select_battery(o2["battery_kwh_optimal"])
    bunt = 0; stk = None
    if bs:
        bunt = max(1, int(np.ceil(o2["battery_kwh_optimal"] / bs["usable_capacity_kwh"])))
        stk  = dict(bs)
        stk["usable_capacity_kwh"]   *= bunt
        stk["max_charge_power_kw"]   *= bunt
        stk["max_discharge_power_kw"]*= bunt
    d2  = _run_dispatch_simulation(load, pv2, tars, stk)
    ec2 = _compute_economics(d2, panel, o2["n_panels"], bs, bunt, akwh, avgt, True)

    print(f"    PV-only      payback: {ec1['simple_payback_years']} yr  "
          f"NPV ${ec1['npv_usd']:,.0f}")
    print(f"    With-battery payback: {ec2['simple_payback_years']} yr  "
          f"NPV ${ec2['npv_usd']:,.0f}")

    # -- Cell / array / battery config helpers ---------------------------------
    user_profile = USER_PROFILE  
    ns  = panel["cells_in_series"];  np_ = panel["cells_in_parallel"]
    pc  = panel["panel_power_w"] / (ns * np_)
    vc  = panel["vmp_v"] / ns
    ic  = pc / vc
    vocc  = panel["voc_v"] / ns
    iscc  = panel["isc_a"] / np_
    cc    = panel["panel_power_w"] * panel["cost_per_wp_usd"] / (ns * np_)

    def acfg(n):
        """
        Full array configuration:
        1. Try both portrait and landscape panel orientations on the roof.
        2. For each physical layout (rows_on_roof × cols_on_roof), find the
            electrical string split (panels_in_series × parallel_strings) that
            brings string voltage closest to 400 V while respecting the layout.
        3. Return the layout with the highest roof utilisation.
        """
        p_w = panel["panel_area_m2"] ** 0.5 * 0.75   # approx panel width  (~0.98 m)
        p_h = panel["panel_area_m2"] / p_w            # approx panel height (~1.83 m)

        # Roof dimensions — use USER_PROFILE values if supplied, else sqrt estimate
        rl = float(user_profile.get("roof_length_m") or math.sqrt(roof * 2))
        rw = float(user_profile.get("roof_width_m")  or math.sqrt(roof / 2))

        best = None
        best_util = -1.0

        for (ph, pw) in [(p_h, p_w), (p_w, p_h)]:   # portrait then landscape
            orientation = "portrait" if ph > pw else "landscape"
            cols = max(1, int(rw // pw))   # panels fitting across the width
            rows = max(1, int(rl // ph))   # panels fitting along the length
            max_fit = rows * cols
            if max_fit < n:
                continue   # this orientation can't fit n panels — skip

            # Electrical: find series count closest to 400 V target
            # series must divide n evenly, and series <= cols (one string per row)
            best_ns2, best_np2, best_diff = 1, n, 1e9
            for ns2 in range(1, n + 1):
                if n % ns2 != 0:
                    continue
                np2 = n // ns2
                diff = abs(ns2 * panel["vmp_v"] - 400)
                if diff < best_diff:
                    best_diff = diff
                    best_ns2  = ns2
                    best_np2  = np2

            util = round(100 * n * panel["panel_area_m2"] / roof, 1)
            candidate = {
                # Physical layout
                "orientation":                   orientation,
                "panels_per_row_on_roof":        cols,
                "panel_rows_on_roof":            rows,
                "max_panels_fitting_roof":       max_fit,
                # Within-panel cell config
                "cells_in_series_per_panel":     panel["cells_in_series"],
                "cells_in_parallel_per_panel":   panel["cells_in_parallel"],
                # Electrical string config
                "panels_in_series_per_string":   best_ns2,
                "parallel_strings":              best_np2,
                "total_panels":                  n,
                # Electrical totals
                "string_voltage_v":              round(best_ns2 * panel["vmp_v"], 2),
                "array_current_a":               round(best_np2 * panel["imp_a"], 2),
                "total_dc_capacity_kw":          round(n * panel["panel_power_w"] / 1000, 3),
                # Area
                "total_array_area_m2":           round(n * panel["panel_area_m2"], 2),
                "roof_area_utilization_percent": util,
            }
            if util > best_util:
                best_util = util
                best = candidate

        # Fallback: if no orientation could fit n panels, use old voltage-only logic
        if best is None:
            best_ns2, best_np2, best_diff = 1, n, 1e9
            for ns2 in range(1, n + 1):
                if n % ns2 != 0: continue
                diff = abs(ns2 * panel["vmp_v"] - 400)
                if diff < best_diff:
                    best_diff = diff; best_ns2 = ns2; best_np2 = n // ns2
            best = {
                "orientation":                   "unknown (roof dims not supplied)",
                "panels_per_row_on_roof":        None,
                "panel_rows_on_roof":            None,
                "max_panels_fitting_roof":       None,
                "cells_in_series_per_panel":     panel["cells_in_series"],
                "cells_in_parallel_per_panel":   panel["cells_in_parallel"],
                "panels_in_series_per_string":   best_ns2,
                "parallel_strings":              best_np2,
                "total_panels":                  n,
                "string_voltage_v":              round(best_ns2 * panel["vmp_v"], 2),
                "array_current_a":               round(best_np2 * panel["imp_a"], 2),
                "total_dc_capacity_kw":          round(n * panel["panel_power_w"] / 1000, 3),
                "total_array_area_m2":           round(n * panel["panel_area_m2"], 2),
                "roof_area_utilization_percent": round(100 * n * panel["panel_area_m2"] / roof, 1),
            }
        return best

    def bcfg(spec, units, _kwh):
        if spec is None or units == 0:
            return {"required": False, "manufacturer": None, "model": None,
                    "units_required": None, "total_usable_capacity_kwh": None,
                    "nominal_voltage_v": None, "max_charge_power_kw": None,
                    "max_discharge_power_kw": None,
                    "round_trip_efficiency_percent": None, "cycle_life": None,
                    "cost_per_unit_usd": None, "total_battery_cost_usd": None}
        return {"required":                      True,
                "manufacturer":                  spec["manufacturer"],
                "model":                         spec["model"],
                "units_required":                units,
                "total_usable_capacity_kwh":     round(units * spec["usable_capacity_kwh"], 2),
                "nominal_voltage_v":             spec["nominal_voltage_v"],
                "max_charge_power_kw":           round(units * spec["max_charge_power_kw"], 2),
                "max_discharge_power_kw":        round(units * spec["max_discharge_power_kw"], 2),
                "round_trip_efficiency_percent": spec["round_trip_efficiency_pct"],
                "cycle_life":                    spec["cycle_life"],
                "cost_per_unit_usd":             spec["cost_usd"],
                "total_battery_cost_usd":        units * spec["cost_usd"]}

    return {
        "solar_cell_spec": {
            "manufacturer":                              panel["manufacturer"],
            "model":                                     panel["model"],
            "max_power_w":                               round(pc,   4),
            "voltage_at_max_power_v":                    round(vc,   4),
            "current_at_max_power_a":                    round(ic,   4),
            "open_circuit_voltage_v":                    round(vocc, 4),
            "short_circuit_current_a":                   round(iscc, 4),
            "efficiency_percent":                        panel["efficiency_percent"],
            "temperature_coefficient_percent_per_degC":  panel["temp_coeff_pct_per_C"],
            "cost_per_cell_usd":                         round(cc,   4),
        },
        "panel_configuration": {
            "cells_in_series":          ns,
            "cells_in_parallel":        np_,
            "panel_voltage_v":          panel["vmp_v"],
            "panel_current_a":          panel["imp_a"],
            "panel_power_w":            panel["panel_power_w"],
            "panel_area_m2":            panel["panel_area_m2"],
            "panel_efficiency_percent": panel["efficiency_percent"],
            "cost_per_panel_usd":       round(panel["panel_power_w"] * panel["cost_per_wp_usd"], 2),
        },
        "pv_only": {
            "array_configuration":   acfg(o1["n_panels"]),
            "battery_configuration": bcfg(None, 0, 0),
            "economic_summary":      ec1,
        },
        "with_battery": {
            "array_configuration":   acfg(o2["n_panels"]),
            "battery_configuration": bcfg(bs, bunt, o2["battery_kwh_optimal"]),
            "economic_summary":      ec2,
        },
        "solver_metadata": {
            "pv_only": {
                "objective_value":     o1["objective_value"],
                "optimization_status": o1["status"],
                "solve_time_seconds":  o1["solve_time_s"],
                "model_type":          "MILP / scipy-HiGHS / 8760-h full-year",
            },
            "with_battery": {
                "objective_value":     o2["objective_value"],
                "optimization_status": o2["status"],
                "solve_time_seconds":  o2["solve_time_s"],
                "model_type":          "MILP / scipy-HiGHS / 8760-h full-year",
            },
        },
    }


# =============================================================================
# SECTION 7 -- MAIN
# =============================================================================

if __name__ == "__main__":
    res = recommend_residential_energy_system(USER_PROFILE)
    W   = 65

    print("\n" + "="*W + "\n  SOLAR CELL SPEC\n" + "="*W)
    for k, v in res["solar_cell_spec"].items():
        print(f"  {k:<50} {v}")

    print("\n" + "="*W + "\n  PANEL CONFIGURATION\n" + "="*W)
    for k, v in res["panel_configuration"].items():
        print(f"  {k:<50} {v}")

    for sk, lb in [("pv_only", "PV ONLY"), ("with_battery", "PV + BATTERY")]:
        sc = res[sk]
        print(f"\n{'='*W}\n  SCENARIO: {lb}\n{'='*W}")
        print("\n  Array Configuration\n  " + "-"*45)
        for k, v in sc["array_configuration"].items():
            print(f"  {k:<50} {v}")
        print("\n  Battery Configuration\n  " + "-"*45)
        for k, v in sc["battery_configuration"].items():
            print(f"  {k:<50} {v}")
        eco = sc["economic_summary"]
        print("\n  Economic Summary\n  " + "-"*45)
        skip = {"ten_year_breakdown", "scenario"}
        for k, v in eco.items():
            if k not in skip:
                fmt = ("$" + f"{v:,.2f}") if isinstance(v, float) and "usd" in k else str(v)
                print(f"  {k:<50} {fmt}")
        print(f"\n  {'Year':>4}  {'Traditional $':>14}  {'Solar+OM $':>10}  "
              f"{'Savings $':>10}  {'Cumulative $':>13}")
        for r in eco["ten_year_breakdown"]:
            print(f"  {r['year']:>4}  {r['trad_bill_usd']:>14,.2f}  "
                  f"{r['solar_total_usd']:>10,.2f}  {r['net_savings_usd']:>10,.2f}  "
                  f"{r['cumulative_savings']:>13,.2f}")

    print("\n" + "="*W + "\n  SOLVER METADATA\n" + "="*W)
    for run, meta in res["solver_metadata"].items():
        print(f"\n  {run}")
        for k, v in meta.items():
            print(f"    {k:<46} {v}")
    print()