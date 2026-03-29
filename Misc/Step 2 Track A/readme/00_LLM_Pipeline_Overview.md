# LLM Pipeline — Complete Architecture & Detailed Working

## 1. System Overview

This project implements a **zero-cloud, fully local LLM pipeline** for PV (photovoltaic) solar panel sizing recommendations. The pipeline ingests real-world data from 3 sources, engineers 75+ domain-specific features, augments them with curated domain knowledge via RAG, and feeds everything into a locally-hosted LLM (Llama 3.1 8B) to produce actionable PV installation recommendations for residential households in San Diego County.

**Key Statistics:**
- **30 San Diego locations** processed in a single batch
- **75+ features** computed per location
- **3 data sources** (electricity, weather, household) totalling ~45,000 data points per location
- **5-year historical data** window
- **~144 seconds** average processing time per location
- **60 output files** generated (2 per location)

---

## 2. High-Level Architecture Diagram

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    LLM WORKFLOW: PV PANEL SIZING ADVISOR                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌─────────────┐                                                             ║
║  │ config.yaml  │   User-facing YAML with all tunable parameters             ║
║  └──────┬──────┘                                                             ║
║         │                                                                    ║
║         ▼                                                                    ║
║  ┌─────────────────┐                                                         ║
║  │  WorkflowConfig  │   22 parameters: lat/lon, model, budget, etc.          ║
║  │  (config.py)     │   Validates backend, RAG path, prompt                  ║
║  └──────┬──────────┘                                                         ║
║         │                                                                    ║
║         ▼                                                                    ║
║  ┌─────────────────────────────────────────────────────────────┐             ║
║  │                    PIPELINE (pipeline.py)                     │             ║
║  │                                                               │             ║
║  │  ╔═══════════════════════════════════════════════════════╗   │             ║
║  │  ║  STEP 0: DATA EXTRACTION (data_extractor.py)          ║   │             ║
║  │  ║                                                       ║   │             ║
║  │  ║  ┌──────────────┐  ┌───────────────┐  ┌───────────┐  ║   │             ║
║  │  ║  │ Open-Meteo   │  │ EIA Regional  │  │ Aggregate │  ║   │             ║
║  │  ║  │ Weather API  │  │ Load CSV      │  │ Hourly→   │  ║   │             ║
║  │  ║  │    │         │  │    │          │  │ Weekly    │  ║   │             ║
║  │  ║  │    ▼         │  │    ▼          │  │    │      │  ║   │             ║
║  │  ║  │ weather.csv  │  │ household.csv │  │    ▼      │  ║   │             ║
║  │  ║  │ (261 rows)   │  │ (44,306 rows) │  │ elec.csv  │  ║   │             ║
║  │  ║  │ 10 columns   │  │ 2 columns     │  │ (267 rows)│  ║   │             ║
║  │  ║  └──────────────┘  └───────────────┘  └───────────┘  ║   │             ║
║  │  ╚═══════════════════════════════════════════════════════╝   │             ║
║  │         │                    │                    │           │             ║
║  │         └────────────────────┼────────────────────┘           │             ║
║  │                              │                                │             ║
║  │                              ▼                                │             ║
║  │  ╔═══════════════════════════════════════════════════════╗   │             ║
║  │  ║  STEP 1: FEATURE ENGINEERING (feature_engineering.py) ║   │             ║
║  │  ║                                                       ║   │             ║
║  │  ║  ┌─────────────────────────────────────────────────┐  ║   │             ║
║  │  ║  │ 7 Feature Categories, 60+ Functions:            │  ║   │             ║
║  │  ║  │                                                 │  ║   │             ║
║  │  ║  │ 1. Electricity (15 features)                    │  ║   │             ║
║  │  ║  │    Load distribution, seasonality, trends       │  ║   │             ║
║  │  ║  │                                                 │  ║   │             ║
║  │  ║  │ 2. Weather/Solar (12 features)                  │  ║   │             ║
║  │  ║  │    Irradiance, PSH, cloud cover, efficiency     │  ║   │             ║
║  │  ║  │                                                 │  ║   │             ║
║  │  ║  │ 3. Household (7 features)                       │  ║   │             ║
║  │  ║  │    Per-occupant, per-sqm, costs                 │  ║   │             ║
║  │  ║  │                                                 │  ║   │             ║
║  │  ║  │ 4. Cross-Dataset (10 features)                  │  ║   │             ║
║  │  ║  │    Self-sufficiency, payback, grid dependency    │  ║   │             ║
║  │  ║  │                                                 │  ║   │             ║
║  │  ║  │ 5. Risk & Sensitivity (8 features)              │  ║   │             ║
║  │  ║  │    Price sensitivity, irradiance sensitivity     │  ║   │             ║
║  │  ║  │                                                 │  ║   │             ║
║  │  ║  │ 6. EV & Budget (5 features)                     │  ║   │             ║
║  │  ║  │    EV charging load, budget-constrained sizing   │  ║   │             ║
║  │  ║  │                                                 │  ║   │             ║
║  │  ║  │ 7. Formatting → LLM-ready text (~4,000 chars)   │  ║   │             ║
║  │  ║  └─────────────────────────────────────────────────┘  ║   │             ║
║  │  ╚═════════════════════════════════════╤═════════════════╝   │             ║
║  │                                        │                      │             ║
║  │                              ┌─────────┘                      │             ║
║  │                              │                                │             ║
║  │  ┌───────────────┐          │                                │             ║
║  │  │ knowledge.txt  │          │                                │             ║
║  │  │ (158 lines)    │          │                                │             ║
║  │  └──────┬────────┘          │                                │             ║
║  │         │                    │                                │             ║
║  │         ▼                    │                                │             ║
║  │  ╔══════════════════╗       │                                │             ║
║  │  ║ STEP 2: RAG      ║       │                                │             ║
║  │  ║ (retriever.py)   ║       │                                │             ║
║  │  ║                  ║       │                                │             ║
║  │  ║ TF-IDF Index     ║       │                                │             ║
║  │  ║ Cosine Sim       ║       │                                │             ║
║  │  ║ Top-5 Passages   ║       │                                │             ║
║  │  ╚════════╤═════════╝       │                                │             ║
║  │           │                  │                                │             ║
║  │           └──────┬───────────┘                                │             ║
║  │                  │                                            │             ║
║  │                  ▼                                            │             ║
║  │  ╔═══════════════════════════════════════════════════════╗   │             ║
║  │  ║  STEP 3: PROMPT BUILDER (prompt_builder.py)           ║   │             ║
║  │  ║                                                       ║   │             ║
║  │  ║  ┌───────────────────────────────────────────────┐    ║   │             ║
║  │  ║  │ ## DATA CONTEXT (Feature Summary, ~4K chars)  │    ║   │             ║
║  │  ║  │ ## KNOWLEDGE BASE (RAG Passages, ~2.5K chars) │    ║   │             ║
║  │  ║  │ ## QUESTION / INSTRUCTION (~1K chars)         │    ║   │             ║
║  │  ║  │                                               │    ║   │             ║
║  │  ║  │ Total: ~8,000 characters                      │    ║   │             ║
║  │  ║  │ Max cap: 32,000 characters                    │    ║   │             ║
║  │  ║  └───────────────────────────────────────────────┘    ║   │             ║
║  │  ╚═════════════════════════════╤═════════════════════════╝   │             ║
║  │                                │                              │             ║
║  │                                ▼                              │             ║
║  │  ╔═══════════════════════════════════════════════════════╗   │             ║
║  │  ║  STEP 4: LLM INFERENCE                                ║   │             ║
║  │  ║                                                       ║   │             ║
║  │  ║  ┌─────────────────┐    ┌─────────────────────┐      ║   │             ║
║  │  ║  │  Ollama Backend  │ OR │  vLLM Backend        │      ║   │             ║
║  │  ║  │  llama3.1:8b     │    │  Meta-Llama-3-8B    │      ║   │             ║
║  │  ║  │  REST /api/chat  │    │  OpenAI /v1/chat    │      ║   │             ║
║  │  ║  │  Streaming NDJSON│    │  Single response    │      ║   │             ║
║  │  ║  │  Port 11434      │    │  Port 8000          │      ║   │             ║
║  │  ║  └────────┬────────┘    └──────────────────────┘      ║   │             ║
║  │  ║           │                                            ║   │             ║
║  │  ║           ▼                                            ║   │             ║
║  │  ║  LLM Response (~3,000 chars)                           ║   │             ║
║  │  ║  • PV panel recommendation                             ║   │             ║
║  │  ║  • Financial analysis (ROI, payback)                   ║   │             ║
║  │  ║  • Risk assessment                                     ║   │             ║
║  │  ║  • Battery storage advice                              ║   │             ║
║  │  ╚═══════════════════════════════════════════════════════╝   │             ║
║  │                                │                              │             ║
║  └────────────────────────────────┼──────────────────────────────┘             ║
║                                   │                                            ║
║                                   ▼                                            ║
║                        ┌────────────────────────┐                              ║
║                        │  OUTPUT FILES           │                              ║
║                        │                        │                              ║
║                        │  {location}_output.txt  │  ← LLM recommendation      ║
║                        │  {location}_feature_    │                              ║
║                        │    outputs.txt          │  ← Feature summary          ║
║                        └────────────────────────┘                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## 3. Detailed Data Flow — Numeric Trace

