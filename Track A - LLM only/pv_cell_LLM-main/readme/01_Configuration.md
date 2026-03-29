# Step 1: Configuration (`config.py` + `config.yaml`)

## Overview

The Configuration step is the **entry point** of the entire LLM pipeline. It centralises every tunable parameter — from geographic coordinates and data file paths, to LLM model selection, RAG settings, and output destinations — into a single `WorkflowConfig` dataclass. This ensures **zero hard-coded values** exist downstream, making the pipeline fully reproducible and batch-ready.

---

## Architecture Position

```
┌──────────────────────────────────────────────────────────┐
│                    CONFIGURATION                          │
│                                                          │
│  config.yaml ──► WorkflowConfig.from_dict() ──► config   │
│       OR                                                 │
│  CLI flags   ──► WorkflowConfig(**kwargs)    ──► config   │
│                                                          │
│  config.validate() ──► pass / raise ValueError           │
│                         │                                │
│                         ▼                                │
│              Pipeline(config).run()                       │
└──────────────────────────────────────────────────────────┘
```

---

## Files Involved

| File | Role | Lines of Code |
|------|------|---------------|
| `config.py` | `WorkflowConfig` dataclass definition | 116 lines |
| `config.yaml` | User-facing YAML configuration file | ~85 lines |

---

## `WorkflowConfig` Dataclass — All Parameters

The dataclass has **22 configurable fields** grouped into 6 categories:

### 1. Feature Engineering Parameters (10 fields)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fe_latitude` | `float` | `32.7157` | Latitude of the household (San Diego default) |
| `fe_longitude` | `float` | `-117.1611` | Longitude of the household |
| `electricity_csv` | `str` | `data/electricity_data.csv` | Path to weekly electricity consumption CSV |
| `household_csv` | `str` | `data/household_data.csv` | Path to hourly household load CSV |
| `weather_csv` | `str` | `data/weather_data.csv` | Path to weekly weather/solar CSV |
| `fe_num_panels` | `int` | `10` | Starting assumption for PV panel count |
| `fe_occupants` | `int` | `4` | Number of household occupants |
| `fe_house_sqm` | `float` | `150.0` | House area in square metres |
| `fe_price_per_kwh` | `float` | `0.31` | Local electricity tariff (USD/kWh) |
| `fe_num_evs` | `int` | `0` | Number of electric vehicles owned |
| `fe_pv_budget` | `float` | `10000.0` | Budget for PV installation (USD) |

### 2. RAG Settings (4 fields)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rag_path` | `str \| None` | `None` | Path to knowledge text file (e.g., `data/knowledge.txt`) |
| `chunk_size` | `int` | `500` | Characters per RAG chunk |
| `chunk_overlap` | `int` | `50` | Overlap between consecutive chunks |
| `top_k` | `int` | `3` | Number of top-ranked chunks injected into prompt |

### 3. Prompt Settings (2 fields)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | `str` | `""` | User question/instruction for the LLM |
| `system_prompt` | `str` | `"You are a helpful data analyst…"` | System role instruction |

### 4. LLM Backend (4 fields)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `backend` | `str` | `"ollama"` | Backend engine: `"ollama"` or `"vllm"` |
| `model` | `str` | `"llama3"` | Model name (e.g., `llama3.1:8b`) |
| `host` | `str` | `http://localhost:11434` | Backend server URL |
| `max_tokens` | `int` | `2048` | Maximum output tokens |
| `temperature` | `float` | `0.2` | Sampling temperature (0 = deterministic) |

### 5. Output (2 fields)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_path` | `str` | `output.txt` | Path to save LLM response |
| `feature_output_path` | `str` | `outputs/feature_outputs.txt` | Path to save feature-engineering summary |

---

## Configuration Loading — Two Modes

### Mode A: YAML File (Recommended for Production)

```bash
python workflow.py --config config.yaml
```

Internally calls:

```python
WorkflowConfig.from_dict(yaml.safe_load(open("config.yaml")))
```

The YAML file is organised into nested sections:

```yaml
feature_engineering:      # → fe_latitude, fe_longitude, fe_num_panels, etc.
data:                     # → rag_path
llm:                      # → backend, model, host, max_tokens, temperature
rag:                      # → chunk_size, chunk_overlap, top_k
output:                   # → output_path, feature_output_path
prompt: "..."             # → prompt
system_prompt: "..."      # → system_prompt
```

### Mode B: CLI Flags (Useful for Quick Tests)

```bash
python workflow.py --backend ollama --model llama3.1:8b --prompt "How many panels?"
```

Each CLI flag maps 1:1 to a `WorkflowConfig` field.

---

## Validation Rules

`config.validate()` enforces 3 critical checks before the pipeline starts:

| Check | Condition | Error Raised |
|-------|-----------|--------------|
| Backend | Must be `"ollama"` or `"vllm"` | `ValueError` |
| RAG file | If `rag_path` is set, file must exist on disk | `FileNotFoundError` |
| Prompt | `prompt.strip()` must be non-empty | `ValueError` |

> **Note:** CSV files are **not** validated at config time because they are regenerated from lat/lon during pipeline execution (Step 0: Data Extraction).

---

## Batch Run Override Mechanism

When `run_batch.py` processes 30 San Diego locations, it performs a `deepcopy` of the base config for each location and overrides:

```python
cfg = deepcopy(base_cfg)
cfg.fe_latitude  = loc["latitude"]     # e.g., 32.6399 (Chula Vista)
cfg.fe_longitude = loc["longitude"]    # e.g., -117.1067
cfg.output_path         = "batch_outputs/Chula_Vista_output.txt"
cfg.feature_output_path = "batch_outputs/Chula_Vista_feature_outputs.txt"
```

This means the **same base config** (model, budget, occupants, etc.) is reused across all 30 locations, with only coordinates and output paths changing.

---

## Numeric Defaults Used in Production Batch

The actual `config.yaml` used for the 30-location batch run has these values:

| Parameter | Production Value | Significance |
|-----------|-----------------|--------------|
| `num_panels` | `10` | Starting assumption — actual recommendation is LLM-generated |
| `occupants` | `4` | 4-person household |
| `house_sqm` | `150.0` | ~1,615 sq ft |
| `price_per_kwh` | `$0.31` | SDG&E average residential rate |
| `num_evs` | `1` | 1 electric vehicle |
| `pv_budget` | `$15,000` | Household installation budget |
| `max_tokens` | `4096` | Allows detailed multi-section responses |
| `temperature` | `0.2` | Low temperature for factual, deterministic outputs |
| `top_k` | `5` | 5 RAG chunks injected per query |
| `chunk_size` | `500` | ~100-word chunks from knowledge.txt |

---

## Dependencies

- `pyyaml>=6.0` — for `yaml.safe_load()`
- Python `dataclasses` (stdlib) — for `@dataclass`
- Python `pathlib` (stdlib) — for file existence checks

---

## Key Design Decisions

1. **Dataclass over dict**: Provides IDE autocomplete, type hints, and validation — eliminates typo-based bugs.
2. **No CSV validation at config time**: CSVs are regenerated from lat/lon each run, so they don't need to pre-exist.
3. **`from_dict` factory method**: Decouples YAML structure from dataclass field names — YAML uses nested sections while dataclass is flat.
4. **Deep copy for batch**: Ensures each location gets an independent config — no cross-contamination between iterations.
