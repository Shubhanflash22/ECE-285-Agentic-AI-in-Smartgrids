# Step 7: Pipeline Orchestration (`pipeline.py`)

## Overview

The Pipeline module is the **central orchestrator** of the entire LLM workflow. It stitches together all 5 processing stages — data extraction, feature engineering, RAG retrieval, prompt assembly, and LLM inference — into a single `Pipeline.run()` call. This is the module that `workflow.py` and `run_batch.py` invoke to execute the complete end-to-end analysis for a given configuration.

---

## Architecture Position

```
                    ┌──────────────────┐
                    │  WorkflowConfig   │
                    └────────┬─────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                      PIPELINE.run()                          │
│                                                              │
│  Step 0: regenerate_all()                                    │
│          ├─ weather_data.csv                                 │
│          ├─ household_data.csv                               │
│          └─ electricity_data.csv                             │
│                      │                                       │
│  Step 1: extract_all_features() → format_for_llm()          │
│          └─ feature_context (text, ~4,000 chars)             │
│          └─ saved to feature_output_path                     │
│                      │                                       │
│  Step 2: RAGRetriever.index() → .retrieve()                 │
│          └─ rag_context (text, ~2,500 chars)                 │
│                      │                                       │
│  Step 3: PromptBuilder.build()                               │
│          └─ final_prompt (text, ~8,000 chars)                │
│                      │                                       │
│  Step 4: backend.generate()                                  │
│          └─ response (text, ~3,000 chars)                    │
│                      │                                       │
│  return response                                             │
└──────────────────────────────────────────────────────────────┘
```

---

## File Details

| File | Role | Lines of Code |
|------|------|---------------|
| `pipeline.py` | Orchestration — 5-step sequential execution | 119 lines |

---

## The `Pipeline` Class

### Constructor

```python
pipeline = Pipeline(config: WorkflowConfig)
```

Takes a fully populated `WorkflowConfig` object. The LLM backend is **lazily initialised** (not created until first needed).

### `run()` Method — Step by Step

#### Step 0: Regenerate Data CSVs

```python
regenerate_all(
    latitude=cfg.fe_latitude,       # e.g., 32.7157
    longitude=cfg.fe_longitude,     # e.g., -117.1611
    weather_csv=cfg.weather_csv,    # data/weather_data.csv
    household_csv=cfg.household_csv,# data/household_data.csv
    electricity_csv=cfg.electricity_csv,  # data/electricity_data.csv
)
```

**Generates:** 3 CSV files from lat/lon coordinates  
**Time:** ~5–10 seconds (includes 1 API call to Open-Meteo)

#### Step 1: Feature Engineering

```python
df_elec = pd.read_csv(cfg.electricity_csv)       # 267 rows × 5 cols
df_household = pd.read_csv(cfg.household_csv)     # 44,306 rows × 2 cols
df_weather = pd.read_csv(cfg.weather_csv)          # 261 rows × 10 cols

features = extract_all_features(
    df_elec, df_weather, df_household,
    num_panels=cfg.fe_num_panels,     # 10
    occupants=cfg.fe_occupants,       # 4
    house_sqm=cfg.fe_house_sqm,       # 150.0
    price_per_kwh=cfg.fe_price_per_kwh, # 0.31
    num_evs=cfg.fe_num_evs,           # 1
    pv_budget=cfg.fe_pv_budget,       # 15000.0
)
feature_context = format_for_llm(features)
```

**Output:** ~75 computed features formatted into a ~4,000-char text summary  
**Side effect:** Summary saved to `cfg.feature_output_path`  
**Time:** ~1–2 seconds

#### Step 2: RAG Context Retrieval

```python
retriever = RAGRetriever(chunk_size=500, chunk_overlap=50)
retriever.index(cfg.rag_path)                    # data/knowledge.txt
rag_context = retriever.retrieve(cfg.prompt, top_k=5)
```

**Output:** 5 retrieved knowledge passages (~2,500 chars)  
**Time:** <100 ms

**Conditional:** This step is skipped if `cfg.rag_path` is `None`.

#### Step 3: Prompt Assembly

