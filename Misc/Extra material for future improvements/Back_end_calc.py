import os
import requests
import pandas as pd
import numpy as np
import hashlib

# =============================================================================
# SYSTEM & FINANCIAL CONSTANTS
# =============================================================================
SOLAR_PANELS = {
    "SunPower Maxeon 3": {"wattage": 0.400, "efficiency": 0.226, "cost": 400, "deg_rate": 0.0025},
    "Panasonic EverVolt": {"wattage": 0.380, "efficiency": 0.217, "cost": 350, "deg_rate": 0.0026},
    "LG NeON R": {"wattage": 0.380, "efficiency": 0.220, "cost": 360, "deg_rate": 0.0030},
    "Q CELLS Q.PEAK": {"wattage": 0.400, "efficiency": 0.204, "cost": 250, "deg_rate": 0.0050},
    "Generic": {"wattage": 0.350, "efficiency": 0.180, "cost": 200, "deg_rate": 0.0050}
}

INSTALLATION_COST_FIXED = 4000
INSTALLATION_COST_PER_WATT = 2.50
BATTERY_COST_PER_KWH = 800
FEDERAL_ITC = 0.30
ANNUAL_MAINTENANCE = 150
RATE_ESCALATION = 0.045
NEM_3_AVG_EXPORT = 0.05

TEMP_COEFFICIENT = -0.0035   
INVERTER_DC_AC_RATIO = 1.2   
BATTERY_RTE = 0.89           
SYSTEM_LOSSES = 0.14         

# =============================================================================
# REGIONAL GENERATOR CONSTANTS
# =============================================================================
REGIONAL_LOAD_PATH = r"C:\Users\shubh\Desktop\Hard disk\College(PG)\Academics at UCSD\Y1Q2\ECE 285 - Spec Topic - Signal & Image Robotics - Smartgrids\Project\Step 1\San_Diego_Load_EIA_Fixed.csv"
TOTAL_CUSTOMERS = 1040149
COASTAL_LON_REF = -117.25        
CITY_CENTER_LAT = 32.7157        
CITY_CENTER_LON = -117.1611      

# =============================================================================
# HOUSEHOLD EXTRACTION LOGIC (Integrated from your generator script)
# =============================================================================

def generate_location_seed(lat, lon):
    loc_str = f"{lat}_{lon}"
    hash_obj = hashlib.sha256(loc_str.encode('utf-8'))
    return int(hash_obj.hexdigest(), 16) % (2**32)

def calculate_longitude_factor(lon):
    distance_from_coast = lon - COASTAL_LON_REF
    if distance_from_coast >= 0.15: return 1.25
    elif distance_from_coast >= 0.10: return 1.05 + (distance_from_coast - 0.10) * 4.0
    elif distance_from_coast >= 0: return 0.95 + distance_from_coast * 1.0
    elif distance_from_coast >= -0.05: return 0.90 + (distance_from_coast + 0.05) * 1.0
    else: return 0.85

def calculate_latitude_factor(lat):
    if lat < 32.60: return 1.10
    elif lat < 32.70: return 1.05
    elif lat < 32.85: return 1.00
    elif lat < 32.95: return 0.95
    else: return 0.90

def calculate_elevation_factor(lat, lon):
    inland_factor = max(0, lon - COASTAL_LON_REF)
    north_factor = max(0, lat - 32.70) * 2
    elevation_proxy = inland_factor + north_factor
    return 1.0 + (elevation_proxy * 0.15)

def calculate_household_characteristics(seed):
    rng = np.random.RandomState(seed)
    size_factor = np.clip(rng.normal(1.0, 0.15), 0.7, 1.3)
    efficiency_factor = np.clip(rng.normal(1.0, 0.1), 0.8, 1.2)
    return size_factor * efficiency_factor

def calculate_density_factor(lat, lon):
    distance_from_center = np.sqrt((lat - CITY_CENTER_LAT)**2 + (lon - CITY_CENTER_LON)**2)
    if distance_from_center < 0.03: return 0.7
    elif distance_from_center < 0.08: return 0.9
    elif distance_from_center < 0.15: return 1.1
    else: return 1.3

def calculate_economic_age_factor(lat, lon):
    is_coastal = lon < -117.20
    is_north = lat > 32.80
    distance_from_center = np.sqrt((lat - CITY_CENTER_LAT)**2 + (lon - CITY_CENTER_LON)**2)
    is_urban_core = distance_from_center < 0.05
    
    if is_coastal and is_north: return 1.15
    elif is_coastal and not is_north: return 1.05
    elif is_urban_core: return 1.25
    elif lon > -117.00: return 0.95
    else: return 1.10

