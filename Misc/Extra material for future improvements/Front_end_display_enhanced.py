"""
═══════════════════════════════════════════════════════════════════════════════
RESIDENTIAL SOLAR PV FINANCIAL ANALYZER - INTERACTIVE FRONTEND
═══════════════════════════════════════════════════════════════════════════════

Interactive terminal interface for residential solar photovoltaic system
investment analysis. Provides guided input collection and formatted output
of techno-economic analysis results.

Features:
    - Intelligent default values for San Diego region
    - Input validation and error handling
    - Rich formatting with visual separators
    - Comprehensive results dashboard
    - Export capabilities (JSON, CSV)

Usage:
    python Front_end_display_enhanced.py

Author: Enhanced Solar Modeling Framework
Date: 2025-02-27
Version: 2.0 (Journal-Quality Release)
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from datetime import datetime
from solar_cost_model_enhanced import RoofType, EquipmentTier

import Back_end_calc_enhanced as backend

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Default values (San Diego Downtown)
DEFAULTS = {
    "latitude": 32.7157,
    "longitude": -117.1611,
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "tou_plan": "DR1",
    "panel_brand": "SunPower Maxeon 3",
    "num_panels": 20,
    "include_battery": False,
    "battery_kwh": 13.5,
    "years": 25,
    "budget": 25000.0,
}

# Enable results export
ENABLE_EXPORT = True
EXPORT_DIR = Path("./simulation_results")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def print_header(title: str, width: int = 80, char: str = "=") -> None:
    """Print formatted section header.
    
    Args:
        title: Header text
        width: Total width of header
        char: Character for border
    """
    print(f"\n{char * width}")
    print(f" {title.upper()}")
    print(f"{char * width}\n")


def print_subheader(title: str, width: int = 80) -> None:
    """Print formatted subsection header.
    
    Args:
        title: Subheader text
        width: Total width
    """
    print(f"\n{'─' * width}")
    print(f"  {title}")
    print(f"{'─' * width}")


def get_input(
    prompt: str,
    default: Any,
    cast_type: Callable,
    validator: Optional[Callable[[Any], bool]] = None,
) -> Any:
    """Get validated user input with default value.
    
    Args:
        prompt: Input prompt text
        default: Default value if user presses Enter
        cast_type: Function to cast input (e.g., float, int, str)
        validator: Optional validation function
    
    Returns:
        Validated input value
    """
    while True:
        try:
            raw_input = input(f"{prompt} [Default: {default}]: ").strip()
            
            if not raw_input:
                value = default
            else:
                value = cast_type(raw_input)
            
            # Validate if validator provided
            if validator and not validator(value):
                print(f"  ❌ Invalid input. Please try again.")
                continue
            
            return value
        
        except ValueError as e:
            print(f"  ❌ Invalid format: {e}. Please try again.")
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user. Exiting...")
            sys.exit(0)


def validate_latitude(lat: float) -> bool:
    """Validate latitude is within San Diego bounds."""
    return backend.RegionalConstants.LAT_MIN <= lat <= backend.RegionalConstants.LAT_MAX


def validate_longitude(lon: float) -> bool:
    """Validate longitude is within San Diego bounds."""
    return backend.RegionalConstants.LON_MIN <= lon <= backend.RegionalConstants.LON_MAX


def validate_date(date_str: str) -> bool:
    """Validate date string is in YYYY-MM-DD format."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_positive(value: float) -> bool:
    """Validate value is positive."""
    return value > 0


# ═══════════════════════════════════════════════════════════════════════════════
# INPUT COLLECTION
# ═══════════════════════════════════════════════════════════════════════════════

