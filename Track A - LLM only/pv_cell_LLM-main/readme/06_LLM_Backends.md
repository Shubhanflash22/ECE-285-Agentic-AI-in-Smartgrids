# Step 6: LLM Backends (`ollama_backend.py` + `vllm_backend.py`)

## Overview

The LLM Backend layer is the **inference engine** of the pipeline. It takes the fully assembled prompt from the Prompt Builder and sends it to a locally-hosted language model for generation. The system supports two interchangeable backends — **Ollama** (CPU-friendly, recommended) and **vLLM** (GPU-optimised) — both implementing the same `generate()` interface for seamless swapping.

---

## Architecture Position

```
                    ┌──────────────────────────┐
                    │   Final Prompt String     │
                    │   (~8,000 chars)          │
                    │   + System Prompt         │
                    └──────────┬───────────────┘
                               │
                    ┌──────────┴───────────┐
                    │                      │
                    ▼                      ▼
        ┌─────────────────┐    ┌─────────────────┐
        │  OLLAMA BACKEND  │    │   vLLM BACKEND   │
        │                 │    │                  │
        │  POST /api/chat │    │  POST /v1/chat/  │
        │  streaming      │    │  completions     │
        │  port 11434     │    │  port 8000       │
        └────────┬────────┘    └────────┬─────────┘
                 │                      │
                 └──────────┬───────────┘
                            │
                            ▼
                   LLM Response Text
                   (~2,000–4,000 chars)
```

---

## Files Involved

| File | Role | Lines of Code |
|------|------|---------------|
| `ollama_backend.py` | Ollama REST API client with streaming | 128 lines |
| `vllm_backend.py` | vLLM OpenAI-compatible client (SDK + fallback) | 115 lines |

---

## Common Interface

Both backends implement the exact same method signature:

```python
def generate(
    self,
    prompt: str,           # The assembled multi-section prompt
    system: str = "",      # System role instruction
    max_tokens: int = 2048,# Maximum output tokens
    temperature: float = 0.2,  # Sampling temperature
) -> str:                  # Returns the generated text
```

This allows the pipeline to switch backends with zero code changes — only `config.yaml` needs updating.

---

## Backend 1: Ollama (`OllamaBackend`)

### Setup

```bash
# Install Ollama
brew install ollama    # macOS

# Start server
ollama serve           # Runs on http://localhost:11434

# Pull model (one-time, ~4.7 GB)
ollama pull llama3.1:8b
```

### Configuration

| Parameter | Default | Production Value | Description |
|-----------|---------|-----------------|-------------|
| `host` | `http://localhost:11434` | `http://localhost:11434` | Ollama server URL |
| `model` | `llama3` | `llama3.1:8b` | Model tag (must be pulled first) |

### API Endpoint

**URL:** `POST {host}/api/chat`

### Request Payload

```json
{
  "model": "llama3.1:8b",
  "messages": [
    {"role": "system", "content": "You are an expert power grid data analyst..."},
    {"role": "user", "content": "## DATA CONTEXT...\n## KNOWLEDGE BASE...\n## QUESTION..."}
  ],
  "stream": true,
  "options": {
    "num_predict": 4096,
    "temperature": 0.2
  }
}
```

### Streaming Response Processing

Ollama returns **NDJSON** (newline-delimited JSON) streamed chunks:

```json
{"message":{"content":"## RECOMMENDATION"},"done":false}
{"message":{"content":" FOR PV"},"done":false}
{"message":{"content":" PANEL"},"done":false}
...
{"message":{},"done":true}
```

The backend collects all `content` fragments and joins them:

```python
parts = []
for raw_line in response.iter_lines():
    chunk = json.loads(raw_line)
    content = chunk.get("message", {}).get("content", "")
    if content:
        parts.append(content)
    if chunk.get("done"):
        break
full_response = "".join(parts).strip()
```

### Error Handling

| HTTP Status | Error | Recovery |
|-------------|-------|----------|
| Connection refused | `ConnectionError` | "Make sure Ollama is running (`ollama serve`)" |
| 404 | Model not found | "Pull it first: `ollama pull {model}`" |
| Other 4xx/5xx | `RuntimeError` | Includes server response text |

### Helper Method