This section traces **exact data sizes and transformations** through the pipeline for San Diego (32.7160, -117.1611):

### Stage 0 → Stage 1: Raw Data

| Data Source | Rows | Columns | Granularity | Span |
|-------------|------|---------|-------------|------|
| `weather_data.csv` | 261 | 10 | Weekly | 5 years (2021–2026) |
| `household_data.csv` | 44,306 | 2 | Hourly | 5 years |
| `electricity_data.csv` | 267 | 5 | Weekly | 5 years |
| **Total raw data points** | | | | **~44,834** |

### Stage 1 → Stage 2: Feature Engineering

| Category | # Features | Key Outputs |
|----------|-----------|-------------|
| Electricity Load | 15 | peak=7.79 kW, avg=2.25 kW, CV=0.104 |
| Weather/Solar | 12 | irradiance=219.82 W/m², PSH=1.76 hrs |
| Household | 7 | annual=19,624 kWh, cost=$6,083/yr |
| Cross-Dataset | 10 | 128 panels for 100%, payback=15.7 yr |
| Risk/Sensitivity | 8 | ROI baseline=132.15%, risk=0.209 |
| EV & Budget | 5 | 31 panels within $15K budget |
| **Total** | **~75** | **Formatted: ~4,000 chars** |

### Stage 2: RAG Retrieval

