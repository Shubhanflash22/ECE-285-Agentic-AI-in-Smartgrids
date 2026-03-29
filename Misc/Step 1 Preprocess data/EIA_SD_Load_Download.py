import requests
import pandas as pd
import time

# --- CONFIGURATION ---
API_KEY = "o7Nz5ZmTXjFdN1i5db5CTsekGlxXErit9BujOQcS"  # <--- PASTE KEY FROM EMAIL HERE
OUTPUT_FILE = "San_Diego_Load_EIA_Fixed.csv"

# CORRECTION: Use the "Sub-BA" Endpoint for SDGE
URL = "https://api.eia.gov/v2/electricity/rto/region-sub-ba-data/data"

params = {
    "api_key": API_KEY,
    "frequency": "hourly",          # Try 'hourly' (UTC) first, it's more robust
    "data[0]": "value",             # Load MW
    "facets[subba][]": "SDGE",      # <--- The correct code for San Diego
    "facets[parent][]": "CISO",     # Parent is California ISO
    "start": "2021-01-01T00",
    "end": "2026-02-07T00",
    "sort[0][column]": "period",
    "sort[0][direction]": "asc",
    "offset": 0,
    "length": 5000 
}

def get_eia_data():
    all_data = []
    print(f"🚀 Starting EIA Download for San Diego (Sub-Region SDGE)...")
    
    current_offset = 0
    
    while True:
        params['offset'] = current_offset
        print(f"   Fetching rows {current_offset}...", end="")
        
        try:
            r = requests.get(URL, params=params)
            
            # Debug: Print raw text if not JSON
            try:
                data = r.json()
            except:
                print(f" ❌ API returned non-JSON: {r.text[:100]}")
                break

            if 'response' in data and 'data' in data['response']:
                rows = data['response']['data']
                
                if not rows:
                    print(" ✅ Done (No more data)")
                    break
                
                df = pd.DataFrame(rows)
                all_data.append(df)
                print(f" ✅ Got {len(df)} rows")
                
                current_offset += 5000
                time.sleep(1)
            else:
                # Print the error if it exists
                if 'error' in data:
                    print(f"\n ❌ API Error: {data['error']}")
                else:
                    print(f"\n ⚠️ Unexpected: {data.keys()}")
                break
                
        except Exception as e:
            print(f" ❌ Script Failed: {e}")
            break

    # --- SAVE ---
    if all_data:
        print("\n📦 Combining files...")
        final_df = pd.concat(all_data, ignore_index=True)
        
        # Clean columns
        cols = ['period', 'subba-name', 'value', 'parent-name']
        # Filter only existing columns
        existing_cols = [c for c in cols if c in final_df.columns]
        final_df = final_df[existing_cols]
        
        final_df.rename(columns={'value': 'MW_Load', 'period': 'Timestamp_UTC'}, inplace=True)
        final_df.to_csv(OUTPUT_FILE, index=False)
        print(f"🎉 DONE! Saved {len(final_df)} hourly records to {OUTPUT_FILE}")
    else:
        print("\n❌ No data collected. Double check your API Key.")

if __name__ == "__main__":
    if "PASTE_YOUR_KEY" in API_KEY:
        print("❌ STOP! You forgot to paste your API Key in line 7.")
    else:
        get_eia_data()