```python
backend.list_models()  # → ["llama3.1:8b", "mistral", ...]
```

Calls `GET {host}/api/tags` to list all available models.

---

## Backend 2: vLLM (`VLLMBackend`)

### Setup

```bash
# Install vLLM (requires CUDA GPU)
pip install vllm

# Start server
python -m vllm.entrypoints.openai.api_server \
    --model meta-llama/Meta-Llama-3-8B-Instruct \
    --port 8000
```

### Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `host` | `http://localhost:8000` | vLLM server URL |
| `model` | `meta-llama/Meta-Llama-3-8B-Instruct` | HuggingFace model name |

### API Endpoint

**URL:** `POST {host}/v1/chat/completions`

Uses the OpenAI-compatible API format.

### Two Implementation Paths

The vLLM backend attempts two strategies:

#### Path A: OpenAI SDK (Preferred)

```python
from openai import OpenAI
client = OpenAI(base_url=f"{host}/v1", api_key="EMPTY")
response = client.chat.completions.create(
    model=model,
    messages=[...],
    max_tokens=max_tokens,
    temperature=temperature,
)
result = response.choices[0].message.content.strip()
```

#### Path B: Raw HTTP Requests (Fallback)

If the `openai` package is not installed:

```python
import requests
payload = {
    "model": model,
    "messages": [...],
    "max_tokens": max_tokens,
    "temperature": temperature,
}
r = requests.post(f"{host}/v1/chat/completions", json=payload)
result = r.json()["choices"][0]["message"]["content"].strip()
```

---

## Backend Comparison

| Metric | Ollama | vLLM |
|--------|--------|------|
| **Hardware** | CPU or GPU | GPU required (CUDA) |
| **RAM needed** | ~8 GB (llama3.1:8b) | ~16 GB VRAM |
| **Inference time** | ~60–180 s/query | ~10–30 s/query |
| **Streaming** | ✅ Yes (NDJSON) | ❌ Single response |
| **Model format** | GGUF quantised | Full HuggingFace weights |
| **API compatibility** | Ollama-native | OpenAI-compatible |
| **Setup complexity** | Very easy | Moderate (CUDA, vllm install) |
| **Production use** | ✅ Used for 30-location batch | Available as alternative |

---

## Production Performance (Ollama, 30-location batch)

| Metric | Value |
|--------|-------|
| Model | `llama3.1:8b` |
| Max tokens | 4,096 |
| Temperature | 0.2 |
| Avg response time | ~144 s/location |
| Total batch time | ~4,320 s (72 min) |
| Avg response length | ~2,500–4,000 chars |
| Output format | Markdown with sections and bullet points |

---

## Sample LLM Response (San Diego)

The LLM produces structured PV sizing recommendations:

```markdown
## RECOMMENDATION FOR PV PANEL INSTALLATION

### KEY TRENDS AND SEASONAL PATTERNS
*   The household's electricity consumption is relatively stable
    throughout the year (Winter/Summer ratio: 0.94)
*   Average daily consumption: 53.76 kWh
*   Peak weekly max load: 7.79 kW

### PV PANEL SIZING
*   To offset 100% of consumption: ~128 panels needed
*   With EV charging load: ~150 panels
*   Budget-constrained maximum: 31 panels ($15,000 budget)

### PAYBACK PERIOD AND ROI
*   Break-even: ~10.03 years (budget-constrained)
*   ROI (25 yr): 132.15%
*   Expected annual savings: $1,480.42

### RISKS AND CAVEATS
*   Nighttime load ratio: 70.23%
*   Sunlight consistency CV: 0.3141
*   Battery storage may be advisable
```

---

## Switching Backends

To switch from Ollama to vLLM, only `config.yaml` needs to change:

```yaml
# Before (Ollama)
llm:
  backend: ollama
  model: llama3.1:8b
  host: http://localhost:11434

# After (vLLM)
llm:
  backend: vllm
  model: meta-llama/Meta-Llama-3-8B-Instruct
  host: http://localhost:8000
```

---

## Dependencies

### Ollama Backend
- `requests>=2.31.0` — HTTP client for REST API

### vLLM Backend
- `openai>=1.0.0` (preferred) — OpenAI-compatible SDK
- `requests>=2.31.0` (fallback) — Raw HTTP client