| Metric | Value |
|--------|-------|
| Knowledge base size | 158 lines (~4 KB) |
| Chunks created | ~8–10 |
| Chunks retrieved | 5 |
| RAG context size | ~2,500 chars |

### Stage 3: Prompt Assembly

| Component | Characters | % of Total |
|-----------|-----------|------------|
| Feature summary | ~4,000 | 50% |
| RAG passages | ~2,500 | 30% |
| User prompt | ~1,000 | 12% |
| Headers/formatting | ~600 | 8% |
| **Total prompt** | **~8,100** | **100%** |

### Stage 4: LLM Output

| Metric | Value |
|--------|-------|
| Model | llama3.1:8b |
| Input tokens (est.) | ~2,000 tokens |
| Output tokens (max) | 4,096 tokens |
| Output characters | ~2,500–4,000 |
| Inference time | ~60–180 s |
| Sections generated | 6–8 (trends, sizing, costs, risks, battery, recommendation) |

---

## 4. Component Interaction Diagram

```
                          ┌───────────────────┐
                          │   Entry Points     │
                          │                   │
                          │  workflow.py       │ ← Single location
                          │  run_batch.py     │ ← 30 locations
                          └─────────┬─────────┘
                                    │
                          ┌─────────▼─────────┐
                          │   config.py        │
                          │   WorkflowConfig   │──── config.yaml
                          └─────────┬─────────┘
                                    │
                          ┌─────────▼─────────┐
                          │   pipeline.py      │
                          │   Pipeline.run()   │
                          └─────────┬─────────┘
                                    │
              ┌─────────────────────┼──────────────────────┐
              │                     │                      │
    ┌─────────▼─────────┐  ┌───────▼────────┐  ┌─────────▼──────────┐
    │ data_extractor.py  │  │ retriever.py   │  │ prompt_builder.py   │
    │                   │  │                │  │                     │
    │ regenerate_all()  │  │ RAGRetriever   │  │ PromptBuilder       │
    │   ├─ weather      │  │  .index()      │  │  .build()           │
    │   ├─ household    │  │  .retrieve()   │  │                     │
    │   └─ electricity  │  └────────────────┘  └─────────────────────┘
    └───────────────────┘
              │
    ┌─────────▼──────────────┐           ┌──────────────────────────┐
    │ feature_engineering.py  │           │ ollama_backend.py        │
    │                        │           │ vllm_backend.py          │
    │ extract_all_features() │           │                          │
    │ format_for_llm()       │           │ .generate()              │
    └────────────────────────┘           └──────────────────────────┘
              │                                       │
    ┌─────────▼─────────┐              ┌──────────────▼──────────────┐
    │ weather_data.py    │              │ Ollama Server (port 11434)  │
    │ (Open-Meteo API)   │              │ or vLLM Server (port 8000)  │
    └────────────────────┘              │                             │
              │                         │ llama3.1:8b (4.7 GB)        │
    ┌─────────▼──────────────────┐      └─────────────────────────────┘
    │ household_extraction_      │
    │   per_house.py             │
    │ (EIA CSV → per-household)  │
    └────────────────────────────┘
```