def collect_inputs() -> Dict[str, Any]:
    """Interactive input collection workflow.
    
    Returns:
        Dictionary of user inputs
    """
    print_header("ADVANCED HOURLY SOLAR FINANCIAL MODELER", char="═")
    
    print("""
Welcome to the Residential Solar PV Investment Analysis Tool.

This simulator will help you evaluate the financial viability of installing
a solar photovoltaic system with optional battery storage for your home.

We'll guide you through entering your location, preferences, and constraints.
Press Enter to accept default values, or type your own.

Let's begin!
    """)
    
    # Location
    print_subheader("📍 LOCATION")
    print("Specify the geographic coordinates of your property.")
    print("(San Diego County range: Lat 32.53-33.22, Lon -117.26 to -116.90)\n")
    
    lat = get_input(
        "  Latitude (decimal degrees)",
        DEFAULTS["latitude"],
        float,
        validate_latitude
    )
    
    lon = get_input(
        "  Longitude (decimal degrees, negative for West)",
        DEFAULTS["longitude"],
        float,
        validate_longitude
    )
    
    # Date range
    print_subheader("📅 SIMULATION PERIOD")
    print("Specify the date range for baseline data (hourly resolution).")
    print("Recommendation: Use a full calendar year (e.g., 2023-01-01 to 2023-12-31)\n")
    
    start_date = get_input(
        "  Start Date (YYYY-MM-DD)",
        DEFAULTS["start_date"],
        str,
        validate_date
    )
    
    end_date = get_input(
        "  End Date (YYYY-MM-DD)",
        DEFAULTS["end_date"],
        str,
        validate_date
    )
    
    # Tariff plan
    print_subheader("⚡ UTILITY TARIFF PLAN")
    print("SDG&E offers multiple Time-of-Use (TOU) rate schedules:")
    print("  • DR  : Basic TOU plan")
    print("  • DR1 : EV-friendly TOU plan (recommended for EV owners)")
    print("  • DR2 : Alternative TOU structure\n")
    
    tou_plan = get_input(
        "  TOU Plan (DR, DR1, or DR2)",
        DEFAULTS["tou_plan"],
        lambda x: x.upper(),
        lambda x: x in ["DR", "DR1", "DR2"]
    )
    
    # Panel selection
    print_subheader("☀️  SOLAR PANEL SELECTION")
    print("Available panel brands and models:")
    
    for i, (brand, spec) in enumerate(backend.SOLAR_PANELS.items(), 1):
        print(f"  {i}. {brand}")
        print(f"     └─ {spec.wattage*1000:.0f}W, {spec.efficiency*100:.1f}% efficient, ${spec.cost}/panel")
    
    print()
    
    brands_list = list(backend.SOLAR_PANELS.keys())
    default_idx = brands_list.index(DEFAULTS["panel_brand"]) + 1
    
    brand_idx = get_input(
        f"  Select panel (1-{len(brands_list)})",
        default_idx,
        int,
        lambda x: 1 <= x <= len(brands_list)
    )
    
    panel_brand = brands_list[brand_idx - 1]
    
    num_panels = get_input(
        "  Number of panels to simulate",
        DEFAULTS["num_panels"],
        int,
        validate_positive
    )
    
    # Battery storage
    print_subheader("🔋 BATTERY STORAGE")
    print("Battery storage enables:")
    print("  • Peak demand shaving (discharge during expensive on-peak hours)")
    print("  • Backup power during outages")
    print("  • Maximized solar self-consumption\n")
    
    has_batt_str = get_input(
        "  Include battery storage? (y/n)",
        "n" if not DEFAULTS["include_battery"] else "y",
        lambda x: x.lower(),
        lambda x: x in ["y", "n", "yes", "no"]
    )
    
    include_battery = has_batt_str in ["y", "yes"]
    
    if include_battery:
        print("\n  Available battery systems:")
        for bat_name, bat_spec in backend.BATTERY_SYSTEMS.items():
            if bat_name == "None":
                continue
            print(f"    • {bat_name}: {bat_spec.capacity_kwh} kWh, ${bat_spec.cost:,}")
        print()
        
        battery_kwh = get_input(
            "  Battery capacity (kWh)",
            DEFAULTS["battery_kwh"],
            float,
            validate_positive
        )
    else:
        battery_kwh = 0.0
    
    # Financial parameters
    print_subheader("💰 FINANCIAL PARAMETERS")
    
    years = get_input(
        "  Planning horizon (years)",
        DEFAULTS["years"],
        int,
        lambda x: 5 <= x <= 30
    )
    
    budget = get_input(
        "  Total available budget ($)",
        DEFAULTS["budget"],
        float,
        validate_positive
    )

    roof_type_map = {
    1: RoofType.COMPOSITION_SHINGLE,
    2: RoofType.TILE_FLAT,
    3: RoofType.TILE_SPANISH,
    4: RoofType.METAL_STANDING_SEAM,
    }
    tier_map = {
        1: EquipmentTier.ECONOMY,
        2: EquipmentTier.STANDARD,
        3: EquipmentTier.PREMIUM,
        4: EquipmentTier.LUXURY,
    }
    # Roof type
    roof_types = {
        1: "Composition Shingle (most common)",
        2: "Flat Tile", 
        3: "Spanish/Barrel Tile",
        4: "Metal Standing Seam"
    }
    for k, v in roof_types.items():
        print(f"  {k}. {v}")
    roof_choice = get_input("Roof Type (1-4)", 1, int, lambda x: 1 <= x <= 4)

    # Stories
    story_count = get_input("Number of stories", 1, int, lambda x: 1 <= x <= 4)

    # Equipment tier
    tiers = {1: "Economy", 2: "Standard", 3: "Premium", 4: "Luxury"}
    for k, v in tiers.items():
        print(f"  {k}. {v}")
    tier_choice = get_input("Equipment Tier (1-4)", 2, int, lambda x: 1 <= x <= 4)

    # Add to user_inputs dict
    user_inputs["roof_type"] = roof_type_map[roof_choice]
    user_inputs["story_count"] = story_count
    user_inputs["equipment_tier"] = tier_map[tier_choice]
    
    # Summary confirmation
    print_header("INPUT SUMMARY", char="─")
    print(f"""
Location:        ({lat:.4f}, {lon:.4f})
Date Range:      {start_date} to {end_date}
Tariff Plan:     SDG&E TOU-{tou_plan}
Solar Panels:    {num_panels}x {panel_brand}
Battery:         {"Yes" if include_battery else "No"}{f" ({battery_kwh} kWh)" if include_battery else ""}
Horizon:         {years} years
Budget:          ${budget:,.2f}
    """)
    
    confirm = input("\nProceed with simulation? (y/n) [y]: ").strip().lower()
    
    if confirm and confirm not in ["y", "yes"]:
        print("\n⚠️  Simulation cancelled by user.")
        sys.exit(0)
    
    return {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "tou_plan": tou_plan,
        "panel_brand": panel_brand,
        "num_panels": num_panels,
        "include_battery": include_battery,
        "battery_kwh": battery_kwh,
        "years": years,
        "budget": budget,
        "roof_type":roof_type,
        "story_count":story_count,
        "equipment_tier":equipment_tier
    }