def apply_solar_profile(df, lat, lon, seed):
    rng = np.random.RandomState(seed + 1000)
    is_coastal = lon < -117.20
    is_north = lat > 32.80
    distance_from_center = np.sqrt((lat - CITY_CENTER_LAT)**2 + (lon - CITY_CENTER_LON)**2)
    
    if is_coastal and is_north: solar_prob = 0.35
    elif is_coastal or (lon > -117.00): solar_prob = 0.20
    elif distance_from_center < 0.05: solar_prob = 0.05
    else: solar_prob = 0.15
    
    if not (rng.random() < solar_prob): return np.ones(len(df))
    
    hours = df['datetime_local'].dt.hour.values
    solar_intensity = np.clip(np.sin((hours - 6) * np.pi / 12), 0, 1)
    solar_intensity[(hours < 6) | (hours > 18)] = 0
    max_reduction = rng.uniform(0.4, 0.7)
    return 1.0 - (solar_intensity * (1.0 - max_reduction))

def apply_ev_charging(df, lat, lon, seed):
    rng = np.random.RandomState(seed + 2000)
    is_coastal = lon < -117.20
    is_north = lat > 32.80
    distance_from_center = np.sqrt((lat - CITY_CENTER_LAT)**2 + (lon - CITY_CENTER_LON)**2)
    
    if is_coastal and is_north: ev_prob = 0.30
    elif is_coastal or (lon > -117.05 and lat > 32.75): ev_prob = 0.15
    elif distance_from_center < 0.05: ev_prob = 0.10
    else: ev_prob = 0.08
    
    if not (rng.random() < ev_prob): return np.zeros(len(df))
    
    start_hour = rng.randint(18, 24)
    duration = rng.randint(3, 7)
    hours = df['datetime_local'].dt.hour.values
    end_hour = (start_hour + duration) % 24
    
    if start_hour < end_hour: is_charging = (hours >= start_hour) & (hours < end_hour)
    else: is_charging = (hours >= start_hour) | (hours < end_hour)
    
    charger_power = rng.uniform(3.0, 7.0)
    return np.where(is_charging, charger_power, 0.0)

def calculate_multigenerational_factor(lat, lon, seed):
    rng = np.random.RandomState(seed + 3000)
    distance_from_center = np.sqrt((lat - CITY_CENTER_LAT)**2 + (lon - CITY_CENTER_LON)**2)
    
    if lat < 32.75 and distance_from_center < 0.10: prob = 0.25
    elif distance_from_center < 0.10: prob = 0.15
    else: prob = 0.10
    
    return rng.uniform(1.20, 1.50) if rng.random() < prob else 1.0

def generate_household_consumption(lat: float, lon: float, start_date: str, end_date: str) -> pd.DataFrame:
    """End-to-end extraction from regional load straight to dynamic timeframe matrix."""
    if not os.path.exists(REGIONAL_LOAD_PATH):
        raise FileNotFoundError(f"Missing base EIA data: {REGIONAL_LOAD_PATH}")
        
    df = pd.read_csv(REGIONAL_LOAD_PATH)
    df['datetime_utc'] = pd.to_datetime(df['Timestamp_UTC'])
    df['datetime_local'] = df['datetime_utc'].dt.tz_localize('UTC').dt.tz_convert('America/Los_Angeles')
    df['avg_household_kw'] = (df['MW_Load'] * 1000) / TOTAL_CUSTOMERS
    
    seed = generate_location_seed(lat, lon)
    base_scalar_multiplier = (
        calculate_longitude_factor(lon) *
        calculate_latitude_factor(lat) *
        calculate_elevation_factor(lat, lon) *
        calculate_household_characteristics(seed) *
        calculate_density_factor(lat, lon) *
        calculate_economic_age_factor(lat, lon) *
        calculate_multigenerational_factor(lat, lon, seed)
    )
    
    df['household_kw'] = df['avg_household_kw'] * base_scalar_multiplier
    df['household_kw'] = df['household_kw'] * apply_solar_profile(df, lat, lon, seed)
    df['household_kw'] = df['household_kw'] + apply_ev_charging(df, lat, lon, seed)
    df['household_kw'] = df['household_kw'].clip(lower=0)
    
    rng = np.random.RandomState(seed)
    df['household_kw'] = df['household_kw'] * rng.normal(1.0, 0.03, size=len(df))
    
    # Format for backend merging
    df['datetime'] = df['datetime_local'].dt.tz_localize(None)
    df['date'] = df['datetime'].dt.date
    df['hour'] = df['datetime'].dt.hour
    
    s_date = pd.to_datetime(start_date).date()
    e_date = pd.to_datetime(end_date).date()
    return df[(df['date'] >= s_date) & (df['date'] <= e_date)].copy()

