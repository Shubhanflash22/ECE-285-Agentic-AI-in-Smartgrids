# LLM Workflow: PV Panel Sizing Advisor

A modular, zero-cloud pipeline that performs **feature engineering** on 3 real-world CSV data sources (electricity, weather, household), augments it with a **RAG knowledge base**, and feeds everything into a **local LLM** (Ollama or vLLM) to produce a PV solar panel sizing recommendation.

```
electricity_data.csv ─┐
weather_data.csv      ├─► DataExtractor ─► FeatureEngineering ─┐
household_data.csv ───┘                                         ├─► PromptBuilder ─► LLM ─► output.txt
                                                                │
                                          RAGRetriever ─────────┘
                                               ▲
                                          knowledge.txt
```

---

## Project Structure

```
285_LLM_Workflow/
├── workflow.py              ← Entry point (CLI)
├── config.yaml              ← Edit this to configure your run
├── config.py                ← WorkflowConfig dataclass
├── pipeline.py              ← Orchestration logic
├── data_extractor.py        ← Regenerates CSVs from lat/lon
├── feature_engineering.py  ← Domain feature computation
├── retriever.py             ← TF-IDF RAG retriever
├── prompt_builder.py        ← Assembles final LLM prompt
├── ollama_backend.py        ← Ollama REST API client
├── vllm_backend.py          ← vLLM OpenAI-compatible client
├── loader.py                ← CSV loader utility
├── run_batch.py             ← Batch runner
├── requirements.txt
│
├── data/
│   ├── electricity_data.csv
│   ├── household_data.csv
│   ├── weather_data.csv
│   ├── knowledge.txt        ← RAG knowledge base
│   └── lats_longs_san_diego.csv
│
└── outputs/
    ├── output.txt           ← LLM response
    └── feature_outputs.txt  ← Feature engineering summary
```

---

## Prerequisites