# ═══════════════════════════════════════════════════════════════════════════════
# RESULTS DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

def display_results(results: Dict[str, float], inputs: Dict[str, Any]) -> None:
    """Display comprehensive results dashboard.
    
    Args:
        results: Dictionary of calculated metrics
        inputs: Original user inputs
    """
    print_header("COMPREHENSIVE TECHNO-ECONOMIC ANALYSIS RESULTS", char="═")
    
    # Electricity consumption
    print_subheader("📊 HOUSEHOLD ELECTRICITY CONSUMPTION PROFILE")
    print(f"  Based on location ({inputs['latitude']:.4f}, {inputs['longitude']:.4f})")
    print(f"  Data period: {inputs['start_date']} to {inputs['end_date']}\n")
    
    print(f"  Annual Consumption:            {results['cons_annual']:>12,.0f} kWh")
    print(f"  Daily Average:                 {results['cons_daily_avg']:>12,.2f} kWh/day")
    print(f"  Weekly Average Load:           {results['cons_weekly_avg']:>12,.2f} kW")
    print(f"  Weekly Peak Load:              {results['cons_weekly_max']:>12,.2f} kW")
    print(f"  Weekly Minimum Load:           {results['cons_weekly_min']:>12,.2f} kW")
    print(f"  Load Standard Deviation:       {results['cons_std_dev']:>12,.2f} kW")
    print(f"  Coefficient of Variation:      {results['cons_cv']:>12,.4f}")
    print(f"  Peak-to-Trough Ratio:          {results['pt_ratio']:>12,.2f}x")
    print(f"  95th Percentile Weekly Load:   {results['cons_p95']:>12,.2f} kW")
    
    # Solar potential
    print_subheader("☀️  SOLAR RESOURCE ASSESSMENT")
    print(f"  Average Hourly Irradiance:     {results['sol_irr_w']:>12,.0f} W/m²")
    print(f"  Annual Sunlight Hours:         {results['sol_annual_hrs']:>12,.0f} hours")
    print(f"  Irradiance Variance:           {results['sol_var']:>12,.0f} (W/m²)²")
    print(f"  Cloudy Day Frequency:          {results['sol_cloudy_freq']*100:>12,.1f} %")
    print(f"  Solar Consistency (CV):        {results['sol_cv']:>12,.4f}")
    
    # System specifications
    print_subheader("⚡ SIMULATED PV SYSTEM SPECIFICATIONS")
    panel_spec = backend.SOLAR_PANELS[inputs['panel_brand']]
    system_dc_kw = inputs['num_panels'] * panel_spec.wattage
    system_ac_kw = system_dc_kw / backend.DEFAULT_SYSTEM.dc_ac_ratio
    
    print(f"  Panel Model:                   {inputs['panel_brand']}")
    print(f"  Panel Specifications:          {panel_spec.wattage*1000:.0f}W, {panel_spec.efficiency*100:.1f}% efficient")
    print(f"  Number of Panels:              {inputs['num_panels']}")
    print(f"  System DC Capacity:            {system_dc_kw:>12,.2f} kW")
    print(f"  System AC Capacity:            {system_ac_kw:>12,.2f} kW (inverter)")
    print(f"  DC/AC Ratio:                   {backend.DEFAULT_SYSTEM.dc_ac_ratio:>12,.2f}")
    
    if inputs['include_battery']:
        print(f"\n  Battery Storage:               {inputs['battery_kwh']:>12,.1f} kWh")
        print(f"  Round-Trip Efficiency:         {backend.BATTERY_SYSTEMS['Tesla Powerwall 3'].round_trip_efficiency*100:>12,.1f} %")
    else:
        print(f"\n  Battery Storage:               {'None':>12}")
    
    # Production metrics
    print_subheader("🔆 SOLAR PRODUCTION METRICS")
    print(f"  Annual Generation (Year 1):    {results['pv_gen_panel'] * inputs['num_panels']:>12,.0f} kWh")
    print(f"  Generation per Panel:          {results['pv_gen_panel']:>12,.0f} kWh/panel/year")
    print(f"  System Capacity Factor:        {(results['pv_gen_panel'] * inputs['num_panels']) / (system_dc_kw * 8760) * 100:>12,.1f} %")
    print(f"  Annual Degradation:            {panel_spec.degradation_rate*100:>12,.2f} %/year")
    
    # Sizing recommendations
    print_subheader("📐 SYSTEM SIZING RECOMMENDATIONS")
    print(f"  Panels for 100% Offset:        {results['pv_100']:>12} panels")
    print(f"  Panels for 70% Offset:         {results['pv_70']:>12} panels")
    print(f"  Max Panels Within Budget:      {results['max_panels_budget']:>12} panels")
    print(f"  → OPTIMAL RECOMMENDATION:      {results['optimal_panels']:>12} panels")
    
    # Financial analysis
    print_subheader("💰 FINANCIAL ANALYSIS")
    
    # Costs
    gross_cost = (
        inputs['num_panels'] * panel_spec.cost
        + backend.DEFAULT_ECONOMICS.installation_fixed
        + system_dc_kw * 1000 * backend.DEFAULT_ECONOMICS.installation_per_watt
    )
    if inputs['include_battery']:
        gross_cost += inputs['battery_kwh'] * backend.DEFAULT_ECONOMICS.ca_sgip_per_kwh
    
    net_cost = gross_cost * (1 - backend.DEFAULT_ECONOMICS.federal_itc)
    
    print(f"  Gross System Cost:             ${gross_cost:>12,.2f}")
    print(f"  Federal Tax Credit (30%):      ${gross_cost * backend.DEFAULT_ECONOMICS.federal_itc:>12,.2f}")
    print(f"  Net System Cost:               ${net_cost:>12,.2f}")
    print(f"\n  Hardware Cost per Panel:       ${panel_spec.cost:>12,.2f}")
    print(f"  Installation ($/W):            ${backend.DEFAULT_ECONOMICS.installation_per_watt:>12,.2f}")
    print(f"  Fixed Installation Cost:       ${backend.DEFAULT_ECONOMICS.installation_fixed:>12,.2f}")
    
    # Returns
    print(f"\n  Net Present Value ({inputs['years']} yr): ${results['pv_npv']:>12,.2f}")
    print(f"  Internal Rate of Return:       {results['pv_irr']*100:>12,.2f} %")
    print(f"  Return on Investment:          {results['pv_roi']*100:>12,.2f} %")
    print(f"  Simple Payback Period:         {results['pv_breakeven']:>12,.1f} years")
    
    # Optimal system financials
    print_subheader("🎯 OPTIMAL SYSTEM FINANCIAL PROJECTION")
    print(f"  Recommended Panels:            {results['optimal_panels']:>12} panels")
    print(f"  Expected Annual Generation:    {results['optimal_gen']:>12,.0f} kWh")
    print(f"  Annual Electricity Savings:    ${results['optimal_savings']:>12,.2f}")
    print(f"  Optimal Payback Period:        {results['optimal_payback']:>12,.1f} years")
    
    # Risk assessment
    print_subheader("⚠️  RISK FACTORS & CONSIDERATIONS")
    print(f"  Nighttime Load Dependency:     {results['night_ratio']*100:>12,.1f} %")
    print(f"  Base Load (Minimum):           {results['base_load']:>12,.2f} kW")
    print(f"  Solar Consistency:             {results['sol_cv']:>12,.4f} (lower is better)")
    print(f"\n  Scenario Analysis (ROI):")
    print(f"    Base Case:                   {results['risk_roi_base']*100:>12,.1f} %")
    print(f"    Optimistic (+15%):           {results['risk_roi_p10']*100:>12,.1f} %")
    print(f"    Conservative (-15%):         {results['risk_roi_m10']*100:>12,.1f} %")
    
    # Executive summary
    print_header("EXECUTIVE RECOMMENDATION", char="═")
    
    if results['pv_npv'] > 0:
        verdict = "✅ FINANCIALLY VIABLE"
        color = "\033[92m"  # Green
    elif results['pv_npv'] > -5000:
        verdict = "⚠️  MARGINAL"
        color = "\033[93m"  # Yellow
    else:
        verdict = "❌ NOT RECOMMENDED"
        color = "\033[91m"  # Red
    
    reset = "\033[0m"
    
    print(f"{color}{verdict}{reset}\n")
    
    print(f"Based on the comprehensive analysis for your location at")
    print(f"({inputs['latitude']:.4f}, {inputs['longitude']:.4f}):\n")
    
    print(f"• Install {results['optimal_panels']} {inputs['panel_brand']} panels")
    print(f"  (Total system: {results['optimal_panels'] * panel_spec.wattage:.1f} kW DC)")
    
    if inputs['include_battery']:
        print(f"• Include {inputs['battery_kwh']} kWh battery storage")
    else:
        print(f"• Consider adding battery storage for optimal TOU arbitrage")
    
    print(f"\n• Expected annual generation: {results['optimal_gen']:,.0f} kWh")
    print(f"• Annual electricity savings: ${results['optimal_savings']:,.2f}")
    print(f"• Net system cost: ${net_cost:,.2f}")
    print(f"• Payback period: {results['optimal_payback']:.1f} years")
    print(f"• {inputs['years']}-year NPV: ${results['pv_npv']:,.2f}")
    print(f"• Internal rate of return: {results['pv_irr']*100:.1f}%")
    
    print(f"\n{'─'*80}")
    
    print(f"\nKey insights:")
    
    if results['night_ratio'] > 0.40:
        print(f"• High nighttime consumption ({results['night_ratio']*100:.0f}%) suggests")
        print(f"  battery storage would significantly improve financial returns.")
    
    if results['sol_cv'] < 0.5:
        print(f"• Excellent solar consistency (CV={results['sol_cv']:.3f}) at this location.")
    elif results['sol_cv'] > 0.7:
        print(f"• Moderate solar variability (CV={results['sol_cv']:.3f}). Consider")
        print(f"  conservative sizing or battery backup.")
    
    if results['optimal_payback'] < 8:
        print(f"• Rapid payback ({results['optimal_payback']:.1f} years) makes this")
        print(f"  an attractive investment.")
    elif results['optimal_payback'] > 12:
        print(f"• Extended payback ({results['optimal_payback']:.1f} years). Review")
        print(f"  assumptions and consider waiting for cost reductions.")
    
    print()


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORT FUNCTIONALITY
# ═══════════════════════════════════════════════════════════════════════════════

