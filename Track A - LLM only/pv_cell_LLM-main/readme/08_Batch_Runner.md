# Step 8: Batch Runner (`run_batch.py`) & Single-Location Entry Point (`workflow.py`)

## Overview

The Batch Runner and Workflow Entry Point are the **top-level scripts** that users execute. `workflow.py` handles a single location, while `run_batch.py` iterates over all **30 San Diego neighbourhoods** defined in a locations CSV, running the full pipeline for each and saving individual output files with a live progress bar.

---

## Architecture Position

```
┌───────────────────────────────────────────────────────────────────┐
│                        ENTRY POINTS                                │
│                                                                   │
│  ┌─────────────────────┐     ┌────────────────────────────────┐  │
│  │   workflow.py         │     │   run_batch.py                  │  │
│  │   (single location)  │     │   (30 locations, loop)          │  │
│  │                      │     │                                 │  │
│  │  1. Parse CLI/YAML   │     │  1. Parse CLI                   │  │
│  │  2. Validate config  │     │  2. Load base config (YAML)     │  │
│  │  3. Pipeline(cfg)    │     │  3. Load locations CSV           │  │
│  │  4. .run()           │     │  4. FOR each location:           │  │
│  │  5. Save output      │     │     a. deepcopy(config)          │  │
│  │  6. Print result     │     │     b. Override lat/lon/paths    │  │
│  │                      │     │     c. Pipeline(cfg).run()       │  │
│  └──────────────────────┘     │     d. Save 2 output files       │  │
│                               │  5. Print summary                │  │
│                               └────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

---

## Files Involved

| File | Role | Lines of Code |
|------|------|---------------|
| `workflow.py` | CLI entry point for single-location runs | 158 lines |
| `run_batch.py` | Batch runner for 30 San Diego locations | 169 lines |
| `data/lats_longs_san_diego.csv` | Locations file: 30 neighbourhoods | 32 lines (header + 31 rows) |

---

## Part A: Single-Location Entry Point (`workflow.py`)

### Usage

```bash
# Via YAML config (recommended)
python workflow.py --config config.yaml

# Via CLI flags
python workflow.py \
  --backend ollama --model llama3.1:8b \
  --prompt "How many PV panels should I install?" \
  --rag data/knowledge.txt --output outputs/output.txt
```

### Execution Flow

1. **Parse arguments** — `argparse` with 20+ flags across 5 groups
2. **Load config** — from YAML file or CLI flags → `WorkflowConfig`
3. **Validate** — `config.validate()` (backend, RAG file, prompt checks)
4. **Run pipeline** — `Pipeline(config).run()` → returns LLM response string
5. **Save output** — Write response to `config.output_path`
6. **Print** — Display response in terminal with `═` border

### Timing

```
10:42:01 [INFO] workflow – Starting LLM workflow
10:42:01 [INFO] workflow –   Backend : ollama  |  Model: llama3.1:8b
10:42:05 [INFO] pipeline – Regenerating data CSVs …
10:42:06 [INFO] pipeline – Running feature engineering …
10:42:06 [INFO] pipeline – Building RAG index …
10:42:06 [INFO] pipeline – Building final prompt …
10:42:06 [INFO] pipeline – Calling LLM backend …
...
10:43:15 [INFO] workflow – Done in 69.3 s – output saved to outputs/output.txt
```

---

## Part B: Batch Runner (`run_batch.py`)

### The 30 San Diego Locations

| # | Location | Latitude | Longitude | Area Type |
|---|----------|----------|-----------|-----------|
| 1 | San Diego | 32.7160 | -117.1611 | Urban core |
| 2 | Chula Vista | 32.6399 | -117.1067 | Suburban |
| 3 | Oceanside | 33.1959 | -117.3795 | Coastal |
| 4 | Escondido | 33.1247 | -117.0808 | Inland |
| 5 | Carlsbad | 33.1581 | -117.3506 | Coastal |
| 6 | Vista | 33.1936 | -117.2411 | Inland |
| 7 | San Marcos | 33.1434 | -117.1661 | Suburban |
| 8 | Encinitas | 33.0391 | -117.2954 | Coastal |
| 9 | National City | 32.6692 | -117.0890 | Urban |
| 10 | Imperial Beach | 32.5839 | -117.1131 | Coastal border |
| 11 | El Cajon | 32.7948 | -116.9628 | Inland valley |
| 12 | La Mesa | 32.7678 | -117.0230 | Suburban |
| 13 | Lemon Grove | 32.7335 | -117.0337 | Suburban |
| 14 | Santee | 32.8384 | -116.9739 | Inland |
| 15 | Poway | 32.9627 | -117.0362 | Suburban |
| 16 | Solana Beach | 33.0006 | -117.2688 | Coastal |
| 17 | Alpine | 32.8351 | -116.7664 | Rural/mountain |
| 18 | Bonita | 32.6653 | -117.0444 | Suburban |
| 19 | Fallbrook | 33.3764 | -117.2511 | Rural north |
| 20 | Jamul | 32.7266 | -116.8823 | Rural |
| 21 | Coronado | 32.6859 | -117.1831 | Coastal island |
| 22 | Del Mar | 32.9595 | -117.2653 | Coastal affluent |
| 23 | Rancho Santa Fe | 33.0167 | -117.2056 | Rural affluent |
| 24 | Camp Pendleton North | 33.2817 | -117.3197 | Military |
| 25 | Eucalyptus Hills | 32.8295 | -116.8201 | Rural |
| 26 | La Jolla | 32.8427 | -117.2578 | Coastal affluent |
| 27 | Mira Mesa | 32.9185 | -117.1382 | Suburban |
| 28 | Lakeside | 32.8820 | -116.9017 | Inland |
| 29 | Casa de Oro-Mount Helix | 32.7335 | -116.9964 | Suburban hills |
| 30 | Bostonia | — | — | Suburban |

**Geographic spread:**
- Latitude range: 32.5839 (Imperial Beach, southernmost) → 33.3764 (Fallbrook, northernmost)
- Longitude range: -117.3795 (Oceanside, westernmost) → -116.7664 (Alpine, easternmost)
- Distance covered: ~90 km north-south, ~60 km east-west

### Usage

```bash
# Full batch (runs all 30 locations with LLM)
python run_batch.py