---

## 5. Module Inventory

| Module | Lines | Functions/Classes | Category |
|--------|-------|-------------------|----------|
| `config.py` | 116 | 1 class (`WorkflowConfig`) | Configuration |
| `config.yaml` | 85 | — | Configuration |
| `data_extractor.py` | 221 | 4 functions | Data Extraction |
| `weather_data.py` | 215 | 6 functions | Data Extraction |
| `household_extraction_per_house.py` | 748 | 5+ functions | Data Extraction |
| `feature_engineering.py` | 1,631 | 60+ functions | Feature Engineering |
| `retriever.py` | 168 | 1 class (`RAGRetriever`) | RAG |
| `prompt_builder.py` | 122 | 1 class (`PromptBuilder`) | Prompt Assembly |
| `ollama_backend.py` | 128 | 1 class (`OllamaBackend`) | LLM Inference |
| `vllm_backend.py` | 115 | 1 class (`VLLMBackend`) | LLM Inference |
| `pipeline.py` | 119 | 1 class (`Pipeline`) | Orchestration |
| `workflow.py` | 158 | 3 functions | Entry Point |
| `run_batch.py` | 169 | 5 functions | Batch Runner |
| `loader.py` | 132 | 1 class (`CSVLoader`) | Utility |
| **Total** | **~4,137** | | |

---

## 6. Technology Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **Language** | Python | 3.9+ | Core implementation |
| **LLM Runtime** | Ollama | Latest | Local LLM hosting |
| **Model** | Llama 3.1 8B | 8B params, 4.7 GB | Text generation |
| **Data Processing** | pandas | ≥2.0.0 | DataFrame operations |
| **Numerical** | numpy | — | Statistics, linear regression |
| **RAG** | scikit-learn | ≥1.3.0 | TF-IDF, cosine similarity |
| **HTTP** | requests | ≥2.31.0 | API calls (weather, LLM) |
| **Config** | PyYAML | ≥6.0 | YAML parsing |
| **Tables** | tabulate | ≥0.9.0 | Markdown formatting |
| **Progress** | tqdm | — | Batch progress bar |
| **Alt SDK** | openai | ≥1.0.0 | vLLM backend (optional) |