- **Python 3.9+**
- **[Ollama](https://ollama.com)** installed on your machine (for the default backend)
- Sufficient RAM: at least **8 GB** for `llama3.1:8b` (16 GB recommended)

---

## Step-by-Step: Running the Batch (30 San Diego Locations)

This is the primary way to run the project. `run_batch.py` iterates over all 30 San Diego neighbourhoods defined in `data/lats_longs_san_diego.csv`, runs the full pipeline (data extraction → feature engineering → RAG → LLM) for each, and saves individual output files in `batch_outputs/`.

### Step 1 — Install Python dependencies

```bash
cd /path/to/285_LLM_Workflow
pip install -r requirements.txt
```

### Step 2 — Install and start Ollama

If you haven't installed Ollama yet:

```bash
# macOS
brew install ollama
```

Or download directly from [https://ollama.com/download](https://ollama.com/download).

Start the Ollama server in a **separate terminal** (keep it running throughout the batch):

```bash
ollama serve
```

You should see:
```
Listening on 127.0.0.1:11434 ...
```

### Step 3 — Pull the model (one-time, ~4.7 GB)

```bash
ollama pull llama3.1:8b
```

Verify it's available:

```bash
ollama list
```

### Step 4 — (Optional) Review `config.yaml`

The batch runner uses `config.yaml` as a base config and overrides `latitude`/`longitude` for each location. Key parameters:

```yaml
feature_engineering:
  num_panels: 10            # Starting assumption for PV panel count
  occupants:  4             # Number of people in the household
  house_sqm:  150.0         # House size in square metres
  price_per_kwh: 0.31       # Local electricity rate (USD/kWh)
  num_evs: 1                # Number of EVs owned
  pv_budget: 15000          # Budget for PV installation (USD)

llm:
  backend: ollama
  model: llama3.1:8b        # Must match what you pulled in Step 3
  host: http://localhost:11434
  max_tokens: 4096
  temperature: 0.2
```

### Step 5 — Run the full batch

```bash
python run_batch.py
```

Or explicitly point to your config:

```bash
python run_batch.py --config config.yaml
```

This will process all **30 locations** with a live progress bar. For each location it:
1. **Regenerates** weather & household CSVs for that lat/lon
2. **Runs feature engineering** on electricity, weather, and household data
3. **Retrieves RAG passages** from `data/knowledge.txt`
4. **Calls the LLM** and saves the recommendation

Expected output:

```
════════════════════════════════════════════════════════════
  BATCH RUN – 30 locations
  Backend : ollama  |  Model: llama3.1:8b
  Outputs → /path/to/285_LLM_Workflow/batch_outputs
════════════════════════════════════════════════════════════

Locations: 100%|████████████████████| 30/30 [1:12:00<00:00, 144s/loc]

════════════════════════════════════════════════════════════
  BATCH COMPLETE
  Succeeded : 30 / 30
════════════════════════════════════════════════════════════

  Total time : 4320.0s
  Avg / loc  : 144.0s

  All outputs saved in: /path/to/285_LLM_Workflow/batch_outputs
```

### Batch output files

For each location (e.g. `Chula Vista`) two files are written to `batch_outputs/`:

| File | Description |
|------|-------------|
| `Chula_Vista_output.txt` | Full LLM PV sizing recommendation |
| `Chula_Vista_feature_outputs.txt` | Feature-engineering summary fed to the LLM |

### Dry run (skip LLM — just extract data & features)

Useful for testing the data pipeline without waiting for LLM inference:

```bash
python run_batch.py --dry-run
```

### Batch CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--config` | `config.yaml` | Base YAML config (lat/lon overridden per location) |
| `--locations` | `data/lats_longs_san_diego.csv` | CSV with `name,latitude,longitude` columns |
| `--output-dir` | `batch_outputs/` | Directory for all output files |
| `--dry-run` | `false` | Skip LLM inference; run data extraction + features only |

---

## Running a Single Location

To run the pipeline for one specific location:

```bash
python workflow.py --config config.yaml
```

The pipeline will:
1. **Regenerate CSVs** from the lat/lon in `config.yaml`
2. **Run feature engineering** across electricity, weather, and household data
3. **Build a RAG index** from `data/knowledge.txt` and retrieve relevant passages
4. **Assemble the final prompt** and call the LLM
5. **Save the response** to `outputs/output.txt`

A successful run looks like:

```
10:42:01 [INFO] workflow – Starting LLM workflow
10:42:01 [INFO] workflow –   Backend : ollama  |  Model: llama3.1:8b
10:42:01 [INFO] pipeline – Regenerating data CSVs for (32.7157, -117.1611) …
10:42:05 [INFO] pipeline – Running feature engineering on CSV data …
10:42:06 [INFO] pipeline – Building RAG index from data/knowledge.txt …
10:42:06 [INFO] pipeline – Building final prompt …
10:42:06 [INFO] pipeline – Running LLM inference …
...
10:43:15 [INFO] workflow – Done in 69.3 s – output saved to outputs/output.txt
```

The LLM response is printed to the terminal **and** saved to `outputs/output.txt`.

---

## Running via CLI Flags (no config file)

```bash
python workflow.py \
  --elec      data/electricity_data.csv \
  --household data/household_data.csv \
  --weather   data/weather_data.csv \
  --rag       data/knowledge.txt \
  --prompt    "How many PV panels should I install?" \
  --backend   ollama \
  --model     llama3.1:8b \
  --output    outputs/output.txt \
  --verbose
```

### All CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--config` | — | Path to YAML config (overrides all other flags) |
| `--elec` | `data/electricity_data.csv` | Electricity CSV path |
| `--household` | `data/household_data.csv` | Household CSV path |
| `--weather` | `data/weather_data.csv` | Weather CSV path |
| `--rag` | — | RAG knowledge text file |
| `--panels` | `10` | Assumed PV panel count |
| `--occupants` | `4` | Household occupants |
| `--sqm` | `150.0` | House area (m²) |
| `--price` | `0.31` | Electricity rate ($/kWh) |
| `--prompt` | — | User question / instruction |
| `--prompt-file` | — | Path to a `.txt` file with the prompt |
| `--backend` | `ollama` | `ollama` or `vllm` |
| `--model` | `llama3` | Model name |
| `--host` | `http://localhost:11434` | Backend server URL |
| `--max-tokens` | `2048` | Max output tokens |
| `--temperature` | `0.2` | Sampling temperature (0 = deterministic) |
| `--chunk-size` | `500` | Characters per RAG chunk |
| `--chunk-overlap` | `50` | Overlap between RAG chunks |
| `--top-k` | `3` | Number of RAG chunks to inject |
| `--output` | `output.txt` | Path to save the LLM response |
| `--verbose` | `false` | Enable DEBUG logging |

---

## Configuration Reference (`config.yaml`)

| Key | Default | Description |
|-----|---------|-------------|
| `feature_engineering.latitude/longitude` | `32.7157, -117.1611` | Location for data regeneration |
| `feature_engineering.electricity_csv` | `data/electricity_data.csv` | Electricity data path |
| `feature_engineering.household_csv` | `data/household_data.csv` | Household data path |
| `feature_engineering.weather_csv` | `data/weather_data.csv` | Weather data path |
| `feature_engineering.num_panels` | `10` | Assumed starting panel count |
| `feature_engineering.occupants` | `4` | Number of occupants |
| `feature_engineering.house_sqm` | `150.0` | House size (m²) |
| `feature_engineering.price_per_kwh` | `0.31` | Local electricity rate |
| `feature_engineering.num_evs` | `1` | Number of EVs owned |
| `feature_engineering.pv_budget` | `15000` | PV installation budget (USD) |
| `data.rag_file` | `data/knowledge.txt` | RAG knowledge base |
| `prompt` | *(see config.yaml)* | Question / instruction sent to the LLM |
| `system_prompt` | *(see config.yaml)* | System role context for the LLM |
| `llm.backend` | `ollama` | `ollama` \| `vllm` |
| `llm.model` | `llama3.1:8b` | Model name |
| `llm.host` | `http://localhost:11434` | Server URL |
| `llm.max_tokens` | `4096` | Max output tokens |
| `llm.temperature` | `0.2` | Sampling temperature |
| `rag.chunk_size` | `500` | Characters per RAG chunk |
| `rag.chunk_overlap` | `50` | Overlap between chunks |
| `rag.top_k` | `5` | Number of retrieved passages |
| `output.path` | `outputs/output.txt` | Where to save the response |

---

## Using vLLM (GPU) Instead of Ollama

If you have a CUDA GPU and want faster inference:

```bash
pip install vllm

python -m vllm.entrypoints.openai.api_server \
    --model meta-llama/Meta-Llama-3-8B-Instruct \
    --port 8000
```

Then in `config.yaml`:

```yaml
llm:
  backend: vllm
  model: meta-llama/Meta-Llama-3-8B-Instruct
  host: http://localhost:8000
```

---

## Outputs

| File | Description |
|------|-------------|
| `outputs/output.txt` | Full LLM response with PV sizing recommendation |
| `outputs/feature_outputs.txt` | Intermediate feature-engineering summary fed to the LLM |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Connection refused` on port 11434 | Run `ollama serve` in a separate terminal |
| `model not found` error | Run `ollama pull llama3.1:8b` first |
| Out of memory / slow generation | Use a smaller model: `ollama pull phi3` and update `config.yaml` |
| Empty or garbled output | Lower `temperature` to `0.1` or increase `max_tokens` |
| RAG returns irrelevant context | Increase `rag.top_k` or reduce `rag.chunk_size` |

---

## Extending

### Add a new LLM backend

1. Create `my_backend.py` with a class implementing `generate(prompt, system, max_tokens, temperature) → str`
2. Add the `elif backend == "my_backend"` branch in `pipeline.py → _get_backend()`

### Change the location / dataset

Update `feature_engineering.latitude` and `feature_engineering.longitude` in `config.yaml`. The pipeline will automatically regenerate all three CSVs for the new location on the next run.

---

## Tips

- Keep `temperature` at `0.1–0.3` for factual data analysis.
- Increase `rag.top_k` if your knowledge base is large.
- Use `--verbose` to see detailed step-by-step debug logs.
- The feature summary is saved to `outputs/feature_outputs.txt` — inspect it to understand what data the LLM received.