def export_results(results: Dict, inputs: Dict) -> None:
    """Export results to JSON and CSV files.
    
    Args:
        results: Calculated metrics
        inputs: User inputs
    """
    if not ENABLE_EXPORT:
        return
    
    # Create export directory
    EXPORT_DIR.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON export (full data)
    json_path = EXPORT_DIR / f"simulation_{timestamp}.json"
    export_data = {
        "timestamp": timestamp,
        "inputs": inputs,
        "results": results,
    }
    
    with open(json_path, 'w') as f:
        json.dump(export_data, f, indent=2, default=str)
    
    logger.info(f"Results exported to: {json_path}")
    
    # CSV export (key metrics only)
    csv_path = EXPORT_DIR / f"simulation_{timestamp}.csv"
    
    with open(csv_path, 'w') as f:
        f.write("Metric,Value,Unit\n")
        
        # Selected metrics
        metrics = [
            ("Annual Consumption", results['cons_annual'], "kWh"),
            ("Optimal Panels", results['optimal_panels'], "panels"),
            ("System DC Capacity", inputs['num_panels'] * backend.SOLAR_PANELS[inputs['panel_brand']].wattage, "kW"),
            ("Annual Generation", results['optimal_gen'], "kWh"),
            ("Annual Savings", results['optimal_savings'], "USD"),
            ("NPV", results['pv_npv'], "USD"),
            ("IRR", results['pv_irr'] * 100, "%"),
            ("Payback", results['optimal_payback'], "years"),
        ]
        
        for metric, value, unit in metrics:
            f.write(f"{metric},{value:.2f},{unit}\n")
    
    logger.info(f"Summary exported to: {csv_path}")
    
    print(f"\n✅ Results exported to: {EXPORT_DIR}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Main execution flow."""
    try:
        # Collect inputs
        user_inputs = collect_inputs()
        
        # Run simulation
        print_header("RUNNING SIMULATION", char="═")
        print("⚙️  Fetching weather data...")
        print("⚙️  Generating household load profile...")
        print("⚙️  Calculating solar production...")
        print("⚙️  Simulating battery dispatch...")
        print("⚙️  Computing financial metrics...\n")
        
        results = backend.calculate_metrics(user_inputs)
        
        print("✅ Simulation complete!\n")
        
        # Display results
        display_results(results, user_inputs)
        
        # Export
        if ENABLE_EXPORT:
            export_results(results, user_inputs)
        
        print_header("SESSION COMPLETE", char="═")
        print("Thank you for using the Solar PV Financial Analyzer.")
        print("For questions or issues, please refer to the documentation.\n")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Exiting...")
        sys.exit(0)
    
    except Exception as e:
        logger.error(f"Simulation failed: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        print("Please check your inputs and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