---

## 7. Data Sources — Detailed Schema

### 7.1 Weather Data (Open-Meteo API)

```
Source:    https://archive-api.open-meteo.com/v1/archive
Timeframe: 5 years ending 7 days ago
Scope:     Single point (lat, lon)
Columns:   10

 week_number | weekly_max_temp | weekly_min_temp | weekly_avg_temp |
             | weekly_max_irr  | weekly_min_irr  | weekly_avg_irr  |
             | weekly_max_cloud| weekly_min_cloud| weekly_avg_cloud|
```

### 7.2 Household Data (EIA Regional)

```
Source:    San_Diego_Load_EIA_Fixed.csv (1,040,149 meters)
Transform: Regional MW → Per-household kW with 9 variability factors
Scope:     Location-specific via SHA256-seeded randomness
Columns:   2 (datetime_local, household_kw)
```

### 7.3 Electricity Data (Aggregated)

```
Source:    Derived from household_data.csv
Transform: Hourly → Daily → Weekly aggregation
Columns:   5 (week_number, max/min/avg load, start_date)
```

### 7.4 Knowledge Base (Curated Text)

```
Source:    Manually curated San Diego PV market data
Size:      158 lines, ~4 KB
Topics:    Installers, costs, tax credits, batteries, SDG&E policies
```

---

## 8. Execution Timeline (Single Location)

```
Time (s)  │  Step
──────────┼────────────────────────────────────────────
 0.0      │  Start: Load config, validate
 0.1      │  Step 0: Fetch weather data (API call)
 5.0      │  Step 0: Generate household data (EIA transform)
 8.0      │  Step 0: Aggregate electricity data
 9.0      │  Step 1: Load 3 CSVs into DataFrames
 9.5      │  Step 1: Compute 75 features
10.5      │  Step 1: Format summary, save to file
10.6      │  Step 2: Index knowledge.txt (TF-IDF)
10.7      │  Step 2: Retrieve top-5 passages
10.7      │  Step 3: Resolve prompt variables
10.8      │  Step 3: Assemble 3-section prompt
10.8      │  Step 4: POST to Ollama /api/chat
10.9      │  Step 4: Streaming response begins...
 ...      │  Step 4: LLM generating tokens...
69.3      │  Step 4: Streaming complete
69.3      │  Save output.txt
69.3      │  Done ✓
```

---

## 9. LLM Prompt Engineering Strategy

The pipeline uses a **structured prompting strategy** with 3 information layers:

### Layer 1: System Prompt (Role Definition)

```
You are an expert power grid data analyst who can suggest the number
of PV cells that can be installed in any house based on weather,
electricity and household_data and is able to reason well on why the
recommendation is made. Be precise, cite numbers, and structure your
answer with clear sections and bullet points.
```

### Layer 2: Data Context (Feature-Engineered Summary)

The LLM receives pre-computed numerical features rather than raw data. This is critical because:
- Raw CSVs (44K+ rows) would exceed context windows
- Pre-computed features reduce hallucination risk
- Structured formatting guides the LLM's attention

### Layer 3: Knowledge Context (RAG Passages)

Real-world market data that supplements numerical analysis:
- Installation costs ($2.70–$3.30/W)
- Federal tax credits (30% ITC)
- SDG&E NEM 3.0 policies
- Battery storage costs ($8,000–$15,000)
- Local installer information

### Layer 4: Task Instruction (User Prompt)

A 7-point structured task with specific deliverables:
1. Review data summary and knowledge base
2. Identify trends and seasonal patterns
3. Factor in EV charging load
4. Assess budget constraints
5. Determine optimal panel count
6. Estimate savings and payback
7. Comment on risks and battery storage

---

## 10. Output Analysis

### Typical LLM Response Structure