```python
resolved_prompt = cfg.prompt.format(
    num_evs=cfg.fe_num_evs,
    pv_budget=f"{cfg.fe_pv_budget:,.0f}",
)
builder = PromptBuilder(system_prompt=cfg.system_prompt)
final_prompt = builder.build(
    user_prompt=resolved_prompt,
    feature_context=feature_context,
    rag_context=rag_context,
)
```

**Output:** Final prompt string (~8,000 chars) with 3 sections  
**Time:** <10 ms

#### Step 4: LLM Inference

```python
backend = self._get_backend()   # Lazy init: OllamaBackend or VLLMBackend
response = backend.generate(
    prompt=final_prompt,
    system=cfg.system_prompt,
    max_tokens=cfg.max_tokens,   # 4096
    temperature=cfg.temperature, # 0.2
)
```

**Output:** LLM-generated PV sizing recommendation (~3,000 chars)  
**Time:** ~60–180 seconds (Ollama, llama3.1:8b on CPU)

---

## Lazy Backend Initialisation

The LLM backend is **not** created until `_get_backend()` is first called:

```python
def _get_backend(self):
    if self._backend is None:
        if cfg.backend == "ollama":
            from ollama_backend import OllamaBackend
            self._backend = OllamaBackend(host=cfg.host, model=cfg.model)
        elif cfg.backend == "vllm":
            from vllm_backend import VLLMBackend
            self._backend = VLLMBackend(host=cfg.host, model=cfg.model)
    return self._backend
```

**Benefits:**
- Import is deferred — no `ImportError` if unused backend's dependencies are missing
- Backend object is cached — reused for the same pipeline instance
- Clean separation — adding a new backend is a 3-line change

---

## Data Flow Summary

| Step | Input | Output | Size | Time |
|------|-------|--------|------|------|
| 0. Data Extraction | lat, lon | 3 CSVs | ~45K rows total | 5–10 s |
| 1. Feature Engineering | 3 CSVs | Feature summary text | ~4,000 chars | 1–2 s |
| 2. RAG Retrieval | knowledge.txt + query | 5 passages | ~2,500 chars | <100 ms |
| 3. Prompt Assembly | features + RAG + question | Final prompt | ~8,000 chars | <10 ms |
| 4. LLM Inference | Final prompt | Recommendation | ~3,000 chars | 60–180 s |
| **Total** | | | | **~70–190 s** |

---

## Module Dependencies

```python
from config import WorkflowConfig
from data_extractor import regenerate_all
from feature_engineering import extract_all_features, format_for_llm
from retriever import RAGRetriever
from prompt_builder import PromptBuilder

# Conditionally imported (lazy):
from ollama_backend import OllamaBackend    # if backend == "ollama"
from vllm_backend import VLLMBackend        # if backend == "vllm"
```

---

## Error Propagation

The pipeline does **not** catch exceptions internally — errors bubble up to the caller (`workflow.py` or `run_batch.py`):

| Step | Possible Error | Cause |
|------|---------------|-------|
| Step 0 | `FileNotFoundError` | EIA CSV missing |
| Step 0 | `ConnectionError` | Open-Meteo API unreachable |
| Step 1 | `KeyError` | Missing CSV columns |
| Step 2 | `FileNotFoundError` | RAG knowledge file missing |
| Step 4 | `ConnectionError` | LLM server not running |
| Step 4 | `RuntimeError` | Model not pulled / HTTP error |

In batch mode, `run_batch.py` wraps each `Pipeline.run()` call in a try/except to continue processing remaining locations.

---

## Usage Examples

### Single Location (via workflow.py)

```python
config = WorkflowConfig.from_dict(yaml.safe_load(open("config.yaml")))
config.validate()
pipeline = Pipeline(config)
result = pipeline.run()  # Returns LLM response string
```

### Batch Mode (via run_batch.py)

```python
for loc in locations:
    cfg = deepcopy(base_cfg)
    cfg.fe_latitude = loc["latitude"]
    cfg.fe_longitude = loc["longitude"]
    pipeline = Pipeline(cfg)
    result = pipeline.run()
    Path(cfg.output_path).write_text(result)
```

---

## Dependencies

- `pandas>=2.0.0` — CSV loading in Step 1
- All other dependencies are inherited from the modules it orchestrates
