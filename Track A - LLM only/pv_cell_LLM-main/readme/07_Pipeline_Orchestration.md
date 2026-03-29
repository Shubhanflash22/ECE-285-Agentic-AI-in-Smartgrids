# Step 7: Pipeline Orchestration (`pipeline.py`)

## Overview

`pipeline.py` contains the `Pipeline` class, which runs the end-to-end workflow in a fixed sequence:

1. Regenerate CSV data from latitude/longitude
2. Run feature engineering and format feature context text
3. Optionally build and query RAG context
4. Build the final prompt
5. Call the configured LLM backend

`Pipeline.run()` returns the LLM response as a string.

---

## Where It Is Used

- `workflow.py` creates one `Pipeline(config)` and runs it once.
- `run_batch.py` creates one `Pipeline(cfg)` per location and runs it in a loop.
- `run_batch.py --dry-run` does **not** call `Pipeline`; it manually runs only data extraction + feature engineering.

---

## `Pipeline` Class

### Constructor

```python
pipeline = Pipeline(config: WorkflowConfig)
```

- Stores the provided `WorkflowConfig` in `self.config`
- Initialises `self._backend = None` (backend is created lazily)

### Public Method: `run()`

#### Step 0: Regenerate Data CSVs

`run()` starts by calling:

```python
regenerate_all(
    latitude=cfg.fe_latitude,
    longitude=cfg.fe_longitude,
    weather_csv=cfg.weather_csv,
    household_csv=cfg.household_csv,
    electricity_csv=cfg.electricity_csv,
)
```

This writes/updates the configured weather, household, and electricity CSV paths.

#### Step 1: Feature Engineering

`run()` then:

- Loads the regenerated CSV files with `pandas.read_csv`
- Calls `extract_all_features(...)`
- Converts features to text via `format_for_llm(features)`
- Writes the resulting text to `cfg.feature_output_path` (creating parent directories if needed)

#### Step 2: RAG (Optional)

- `rag_context` starts as `None`
- If `cfg.rag_path` is set, `run()`:
  - Creates `RAGRetriever(chunk_size=cfg.chunk_size, chunk_overlap=cfg.chunk_overlap)`
  - Calls `retriever.index(cfg.rag_path)`
  - Calls `retriever.retrieve(cfg.prompt, top_k=cfg.top_k)`
- If `cfg.rag_path` is not set, RAG is skipped and `rag_context` stays `None`

#### Step 3: Prompt Assembly

`run()` builds a resolved user prompt with:

```python
resolved_prompt = cfg.prompt.format(
    num_evs=cfg.fe_num_evs,
    pv_budget=f"{cfg.fe_pv_budget:,.0f}",
)
```

Then:

```python
builder = PromptBuilder(system_prompt=cfg.system_prompt)
final_prompt = builder.build(
    user_prompt=resolved_prompt,
    feature_context=feature_context,
    rag_context=rag_context,
)
```

#### Step 4: LLM Call

`run()` gets the backend via `_get_backend()` and calls:

```python
response = backend.generate(
    prompt=final_prompt,
    system=cfg.system_prompt,
    max_tokens=cfg.max_tokens,
    temperature=cfg.temperature,
)
```

It returns `response`.

---

## Lazy Backend Initialisation (`_get_backend`)

`_get_backend()` initialises once and caches the backend instance:

- If `cfg.backend == "ollama"`: imports and creates `OllamaBackend(host=cfg.host, model=cfg.model)`
- If `cfg.backend == "vllm"`: imports and creates `VLLMBackend(host=cfg.host, model=cfg.model)`
- Otherwise raises `ValueError("Unknown backend: ...")`

On later calls, the cached backend object is reused.

---

## Inputs and Outputs

### Primary Input

- `WorkflowConfig` passed to `Pipeline(config)`

Important fields used directly by `pipeline.py`:

- Data regeneration: `fe_latitude`, `fe_longitude`, `weather_csv`, `household_csv`, `electricity_csv`
- Feature engineering parameters: `fe_num_panels`, `fe_occupants`, `fe_house_sqm`, `fe_price_per_kwh`, `fe_num_evs`, `fe_pv_budget`
- RAG: `rag_path`, `chunk_size`, `chunk_overlap`, `top_k`
- Prompting: `prompt`, `system_prompt`
- LLM: `backend`, `host`, `model`, `max_tokens`, `temperature`
- Output path for feature summary: `feature_output_path`

### Outputs Produced by `run()`

- Returns: LLM response string
- Writes: feature summary text file at `feature_output_path`
- Regenerates/updates: data CSV files at configured CSV paths

`pipeline.py` itself does **not** write the final LLM response to disk; callers do that (`workflow.py` and `run_batch.py`).

---

## Error Behavior

`Pipeline.run()` does not have an internal `try/except`; exceptions propagate to caller code.

- `workflow.py` lets errors terminate execution.
- `run_batch.py` catches exceptions per location and continues with the remaining locations.

---

## Minimal Usage

```python
from pipeline import Pipeline
from config import WorkflowConfig

cfg = WorkflowConfig(...)
cfg.validate()

result = Pipeline(cfg).run()
```

`result` is the LLM output text.
