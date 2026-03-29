# Step 5: Prompt Builder (`prompt_builder.py`)

## Overview

The Prompt Builder is the **assembly step** that takes three distinct information streams — the feature-engineered data summary, the RAG knowledge passages, and the user's question — and merges them into a single, well-structured prompt string ready for LLM consumption. It also handles prompt length management with a hard character cap and intelligent truncation.

---

## Architecture Position

```
┌──────────────────────────┐  ┌──────────────────────────┐
│  Feature-Engineered       │  │  RAG Knowledge            │
│  Summary (~4,000 chars)   │  │  Passages (~2,500 chars)  │
└───────────┬──────────────┘  └───────────┬──────────────┘
            │                              │
            └──────────┬───────────────────┘
                       │
                       ▼
          ┌──────────────────────────┐
          │      PROMPT BUILDER       │
          │                          │
          │  system_prompt (role)    │
          │  + feature_context       │
          │  + rag_context           │
          │  + user_prompt           │
          │  + truncation logic      │
          │                          │
          │  max_chars = 32,000      │
          └──────────┬───────────────┘
                     │
                     ▼
            Final Prompt String
            (~7,000–10,000 chars)
```

---

## File Details

| File | Role | Lines of Code |
|------|------|---------------|
| `prompt_builder.py` | Prompt assembly and truncation | 122 lines |

---

## PromptBuilder Class

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `system_prompt` | `str` | `""` | System-level instruction for the LLM (sent separately via backend) |
| `max_chars` | `int` | `32,000` | Hard cap on total prompt length in characters |

### Build Method Signature

```python
def build(
    self,
    user_prompt: str,              # The user's question/instruction
    feature_context: str | None,   # Feature-engineered summary
    rag_context: str | None,       # Retrieved knowledge passages
) -> str:
```

---

## Prompt Structure — Final Output

The assembled prompt has **3 clearly delineated sections** using Markdown headings:

```markdown
## DATA CONTEXT (Feature-Engineered Summary)
The following is a pre-computed, feature-engineered summary
derived from the electricity, household, and weather datasets.
Use these numbers to answer the question accurately.

================================================================
  FEATURE-ENGINEERED SUMMARY FOR LLM
================================================================
📊 ELECTRICITY CONSUMPTION SUMMARY
  Annual household consumption    : 19,624.05 kWh
  Avg daily consumption           : 53.76 kWh
  ...
☀️ SOLAR POTENTIAL SUMMARY
  Avg weekly irradiance           : 219.82 W/m²
  ...
⚡ PV SIZING & FINANCIAL ANALYSIS
  Est annual production / panel    : 154.05 kWh
  ...
────────────────────────────────────────────────────────────────

## KNOWLEDGE BASE (retrieved passages)
The following passages were retrieved from the knowledge base
and are relevant to the user's question.

[Passage 1]
Solar Panel Installation Cost – San Diego (2025 Range)
Average cost per watt installed: 2.70 to 3.30 USD per watt
...

[Passage 2]
SDG&E Considerations
Under current net billing rules, excess solar energy...
...
────────────────────────────────────────────────────────────────

## QUESTION / INSTRUCTION
You have been given a pre-computed feature-engineered summary
of electricity consumption, weather / solar potential, household
metrics, PV sizing analysis, and risk factors...

Task:
1. Review the feature-engineered data summary...
2. Identify key trends, seasonal patterns, and anomalies...
3. The household owns 1 EV(s)...
4. The household has a budget of $15,000 USD...
5. Determine the optimal number of PV panels...
6. Estimate the cost savings and payback period...
7. Comment on risks...

Output: A clear recommendation with the number of PV panels...

Please provide a thorough, accurate response based on the data
summary and knowledge passages above. Cite specific figures or
passages where relevant.
```

---

## Section Separators

Each section is separated by a visual divider:

```python
SEPARATOR = "─" * 60
```

This produces: `────────────────────────────────────────────────────────────────`

---

## Prompt Variable Resolution

Before the prompt is built, `pipeline.py` resolves dynamic variables in the user prompt:

```python
resolved_prompt = cfg.prompt.format(
    num_evs=cfg.fe_num_evs,           # e.g., 1
    pv_budget=f"{cfg.fe_pv_budget:,.0f}",  # e.g., "15,000"
)
```

This replaces `{num_evs}` → `1` and `{pv_budget}` → `$15,000` in the prompt template from `config.yaml`.

---

## Truncation Logic

If the total prompt exceeds `max_chars` (default 32,000), the builder applies intelligent truncation:

### Truncation Priority

| Priority | Component | Action |
|----------|-----------|--------|
| 1 (Preserved) | `user_prompt` | Never truncated |
| 2 (Preserved) | `rag_context` | Never truncated |
| 3 (Truncated) | `feature_context` | Truncated to fit within budget |

### Budget Calculation

```python
overhead = len(user_prompt) + len(rag_context) + 2000  # 2K buffer for headers/separators
budget = max(max_chars - overhead, 2000)               # Minimum 2K for features

if len(feature_context) > budget:
    feature_context = feature_context[:budget] + "\n… [truncated]"
```

### Typical Prompt Sizes

| Component | Typical Size | % of Total |
|-----------|-------------|------------|
| Feature context | ~4,000 chars | ~50% |
| RAG context (5 passages) | ~2,500 chars | ~30% |
| User prompt | ~1,000 chars | ~12% |
| Headers, separators, instructions | ~600 chars | ~8% |
| **Total** | **~8,100 chars** | **100%** |

Since the typical total (~8K chars) is well under the 32K limit, **truncation rarely activates** in normal operation.

---

## System Prompt (Sent Separately)

The system prompt is **not** embedded in the final prompt string. It is passed separately to the LLM backend via the `system` parameter:

```python
backend.generate(
    prompt=final_prompt,          # The assembled multi-section string
    system=cfg.system_prompt,      # Sent as system role message
    max_tokens=cfg.max_tokens,
    temperature=cfg.temperature,
)
```

**Production system prompt:**
```
You are an expert power grid data analyst who can suggest the number
of PV cells that can be installed in any house based on weather,
electricity and household_data and is able to reason well on why
the recommendation is made. Be precise, cite numbers, and structure
your answer with clear sections and bullet points.
```

---

## Design Principles

1. **Explicit context labelling:** Each section has a clear `## HEADING` and explanatory preamble so the LLM understands what each block represents.
2. **Feature context first:** Numerical data comes before knowledge passages, giving the LLM a data-first analytical frame.
3. **Action-oriented closing:** The final line explicitly asks the LLM to cite figures and use the context, reducing hallucination.
4. **Graceful degradation:** If either `feature_context` or `rag_context` is `None`, that section is simply omitted — the prompt still works.

---

## Dependencies

- Python `typing` (stdlib) — `List`, `Optional` type hints
- No external dependencies
