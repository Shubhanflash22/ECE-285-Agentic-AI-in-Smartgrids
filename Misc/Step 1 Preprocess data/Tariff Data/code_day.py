#!/usr/bin/env python3
"""
Build DAY-resolution rate tables from a Part-1 "segments" CSV.

Designed for your folder layout:
.
├── TOU-DR/   sdge_tou_dr_segments_2021_2025.csv   output/
├── TOU-DR1/  sdge_tou_dr1_segments_2021_2025.csv  output/
├── TOU-DR2/  sdge_tou_dr2_segments_2021_2025.csv  output/

Examples:
  # Build daily for one scheme:
  python code_day.py --segments TOU-DR/sdge_tou_dr_segments_2021_2025.csv --scheme tou_dr

  # Build daily for all schemes under current dir:
  python code_day.py --all

  # Include per-year CSVs too:
  python code_day.py --all --per-year
"""

import argparse
from pathlib import Path
import pandas as pd


# ---------- Season logic (from SDG&E TOU definition page) ----------
def sdge_season(d: pd.Timestamp) -> str:
    # Summer: Jun 1–Oct 31. Winter: Nov 1–May 31.
    return "summer" if d.month in (6, 7, 8, 9, 10) else "winter"


# ---------- Core expansion ----------
def expand_segments_to_daily(df_seg: pd.DataFrame) -> pd.DataFrame:
    # Normalize column names lightly (strip whitespace)
    df_seg = df_seg.copy()
    df_seg.columns = [c.strip() for c in df_seg.columns]

    # Required columns for SDG&E-style TOU segment CSVs
    required = [
        "start_date", "end_date",
        "summer_on_peak_$/kwh", "summer_off_peak_$/kwh", "summer_super_off_peak_$/kwh",
        "winter_on_peak_$/kwh", "winter_off_peak_$/kwh", "winter_super_off_peak_$/kwh",
    ]
    missing = [c for c in required if c not in df_seg.columns]
    if missing:
        raise ValueError(
            "Segments CSV is missing required columns for this expander:\n"
            f"  missing={missing}\n\n"
            "If this is a different scheme with different columns, either:\n"
            "  (a) rename columns into the expected names, or\n"
            "  (b) extend this script with a scheme-specific mapper."
        )

    # Parse dates
    df_seg["start_date"] = pd.to_datetime(df_seg["start_date"]).dt.normalize()
    df_seg["end_date"] = pd.to_datetime(df_seg["end_date"]).dt.normalize()

    # Identify meta columns (carry through to every daily row)
    seasonal_cols = set(required)
    meta_cols = [c for c in df_seg.columns if c not in seasonal_cols]

    parts = []
    for _, r in df_seg.iterrows():
        days = pd.date_range(r["start_date"], r["end_date"], freq="D")
        part = pd.DataFrame({"date": days})

        # Carry metadata columns
        for c in meta_cols:
            part[c] = r[c]

        # Season and daily TOU rates
        part["season"] = part["date"].apply(sdge_season)

        part["on_peak_$/kwh"] = part["season"].map({
            "summer": r["summer_on_peak_$/kwh"],
            "winter": r["winter_on_peak_$/kwh"],
        })
        part["off_peak_$/kwh"] = part["season"].map({
            "summer": r["summer_off_peak_$/kwh"],
            "winter": r["winter_off_peak_$/kwh"],
        })
        part["super_off_peak_$/kwh"] = part["season"].map({
            "summer": r["summer_super_off_peak_$/kwh"],
            "winter": r["winter_super_off_peak_$/kwh"],
        })

        parts.append(part)

    out = pd.concat(parts, ignore_index=True)

    # Nice column order (keeps unknown meta columns too)
    preferred = [
        "date", "year", "season",
        "on_peak_$/kwh", "off_peak_$/kwh", "super_off_peak_$/kwh",
        "format", "tou_rate_kind", "minimum_bill_$/day", "base_services_charge_$/day",
        "source_pdf", "sheet1_page",
        "start_date", "end_date",  # in case you keep them
    ]
    cols = list(out.columns)
    ordered = [c for c in preferred if c in cols] + [c for c in cols if c not in preferred]
    out = out[ordered].sort_values("date").reset_index(drop=True)

    return out


