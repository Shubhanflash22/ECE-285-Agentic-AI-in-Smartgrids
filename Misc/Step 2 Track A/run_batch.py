"""
run_batch.py – Run the full LLM workflow across all 30 San Diego locations.
==========================================================================

Reads data/lats_longs_san_diego.csv, and for each row:
  1. Overwrites config lat/lon → regenerates weather & household CSVs
  2. Runs feature engineering + RAG + LLM
  3. Saves  batch_outputs/{name}_output.txt
            batch_outputs/{name}_feature_outputs.txt

Usage:
    python run_batch.py                        # uses config.yaml
    python run_batch.py --config config.yaml   # explicit config
    python run_batch.py --dry-run              # skip LLM, just extract + features
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import time
from copy import deepcopy
from pathlib import Path

import yaml
from tqdm import tqdm

from config import WorkflowConfig
from pipeline import Pipeline

# ─── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,          # keep quiet – tqdm shows progress
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_batch")


# ─── Helpers ──────────────────────────────────────────────────

LOCATIONS_CSV = Path("data/lats_longs_san_diego.csv")
OUTPUT_DIR    = Path("batch_outputs")


def sanitise_name(name: str) -> str:
    """Turn a location name into a safe filename fragment.
    e.g. 'Casa de Oro-Mount Helix' → 'Casa_de_Oro-Mount_Helix'
    """
    return re.sub(r"[^\w\-]", "_", name).strip("_")


def load_locations(csv_path: Path = LOCATIONS_CSV) -> list[dict]:
    """Return a list of {name, latitude, longitude} dicts."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append({
                "name": row["name"].strip(),
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
            })
    return rows


def load_base_config(yaml_path: str = "config.yaml") -> WorkflowConfig:
    with open(yaml_path) as f:
        raw = yaml.safe_load(f)
    return WorkflowConfig.from_dict(raw)


# ─── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Batch-run LLM workflow over 30 locations")
    parser.add_argument("--config", default="config.yaml", help="Base YAML config")
    parser.add_argument("--locations", default=str(LOCATIONS_CSV), help="CSV with name,latitude,longitude")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Folder for all outputs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run data extraction + features only (skip LLM)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    locations = load_locations(Path(args.locations))
    base_cfg  = load_base_config(args.config)

    print(f"\n{'═' * 60}")
    print(f"  BATCH RUN – {len(locations)} locations")
    print(f"  Backend : {base_cfg.backend}  |  Model: {base_cfg.model}")
    print(f"  Outputs → {output_dir.resolve()}")
    print(f"{'═' * 60}\n")

    successes = []
    failures  = []

    pbar = tqdm(locations, desc="Locations", unit="loc", ncols=90, colour="green")

    for loc in pbar:
        name = loc["name"]
        safe = sanitise_name(name)
        lat  = loc["latitude"]
        lon  = loc["longitude"]

        pbar.set_postfix_str(f"{name} ({lat:.4f}, {lon:.4f})")

        # ── Build a per-location config (deep-copy to be safe) ──
        cfg = deepcopy(base_cfg)
        cfg.fe_latitude  = lat
        cfg.fe_longitude = lon
        cfg.output_path         = str(output_dir / f"{safe}_output.txt")
        cfg.feature_output_path = str(output_dir / f"{safe}_feature_outputs.txt")

        try:
            t0 = time.perf_counter()

            if args.dry_run:
                # Only run Steps 0 + 1 (data extraction + feature eng.)
                from data_extractor import regenerate_all
                from feature_engineering import extract_all_features, format_for_llm
                import pandas as pd

                regenerate_all(
                    latitude=lat, longitude=lon,
                    weather_csv=cfg.weather_csv,
                    household_csv=cfg.household_csv,
                    electricity_csv=cfg.electricity_csv,
                )
                df_e = pd.read_csv(cfg.electricity_csv)
                df_h = pd.read_csv(cfg.household_csv)
                df_w = pd.read_csv(cfg.weather_csv)
                feats = extract_all_features(
                    df_e, df_w, df_h,
                    num_panels=cfg.fe_num_panels,
                    occupants=cfg.fe_occupants,
                    house_sqm=cfg.fe_house_sqm,
                    price_per_kwh=cfg.fe_price_per_kwh,
                    num_evs=cfg.fe_num_evs,
                    pv_budget=cfg.fe_pv_budget,
                )
                feat_text = format_for_llm(feats)
                fe_out = Path(cfg.feature_output_path)
                fe_out.parent.mkdir(parents=True, exist_ok=True)
                fe_out.write_text(feat_text, encoding="utf-8")
                result = "[dry-run] LLM skipped"
            else:
                pipeline = Pipeline(cfg)
                result = pipeline.run()

            elapsed = time.perf_counter() - t0

            # ── Save output ──
            out = Path(cfg.output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(result, encoding="utf-8")

            successes.append((name, elapsed))

        except Exception as exc:
            failures.append((name, str(exc)))
            tqdm.write(f"  ✗ {name}: {exc}")

    # ─── Summary ──────────────────────────────────────────────
    print(f"\n{'═' * 60}")
    print(f"  BATCH COMPLETE")
    print(f"  Succeeded : {len(successes)} / {len(locations)}")
    if failures:
        print(f"  Failed    : {len(failures)}")
    print(f"{'═' * 60}")

    if successes:
        total_time = sum(t for _, t in successes)
        avg_time   = total_time / len(successes)
        print(f"\n  Total time : {total_time:.1f}s")
        print(f"  Avg / loc  : {avg_time:.1f}s")

    if failures:
        print(f"\n  Failed locations:")
        for name, err in failures:
            print(f"    • {name}: {err}")

    print(f"\n  All outputs saved in: {output_dir.resolve()}\n")


if __name__ == "__main__":
    main()