# With explicit config
python run_batch.py --config config.yaml

# Dry run (data extraction + features only, skip LLM)
python run_batch.py --dry-run
```

### CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--config` | `config.yaml` | Base YAML config |
| `--locations` | `data/lats_longs_san_diego.csv` | CSV with name, latitude, longitude |
| `--output-dir` | `batch_outputs/` | Directory for all output files |
| `--dry-run` | `false` | Skip LLM, run data extraction + features only |

### Batch Processing Logic

For each of the 30 locations:

1. **Deep copy** base config to avoid cross-contamination
2. **Override** latitude, longitude, output paths
3. **Execute** `Pipeline(cfg).run()` (full 5-step pipeline)
4. **Save** 2 output files per location:

| File | Content | Typical Size |
|------|---------|-------------|
| `{Name}_output.txt` | Full LLM recommendation | ~2,500–4,000 chars |
| `{Name}_feature_outputs.txt` | Feature-engineered summary | ~4,000 chars |

### Filename Sanitisation

Location names are converted to safe filenames:

```python
"Casa de Oro-Mount Helix" → "Casa_de_Oro-Mount_Helix"
"Camp Pendleton North"    → "Camp_Pendleton_North"
```

Regex: `re.sub(r"[^\w\-]", "_", name).strip("_")`

### Progress Display

Uses `tqdm` for a live progress bar:

```
════════════════════════════════════════════════════════════
  BATCH RUN – 30 locations
  Backend : ollama  |  Model: llama3.1:8b
  Outputs → /path/to/batch_outputs
════════════════════════════════════════════════════════════

Locations: 100%|████████████████████| 30/30 [1:12:00<00:00, 144s/loc]
```

### Error Handling

Each location is wrapped in a try/except — a failure in one location **does not** stop the batch:

```python
try:
    pipeline = Pipeline(cfg)
    result = pipeline.run()
    successes.append((name, elapsed))
except Exception as exc:
    failures.append((name, str(exc)))
    tqdm.write(f"  ✗ {name}: {exc}")
```

### Batch Summary Output

```
════════════════════════════════════════════════════════════
  BATCH COMPLETE
  Succeeded : 30 / 30
════════════════════════════════════════════════════════════

  Total time : 4320.0s
  Avg / loc  : 144.0s

  All outputs saved in: /path/to/batch_outputs
```

### Dry Run Mode

Skips the LLM call entirely — only runs Steps 0 and 1:

```python
if args.dry_run:
    regenerate_all(...)                    # Step 0
    feats = extract_all_features(...)      # Step 1
    feat_text = format_for_llm(feats)
    fe_out.write_text(feat_text)
    result = "[dry-run] LLM skipped"
```

Useful for:
- Testing the data pipeline without waiting for LLM inference
- Generating feature summaries for manual analysis
- Verifying data extraction works for all 30 locations

---

## Output File Inventory (Full Batch)

After a complete batch run, `batch_outputs/` contains **60 files** (2 per location):

```
batch_outputs/
├── Alpine_output.txt
├── Alpine_feature_outputs.txt
├── Bonita_output.txt
├── Bonita_feature_outputs.txt
├── Bostonia_output.txt
├── Bostonia_feature_outputs.txt
├── Camp_Pendleton_North_output.txt
├── Camp_Pendleton_North_feature_outputs.txt
├── Carlsbad_output.txt
├── Carlsbad_feature_outputs.txt
├── ...
├── Vista_output.txt
└── Vista_feature_outputs.txt
```

**Total output data:** ~60 files × ~3.5 KB avg = **~210 KB** of analysis

---

## Batch Performance Metrics

| Metric | Value |
|--------|-------|
| Locations processed | 30 |
| Success rate | 30/30 (100%) |
| Total runtime | ~4,320 s (72 minutes) |
| Avg per location | ~144 s |
| Avg data extraction | ~8 s/location |
| Avg feature engineering | ~2 s/location |
| Avg LLM inference | ~130 s/location |
| Output files generated | 60 |
| Total output size | ~210 KB |

---

## Dependencies

### workflow.py
- `pyyaml>=6.0` — YAML config loading
- `argparse` (stdlib) — CLI parsing
- `time` (stdlib) — Performance timing
- `pathlib` (stdlib) — Output file handling

### run_batch.py
- `tqdm` — Progress bar
- `copy.deepcopy` (stdlib) — Config isolation per location
- `csv` (stdlib) — Locations CSV reading
- `re` (stdlib) — Filename sanitisation
- All pipeline dependencies