```
## RECOMMENDATION FOR PV PANEL INSTALLATION

### KEY TRENDS AND SEASONAL PATTERNS
  • Annual consumption: 19,624 kWh
  • Stable demand, slight summer peak

### PV PANEL SIZING
  • 100% offset: 128 panels needed
  • Budget-constrained: 31 panels ($15,000)

### PAYBACK PERIOD AND ROI
  • Break-even: 10.03 years (budget-constrained)
  • ROI (25 yr): 132.15%
  • Annual savings: $1,480.42

### RISKS AND CAVEATS
  • Nighttime load ratio: 70.23%
  • Sunlight CV: 0.3141

### BATTERY STORAGE
  • Advisable for nighttime consumption offset
  • Cost: $8,000–$15,000

### FINAL RECOMMENDATION
  • Install 31 panels (within budget)
  • Expected production: 4,775 kWh/year
  • 5-7 year savings: $7,402–$10,363
```

---

## 11. Batch Processing — 30 Locations

### Processing Loop

```
FOR each of 30 locations:
    1. Deep copy base config
    2. Override: lat, lon, output paths
    3. Call Pipeline(cfg).run():
        a. Regenerate 3 CSVs for this lat/lon
        b. Compute 75 features
        c. Retrieve 5 RAG passages
        d. Assemble prompt
        e. Call LLM (Ollama)
    4. Save: {name}_output.txt, {name}_feature_outputs.txt
    5. Record timing
```

### Batch Performance

| Metric | Value |
|--------|-------|
| Total locations | 30 |
| Success rate | 100% (30/30) |
| Total runtime | ~72 minutes |
| Avg per location | ~144 seconds |
| Data extraction time | ~8 s/loc (5.5%) |
| Feature engineering | ~2 s/loc (1.4%) |
| RAG retrieval | <0.1 s/loc (0.1%) |
| Prompt assembly | <0.1 s/loc (0.1%) |
| **LLM inference** | **~134 s/loc (93%)** |
| Files generated | 60 (30 × 2) |
| Total output size | ~210 KB |

**Key insight:** LLM inference dominates at 93% of total time. All data processing (extraction, features, RAG, prompt) takes only ~10 seconds combined.

---

## 12. Dependencies & Requirements

```
# requirements.txt
requests>=2.31.0         # HTTP: weather API, Ollama, vLLM
pyyaml>=6.0              # Config parsing
pandas>=2.0.0            # CSV loading, aggregation, statistics
tabulate>=0.9.0          # Markdown table formatting
scikit-learn>=1.3.0      # TF-IDF RAG indexing and retrieval
openai>=1.0.0            # vLLM backend (optional)
tqdm                     # Batch progress bar
```

**System requirements:**
- Python 3.9+
- Ollama installed and running (`brew install ollama`)
- `llama3.1:8b` model pulled (~4.7 GB)
- 8+ GB RAM (16 GB recommended)

---

## 13. File Structure

