import Back_end_calc

def get_input(prompt: str, default, cast_type):
    val = input(f"{prompt} [Default: {default}]: ").strip()
    return cast_type(val) if val else default

def main():
    print("="*65)
    print(" ADVANCED HOURLY SOLAR FINANCIAL MODELER ")
    print("="*65)
    print("Establish your baseline parameters (Press Enter for defaults):\n")
    
    lat = get_input("1. Latitude", 32.72, float)
    lon = get_input("2. Longitude", -117.16, float)
    s_date = get_input("3. Baseline Start Date (YYYY-MM-DD)", "2023-01-01", str)
    e_date = get_input("4. Baseline End Date (YYYY-MM-DD)", "2023-12-31", str)
    tou = get_input("5. TOU Plan (DR, DR1, DR2)", "DR1", str)
    
    print("\n--- System Design & Hardware ---")
    brands = list(Back_end_calc.SOLAR_PANELS.keys())
    print(f"Available Brands: {', '.join(brands)}")
    brand = get_input("6. Panel Brand", "SunPower Maxeon 3", str)
    num_panels = get_input("7. Number of Panels to simulate", 20, int)
    
    has_batt_str = get_input("8. Include Battery Storage? (y/n)", "n", str).lower()
    has_batt = has_batt_str == 'y'
    batt_kwh = get_input("9. Battery Capacity in kWh", 10.0, float) if has_batt else 0.0
    
    years = get_input("10. Simulation Horizon (Years)", 25, int)
    budget = get_input("11. Total PV Installation Budget ($)", 15000.0, float)

    user_inputs = {
        "latitude": lat, "longitude": lon, "start_date": s_date, "end_date": e_date,
        "tou_plan": tou, "panel_brand": brand, "num_panels": num_panels, 
        "include_battery": has_batt, "battery_kwh": batt_kwh, "years": years, "budget": budget
    }
    
    print("\n" + "="*40)
    print("⚙️ Ingesting regional profile, applying variability factors, and running simulation...")
    print("="*40 + "\n")
    
    try:
        res = Back_end_calc.calculate_metrics(user_inputs)
        
        print("================================================================")
        print(" DETAILED SYSTEM & FINANCIAL SUMMARY ")
        print("================================================================")
        
        print("\n📊 ELECTRICITY CONSUMPTION SUMMARY (From Synthesized Profile)")
        print("────────────────────────────────────────")
        print(f" Annual household consumption    : {res['cons_annual']:,.2f} kWh")
        print(f" Avg daily consumption           : {res['cons_daily_avg']:,.2f} kWh")
        print(f" Avg weekly load                 : {res['cons_weekly_avg']:,.2f} kW")
        print(f" Peak weekly max load            : {res['cons_weekly_max']:,.2f} kW")
        print(f" 95th-percentile weekly avg load : {res['cons_p95']:,.2f} kW")
        print(f" Min weekly min load             : {res['cons_weekly_min']:,.2f} kW")
        print(f" Load std deviation              : {res['cons_std_dev']:,.2f} kW")
        print(f" Coefficient of variation        : {res['cons_cv']:.4f}")
        print(f" Peak-to-trough ratio            : {res['pt_ratio']:.2f}")
        
        print("\n☀️  SOLAR POTENTIAL SUMMARY (Hourly Resolution)")
        print("────────────────────────────────────────")
        print(f" Avg hourly irradiance           : {res['sol_irr_w']:,.2f} W/m²")
        print(f" Est annual sunlight hours       : {res['sol_annual_hrs']:,.2f} hrs")
        print(f" Irradiance variance             : {res['sol_var']:,.2f}")
        print(f" Cloudy-day frequency            : {res['sol_cloudy_freq']*100:.2f}%")
        print(f" Sunlight consistency (CV)       : {res['sol_cv']:.4f}")

        print("\n⚡ PV SIZING & FINANCIAL ANALYSIS")
        print("────────────────────────────────────────")
        print(f" Est annual production / panel   : {res['pv_gen_panel']:.2f} kWh")
        print(f" Panels for 100% offset          : {res['pv_100']}")
        print(f" Panels for 70% offset           : {res['pv_70']}")
        print(f" Panel cost                      : ${res['pv_cost_ea']} / panel")
        print(f" Installation fixed cost         : ${res['pv_fixed_cost']:,}")
        print(f" Break-even                      : {res['pv_breakeven']:.2f} years")
        print(f" NPV ({years} yr)                     : ${res['pv_npv']:,.2f}")
        print(f" IRR                             : {res['pv_irr']*100:.2f}%")
        print(f" ROI ({years} yr)                     : {res['pv_roi']*100:.2f}%")

        print("\n================================================================")
        print(" OPTIMAL PV PANEL RECOMMENDATION FOR THE HOUSEHOLD")
        print("================================================================")
        
        print("\n### Task 1 & 2: Key Trends, Seasonal Patterns, and Anomalies")
        print("Based on the data summary:")
        print(f"* Annual Electricity Consumption: The dynamically generated profile shows {res['cons_annual']:,.0f} kWh per year.")
        print(f"* Peak Weekly Max Load: The peak weekly max load is {res['cons_weekly_max']:.2f} kW, dictating our inverter sizing limits.")
        print(f"* 95th-Percentile Weekly Avg Load: The 95th-percentile weekly avg load is {res['cons_p95']:.2f} kW.")
        
        print("\n### Task 3: Household Budget")
        print(f"* PV Installation Budget: ${res['budget']:,.2f} USD")

        

        print("\n### Task 4: Maximum Number of Panels Affordable Within the Budget")
        print("To determine the maximum number of panels affordable within the budget:")
        print(f"* Est Annual Production / Panel: {res['pv_gen_panel']:.2f} kWh")
        print(f"* Panels for 100% Offset: {res['pv_100']}")
        print(f"* Maximum Number of Panels Within Budget: Using the estimated hardware cost per panel (${res['pv_cost_ea']}) and the budget (${res['budget']:,.0f}), the maximum number of panels is: {res['max_panels_budget']} panels.")

        print("\n### Task 5: Optimal Number of PV Panels")
        print(f"* Panels for 70% Offset: {res['pv_70']}")
        print(f"* Optimal Number of PV Panels: Considering the hourly load curve and budget constraints, it is recommended to install at least {res['optimal_panels']} panels.")

        print("\n### Task 6: Cost Savings and Payback Period")
        print(f"* Annual Production (at {res['optimal_panels']} panels): {res['optimal_gen']:,.2f} kWh")
        print(f"* Annual Savings: ${res['optimal_savings']:,.2f}")
        print(f"* Payback Period: Approximately {res['optimal_payback']:.2f} years")

        print("\n### Task 7: Risks and Battery Storage Considerations")
        print("* Sunlight Variability: The household's sunlight consistency coefficient of variation is {:.4f}.".format(res['sol_cv']))
        print(f"* Grid Dependency: The household's nighttime/off-sun load ratio is {res['night_ratio']*100:.2f}%.")
        print("A battery is heavily advised to absorb noon-time clipping and strictly discharge during the 4 PM to 9 PM TOU peak window.")

        

        print("\n## RECOMMENDATION")
        print(f"* Optimal Number of PV Panels: {res['optimal_panels']}")
        print(f"* Expected Annual Production: {res['optimal_gen']:,.2f} kWh")
        print(f"* Cost Savings: ${res['optimal_savings']:,.2f} per year")
        print(f"* Payback Period: Approximately {res['optimal_payback']:.2f} years")
        print(f"* ROI ({years} yr): {res['pv_roi']*100:.2f}%")
        print("\n================================================================")
            
    except Exception as e:
        print(f"\nError occurred: {e}")

if __name__ == "__main__":
    main()