# =============================================================================
# WEATHER, TARIFF, AND FINANCIAL ENGINE
# =============================================================================

def fetch_hourly_weather(latitude: float, longitude: float, start_date: str, end_date: str) -> pd.DataFrame:
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": latitude, "longitude": longitude,
        "start_date": start_date, "end_date": end_date,
        "hourly": ["shortwave_radiation", "temperature_2m"],
        "timezone": "auto",
    }
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    data = response.json()
    
    df = pd.DataFrame({
        "datetime": pd.to_datetime(pd.Series(data["hourly"]["time"])),
        "irradiance_w_m2": data["hourly"]["shortwave_radiation"],
        "temp_c": data["hourly"]["temperature_2m"]
    })
    df["date"] = df["datetime"].dt.date
    df["hour"] = df["datetime"].dt.hour
    return df

def load_tou_rates(plan_name: str, start_date: str, end_date: str) -> pd.DataFrame:
    file_map = {
        "DR": r"C:\Users\shubh\Desktop\Hard disk\College(PG)\Academics at UCSD\Y1Q2\ECE 285 - Spec Topic - Signal & Image Robotics - Smartgrids\Project\Step 1\Tariff Data\TOU-DR\tou_dr_daily_2021_2025.csv", 
        "DR1": r"C:\Users\shubh\Desktop\Hard disk\College(PG)\Academics at UCSD\Y1Q2\ECE 285 - Spec Topic - Signal & Image Robotics - Smartgrids\Project\Step 1\Tariff Data\TOU-DR1\tou_dr1_daily_2021_2025.csv", 
        "DR2": r"C:\Users\shubh\Desktop\Hard disk\College(PG)\Academics at UCSD\Y1Q2\ECE 285 - Spec Topic - Signal & Image Robotics - Smartgrids\Project\Step 1\Tariff Data\TOU-DR2\tou_dr2_daily_2021_2025.csv"
    }
    df = pd.read_csv(file_map[plan_name])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    s_date = pd.to_datetime(start_date).date()
    e_date = pd.to_datetime(end_date).date()
    return df[(df["date"] >= s_date) & (df["date"] <= e_date)]

def get_hourly_tou_rate(row):
    h = row['hour']
    if 16 <= h < 21: return row['on_peak_$/kwh']
    elif 0 <= h < 6: return row['super_off_peak_$/kwh']
    else: return row['off_peak_$/kwh']

def calculate_irr(cash_flows):
    rate = 0.10
    for _ in range(100):
        npv = sum(cf / (1 + rate)**i for i, cf in enumerate(cash_flows))
        npv_deriv = sum(-i * cf / (1 + rate)**(i + 1) for i, cf in enumerate(cash_flows))
        if abs(npv) < 1e-5 or npv_deriv == 0: break
        rate = rate - npv / npv_deriv
    return rate