def write_outputs(df_daily: pd.DataFrame, out_dir: Path, scheme_name: str, per_year: bool):
    out_dir.mkdir(parents=True, exist_ok=True)

    combined_path = out_dir / f"{scheme_name}_daily_2021_2025.csv"
    df_daily.to_csv(combined_path, index=False)
    print(f"Wrote: {combined_path} (rows={len(df_daily)})")

    if per_year and "year" in df_daily.columns:
        for y, g in df_daily.groupby("year", sort=True):
            y = int(y)
            p = out_dir / f"{scheme_name}_daily_{y}.csv"
            g.to_csv(p, index=False)
            print(f"Wrote: {p} (rows={len(g)})")


def infer_scheme_name(segments_path: Path) -> str:
    # Use parent folder name by default (TOU-DR, TOU-DR1, etc.)
    return segments_path.parent.name.lower().replace("-", "_")


def build_one(segments_path: Path, scheme_name: str | None, per_year: bool):
    df_seg = pd.read_csv(segments_path)
    df_daily = expand_segments_to_daily(df_seg)

    if scheme_name is None:
        scheme_name = infer_scheme_name(segments_path)

    out_dir = segments_path.parent / "output"
    write_outputs(df_daily, out_dir, scheme_name, per_year)


def find_all_segments_csvs(root: Path) -> list[Path]:
    # Find any *_segments_2021_2025.csv under immediate subfolders
    return sorted(root.glob("*/sdge_*_segments_2021_2025.csv"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", type=str, help="Path to a segments CSV (Part 1 output)")
    ap.add_argument("--scheme", type=str, default=None, help="Scheme name for output files (default: inferred)")
    ap.add_argument("--per-year", action="store_true", help="Also write year-wise daily CSVs (if `year` column exists)")
    ap.add_argument("--all", action="store_true", help="Process all scheme folders under current directory")
    args = ap.parse_args()

    root = Path(".").resolve()

    if args.all:
        segs = find_all_segments_csvs(root)
        if not segs:
            raise FileNotFoundError(f"No segments CSVs found under {root} matching */sdge_*_segments_2021_2025.csv")
        for p in segs:
            print(f"\n=== Processing: {p} ===")
            build_one(p, scheme_name=None, per_year=args.per_year)
        return

    if not args.segments:
        raise SystemExit("Provide --segments <path> or use --all")

    segments_path = Path(args.segments)
    if not segments_path.exists():
        raise FileNotFoundError(f"Segments CSV not found: {segments_path.resolve()}")

    build_one(segments_path, scheme_name=args.scheme, per_year=args.per_year)


if __name__ == "__main__":
    main()






# """
# Part 2 (DAY resolution)

# Input:  segment CSV produced in Part 1 (e.g., sdge_tou_dr_segments_2021_2025.csv)
# Output: daily CSV (combined and/or year-wise)

# What it does:
# - For each segment row: expands dates from start_date..end_date (inclusive)
# - Assigns season for each day (SDG&E: Summer = Jun 1–Oct 31; Winter = Nov 1–May 31)
# - Picks the correct TOU $/kWh for that day's season:
#     on_peak_$/kwh, off_peak_$/kwh, super_off_peak_$/kwh
# - Carries metadata columns through (format, tou_rate_kind, minimum_bill, base_services_charge, etc.)

# Run examples:
# 1) Combined daily output only:
#    python day_expand.py --in sdge_tou_dr_segments_2021_2025.csv --out sdge_tou_dr_daily_2021_2025.csv

# 2) Combined + year-wise outputs:
#    python day_expand.py --in sdge_tou_dr_segments_2021_2025.csv --out sdge_tou_dr_daily_2021_2025.csv --per-year

# If you’re in this ChatGPT sandbox, your input is likely:
#   /mnt/data/sdge_tou_dr_segments_2021_2025.csv
# """

# import argparse
# from pathlib import Path
# import pandas as pd


# def sdge_season(ts: pd.Timestamp) -> str:
#     # SDG&E TOU seasons (per SDG&E TOU period info): Summer Jun 1–Oct 31, Winter Nov 1–May 31
#     return "summer" if ts.month in (6, 7, 8, 9, 10) else "winter"


# def expand_segments_to_daily(df_seg: pd.DataFrame) -> pd.DataFrame:
#     # Basic validation
#     required = [
#         "year", "start_date", "end_date",
#         "summer_on_peak_$/kwh", "summer_off_peak_$/kwh", "summer_super_off_peak_$/kwh",
#         "winter_on_peak_$/kwh", "winter_off_peak_$/kwh", "winter_super_off_peak_$/kwh",
#     ]
#     missing = [c for c in required if c not in df_seg.columns]
#     if missing:
#         raise ValueError(f"Missing required columns in segments CSV: {missing}")

#     # Parse dates
#     df = df_seg.copy()
#     df["start_date"] = pd.to_datetime(df["start_date"]).dt.normalize()
#     df["end_date"] = pd.to_datetime(df["end_date"]).dt.normalize()

#     # Expand each segment row to daily rows
#     expanded_parts = []
#     for _, r in df.iterrows():
#         days = pd.date_range(r["start_date"], r["end_date"], freq="D")
#         part = pd.DataFrame({"date": days})

#         # Carry through metadata columns (everything except the seasonal rate columns)
#         meta_cols = [c for c in df.columns if c not in (
#             "start_date", "end_date",
#             "summer_on_peak_$/kwh", "summer_off_peak_$/kwh", "summer_super_off_peak_$/kwh",
#             "winter_on_peak_$/kwh", "winter_off_peak_$/kwh", "winter_super_off_peak_$/kwh",
#         )]
#         for c in meta_cols:
#             part[c] = r[c]

#         # Season per day
#         part["season"] = part["date"].apply(sdge_season)

#         # Choose $/kWh values based on season
#         part["on_peak_$/kwh"] = part["season"].map({
#             "summer": r["summer_on_peak_$/kwh"],
#             "winter": r["winter_on_peak_$/kwh"],
#         })
#         part["off_peak_$/kwh"] = part["season"].map({
#             "summer": r["summer_off_peak_$/kwh"],
#             "winter": r["winter_off_peak_$/kwh"],
#         })
#         part["super_off_peak_$/kwh"] = part["season"].map({
#             "summer": r["summer_super_off_peak_$/kwh"],
#             "winter": r["winter_super_off_peak_$/kwh"],
#         })

#         expanded_parts.append(part)

#     out = pd.concat(expanded_parts, ignore_index=True)

#     # Optional: reorder columns nicely
#     preferred_order = [
#         "date", "year", "season",
#         "on_peak_$/kwh", "off_peak_$/kwh", "super_off_peak_$/kwh",
#         # keep these if present
#         "format", "tou_rate_kind", "minimum_bill_$/day", "base_services_charge_$/day",
#         "source_pdf", "sheet1_page",
#         # any other metadata cols will follow
#     ]
#     cols = list(out.columns)
#     ordered = [c for c in preferred_order if c in cols] + [c for c in cols if c not in preferred_order]
#     out = out[ordered].sort_values(["date", "year"]).reset_index(drop=True)

#     return out


# def main():
#     ap = argparse.ArgumentParser()
#     ap.add_argument("--in", dest="inp", required=True, help="Input segments CSV path")
#     ap.add_argument("--out", dest="out", required=True, help="Output combined daily CSV path")
#     ap.add_argument("--per-year", action="store_true", help="Also write year-wise daily CSVs")
#     args = ap.parse_args()

#     inp_path = Path(args.inp)
#     out_path = Path(args.out)

#     df_seg = pd.read_csv(inp_path)
#     df_daily = expand_segments_to_daily(df_seg)

#     df_daily.to_csv(out_path, index=False)
#     print(f"Wrote combined daily CSV: {out_path} (rows={len(df_daily)})")

#     if args.per_year:
#         # Write one CSV per year next to combined output
#         out_dir = out_path.parent
#         for y, g in df_daily.groupby("year", sort=True):
#             p = out_dir / f"sdge_tou_dr_daily_{int(y)}.csv"
#             g.to_csv(p, index=False)
#             print(f"Wrote year-wise daily CSV: {p} (rows={len(g)})")


# if __name__ == "__main__":
#     main()