```
285_LLM_Workflow/
│
├── workflow.py                    ← CLI entry point (single)
├── run_batch.py                   ← Batch runner (30 locations)
├── config.yaml                    ← User configuration
├── config.py                      ← WorkflowConfig dataclass
├── pipeline.py                    ← 5-step orchestrator
├── data_extractor.py              ← CSV regeneration from lat/lon
├── feature_engineering.py         ← 75+ feature computation (1,631 lines)
├── retriever.py                   ← TF-IDF RAG retriever
├── prompt_builder.py              ← 3-section prompt assembler
├── ollama_backend.py              ← Ollama REST API client
├── vllm_backend.py                ← vLLM OpenAI-compatible client
├── loader.py                      ← CSV loader utility
├── requirements.txt               ← Python dependencies
│
├── data/
│   ├── electricity_data.csv       ← Weekly load (267 rows)
│   ├── household_data.csv         ← Hourly usage (44,306 rows)
│   ├── weather_data.csv           ← Weekly weather (261 rows)
│   ├── knowledge.txt              ← RAG knowledge base (158 lines)
│   └── lats_longs_san_diego.csv   ← 30 location coordinates
│
├── data_extraction/
│   ├── weather_data.py            ← Open-Meteo API client
│   └── Household_electricity_data/
│       ├── household_extraction_per_house.py  ← EIA → household
│       └── San_Diego_Load_EIA_Fixed.csv       ← Source EIA data
│
├── batch_outputs/                 ← 60 files (30 locations × 2)
│   ├── San_Diego_output.txt
│   ├── San_Diego_feature_outputs.txt
│   ├── Chula_Vista_output.txt
│   ├── Chula_Vista_feature_outputs.txt
│   └── ... (56 more files)
│
├── outputs/
│   ├── output.txt                 ← Single-run LLM output
│   └── feature_outputs.txt        ← Single-run features
│
└── readme/                        ← Pipeline documentation
    ├── 00_LLM_Pipeline_Overview.md  ← This file
    ├── 01_Configuration.md
    ├── 02_Data_Extraction.md
    ├── 03_Feature_Engineering.md
    ├── 04_RAG_Retriever.md
    ├── 05_Prompt_Builder.md
    ├── 06_LLM_Backends.md
    ├── 07_Pipeline_Orchestration.md
    └── 08_Batch_Runner.md
```

---

## 14. Simplified Flow Diagram (for Image Generation)

Use this description to generate a visual pipeline diagram:

```
┌──────────┐   ┌──────────┐   ┌──────────┐
│ Weather  │   │Household │   │Knowledge │
│ API      │   │ EIA CSV  │   │   .txt   │
│(Open-    │   │(1M meters│   │ (158 ln) │
│ Meteo)   │   │ regional)│   │          │
└────┬─────┘   └────┬─────┘   └────┬─────┘
     │              │              │
     ▼              ▼              │
┌──────────┐  ┌──────────┐        │
│weather   │  │household │        │
│.csv      │  │.csv      │        │
│261 rows  │  │44K rows  │        │
└────┬─────┘  └────┬─────┘        │
     │         ┌───┘              │
     │         ▼                  │
     │   ┌──────────┐            │
     │   │electricity│            │
     │   │.csv       │            │
     │   │267 rows   │            │
     │   └────┬─────┘            │
     │        │                   │
     └────┬───┘                   │
          │                       │
          ▼                       │
   ┌──────────────┐              │
   │  FEATURE      │              │
   │  ENGINEERING  │              │
   │  75 features  │              │
   │  ~4,000 chars │              │
   └──────┬───────┘              │
          │                       │
          │                       ▼
          │              ┌──────────────┐
          │              │  RAG         │
          │              │  RETRIEVER   │
          │              │  TF-IDF      │
          │              │  5 passages  │
          │              │  ~2,500 chars│
          │              └──────┬───────┘
          │                     │
          └──────────┬──────────┘
                     │
                     ▼
              ┌──────────────┐
              │   PROMPT     │
              │   BUILDER    │
              │   3 sections │
              │   ~8K chars  │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │   LLM        │
              │   Llama 3.1  │
              │   8B params  │
              │   Ollama     │
              │   ~144s      │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │   OUTPUT     │
              │   PV Sizing  │
              │   Recommend. │
              │   ~3K chars  │
              └──────────────┘
```

**Colour Coding Suggestion:**
- 🔵 Blue: Data sources (external inputs)
- 🟢 Green: Processing steps (internal computation)
- 🟡 Yellow: LLM inference (neural network)
- 🔴 Red: Output (final deliverable)

**Arrow Labels:**
- Weather API → weather.csv: "5yr hourly → weekly aggregation"
- EIA CSV → household.csv: "Regional MW → per-household kW"
- 3 CSVs → Feature Engineering: "~45K data points → 75 features"
- Knowledge.txt → RAG: "158 lines → 5 passages (TF-IDF cosine)"
- Features + RAG → Prompt: "~6.5K chars → 8K char structured prompt"
- Prompt → LLM: "~2K tokens input → 4K tokens max output"
- LLM → Output: "Structured recommendation with sections"