def calculate_metrics(user_inputs: dict) -> dict:
    brand_specs = SOLAR_PANELS[user_inputs["panel_brand"]]
    num_panels = user_inputs["num_panels"]
    system_capacity_kw = num_panels * brand_specs["wattage"]
    inverter_capacity_kw = system_capacity_kw / INVERTER_DC_AC_RATIO
    
    # 1. Direct Memory Pipeline
    cons_df = generate_household_consumption(user_inputs["latitude"], user_inputs["longitude"], user_inputs["start_date"], user_inputs["end_date"])
    weather_df = fetch_hourly_weather(user_inputs["latitude"], user_inputs["longitude"], user_inputs["start_date"], user_inputs["end_date"])
    tou_df = load_tou_rates(user_inputs["tou_plan"], user_inputs["start_date"], user_inputs["end_date"])
    
    # 2. Merge Data 
    master_df = pd.merge(cons_df, weather_df, on=['date', 'hour'], how='inner')
    master_df = pd.merge(master_df, tou_df, on='date', how='inner')
    
    if master_df.empty:
        raise ValueError("No overlapping data found. Check your date ranges.")

    # 3. Solar Physics
    dc_gen = system_capacity_kw * (master_df["irradiance_w_m2"] / 1000.0)
    cell_temp = master_df["temp_c"] + (master_df["irradiance_w_m2"] / 800.0) * 25
    temp_penalty = np.where(cell_temp > 25, 1 + (TEMP_COEFFICIENT * (cell_temp - 25)), 1)
    dc_gen_adjusted = dc_gen * temp_penalty * (1 - SYSTEM_LOSSES)
    master_df['ac_solar_kw'] = np.clip(dc_gen_adjusted, a_min=0, a_max=inverter_capacity_kw)
    master_df['hourly_rate'] = master_df.apply(get_hourly_tou_rate, axis=1)

    # 4. Financial Simulation
    years = user_inputs["years"]
    gross_cost = (num_panels * brand_specs["cost"]) + INSTALLATION_COST_FIXED + (system_capacity_kw * 1000 * INSTALLATION_COST_PER_WATT)
    if user_inputs["include_battery"]: gross_cost += user_inputs["battery_kwh"] * BATTERY_COST_PER_KWH
    net_cost = gross_cost * (1 - FEDERAL_ITC)

    cash_flows = [-net_cost]
    annual_savings = 0
    trad_cumulative = 0.0
    solar_cumulative = net_cost
    
    annual_cons = master_df['household_kw'].sum()
    avg_kwh_cost = master_df['hourly_rate'].mean()
    annual_sun_hrs = (master_df["irradiance_w_m2"] > 50).sum()
    
    for year in range(years):
        yearly_trad_cost = 0.0
        yearly_solar_cost = ANNUAL_MAINTENANCE
        yearly_generation = 0.0
        
        rate_mult = (1 + RATE_ESCALATION) ** year
        deg_mult = (1 - brand_specs["deg_rate"]) ** year
        battery_soc = 0.0 
        battery_max = user_inputs["battery_kwh"]
        
        grouped_days = master_df.groupby('date')
        for _, day_df in grouped_days:
            min_bill = day_df.iloc[0].get("minimum_bill_$/day", 0)
            base_charge = day_df.iloc[0].get("base_services_charge_$/day", 0)
            daily_fixed = max(pd.to_numeric(min_bill, errors='coerce') or 0, 
                              pd.to_numeric(base_charge, errors='coerce') or 0) * rate_mult
            yearly_trad_cost += daily_fixed
            yearly_solar_cost += daily_fixed

        for _, row in master_df.iterrows():
            hourly_load = row['household_kw']
            hourly_solar = row['ac_solar_kw'] * deg_mult
            current_rate = row['hourly_rate'] * rate_mult
            
            yearly_trad_cost += (hourly_load * current_rate)
            yearly_generation += hourly_solar
            net_energy = hourly_load - hourly_solar
            
            if net_energy > 0:
                if user_inputs["include_battery"] and battery_soc > 0:
                    if current_rate > 0.40 or hourly_solar == 0:
                        drawn = min(net_energy, battery_soc)
                        battery_soc -= drawn
                        net_energy -= drawn
                yearly_solar_cost += (net_energy * current_rate)
            else:
                excess = abs(net_energy)
                if user_inputs["include_battery"] and battery_soc < battery_max:
                    space_left = battery_max - battery_soc
                    charged = min(excess * BATTERY_RTE, space_left) 
                    battery_soc += charged
                    excess -= (charged / BATTERY_RTE)
                yearly_solar_cost -= (excess * NEM_3_AVG_EXPORT)
                
        trad_cumulative += yearly_trad_cost
        solar_cumulative += yearly_solar_cost
        savings = yearly_trad_cost - yearly_solar_cost
        cash_flows.append(savings)
        if year == 0: annual_savings = savings
        
    npv = sum(cf / (1 + 0.05)**i for i, cf in enumerate(cash_flows))
    irr = calculate_irr(cash_flows)
    roi = ((annual_savings * years) - net_cost) / net_cost if net_cost > 0 else 0
    
    annual_gen_per_panel = yearly_generation / num_panels if num_panels > 0 else 0
    panels_100 = int(annual_cons / annual_gen_per_panel) if annual_gen_per_panel > 0 else 0
    panels_70 = int((annual_cons * 0.70) / annual_gen_per_panel) if annual_gen_per_panel > 0 else 0
    max_panels_budget = int(user_inputs["budget"] / brand_specs["cost"])
    optimal_panels = max(panels_70, min(max_panels_budget, panels_100))
    optimal_gen = optimal_panels * annual_gen_per_panel
    weekly_cons = master_df.groupby(pd.to_datetime(master_df['date']).dt.isocalendar().week)['household_kw'].sum()    
    
    # Fully loaded cost per panel = hardware + ($2.50 * panel wattage in W)
    installed_cost_per_panel = brand_specs["cost"] + (brand_specs["wattage"] * 1000 * INSTALLATION_COST_PER_WATT)
    battery_upfront = user_inputs["battery_kwh"] * BATTERY_COST_PER_KWH if user_inputs["include_battery"] else 0
    
    # Calculate how many panels actually fit in the budget
    available_budget = user_inputs["budget"] - INSTALLATION_COST_FIXED - battery_upfront
    max_panels_budget = max(0, int(available_budget / installed_cost_per_panel))
    
    # Cap optimal panels so it NEVER exceeds the budget
    optimal_panels = max(panels_70, min(max_panels_budget, panels_100))
    if optimal_panels > max_panels_budget:
        optimal_panels = max_panels_budget
        
    optimal_gen = optimal_panels * annual_gen_per_panel
    
    # Calculate true net cost for the recommendation
    optimal_gross_cost = INSTALLATION_COST_FIXED + battery_upfront + (optimal_panels * installed_cost_per_panel)
    optimal_net_cost = optimal_gross_cost * (1 - FEDERAL_ITC)
    
    # Pro-rate the highly-accurate 8760 savings to match the recommended panel count
    if num_panels > 0:
        optimal_savings = annual_savings * (optimal_panels / num_panels)
    else:
        optimal_savings = 0

    return {
        "cons_annual": annual_cons, 
        "cons_daily_avg": master_df['household_kw'].sum() / master_df['date'].nunique(), 
        "cons_weekly_avg": weekly_cons.mean(),
        "cons_weekly_max": weekly_cons.max(), 
        "cons_weekly_min": weekly_cons.min(),
        "cons_std_dev": weekly_cons.std(), 
        "cons_cv": weekly_cons.std() / weekly_cons.mean(),
        "cons_iqr": np.percentile(weekly_cons, 75) - np.percentile(weekly_cons, 25),
        "cons_p95": np.percentile(weekly_cons, 95),
        "pt_ratio": weekly_cons.max() / (weekly_cons.min() if weekly_cons.min() > 0 else 1),
        
        "sol_irr_w": master_df["irradiance_w_m2"].mean(), 
        "sol_annual_hrs": annual_sun_hrs,
        "sol_var": master_df["irradiance_w_m2"].var(), 
        "sol_cloudy_freq": (master_df.groupby('date')["irradiance_w_m2"].sum() < 2000).mean(),
        "sol_cv": master_df["irradiance_w_m2"].std() / master_df["irradiance_w_m2"].mean() if master_df["irradiance_w_m2"].mean() > 0 else 0,
        
        "eff_cost": avg_kwh_cost, 
        "ann_spend": annual_cons * avg_kwh_cost,
        "proj_5y_spend": sum(annual_cons * (avg_kwh_cost * ((1+RATE_ESCALATION)**y)) for y in range(5)),
        
        "pv_gen_panel": annual_gen_per_panel, 
        "pv_100": panels_100, "pv_70": panels_70,
        "pv_cost_ea": brand_specs["cost"], 
        "pv_fixed_cost": INSTALLATION_COST_FIXED,
        "pv_breakeven": net_cost / annual_savings if annual_savings > 0 else 0,
        "pv_npv": npv, "pv_irr": irr, "pv_roi": roi,
        
        "night_ratio": master_df[master_df['hour'].isin([20,21,22,23,0,1,2,3,4,5])]['household_kw'].sum() / annual_cons,
        "base_load": master_df['household_kw'].min(),
        "risk_roi_base": roi, "risk_roi_p10": roi * 1.15, "risk_roi_m10": roi * 0.85,
        
        "budget": user_inputs["budget"],
        "max_panels_budget": max_panels_budget, 
        "optimal_panels": optimal_panels,
        "optimal_gen": optimal_gen,
        "optimal_savings": optimal_savings,
        "optimal_payback": optimal_net_cost / optimal_savings if optimal_savings > 0 else 0
    }