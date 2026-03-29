# ECE 285: SolarInvestAgent — Agentic AI for Home Solar Investment ☀️⚡
A hybrid intelligent decision-support system that optimizes residential Photovoltaic (PV) and Battery Energy Storage System (BESS) sizing by coupling a Mixed-Integer Linear Programming (MILP) solver with an LLM orchestration layer. This project was developed for ECE 285 (Special Topics: Agentic AI and LLM for Smart Grids) at UC San Diego.

## Table of Contents

* [Project Overview](#project-overview)
* [Dataset](#dataset)
* [Features](#features)
* [Installation](#installation)
* [Usage](#usage)
* [Methods](#methods)
* [Results](#results)
* [Future Work](#future-work)
* [Citation](#citation)
* [License](#license)

---

## Project Overview

This repository contains the final project for ECE 285 at UC San Diego. The project builds **SolarInvestAgent**, an agentic AI system that takes household inputs (location, load profile, tariff plan, EV count, roof dimensions, budget) and outputs a mathematically grounded PV-BESS sizing recommendation with projected NPV, payback period, and annual savings.

The core motivation is that existing residential solar sizing workflows are either technically rigorous but inaccessible to non-experts, or LLM-driven but heuristic and unverifiable. SolarInvestAgent closes this gap by embedding a constrained MILP optimizer within a LangGraph agentic loop — the LLM handles natural-language interaction and explanation while all numerical decisions are delegated to a deterministic solver, enforcing feasibility by construction.

Key implementations include:

* A HiGHS-based MILP optimizer implementing the full PV-BESS sizing formulation with hourly power balance, SoC dynamics, charge/discharge exclusivity, roof area, and budget constraints
* A stochastic household load model with geographic, demographic, and EV-charging factors for San Diego County
* A 75+ feature engineering pipeline covering solar potential, financial metrics, and risk indicators
* A LangGraph-orchestrated agentic pipeline (Track B) with tool calls to the MILP solver, Open-Meteo irradiance API, and a retrieval-augmented knowledge base
* A three-stage validation loop (syntactic → schema → logical) with automatic repair on failure
* A direct LLM-only baseline (Track A) for benchmarking

**Team**: Shubhan Mital, Manasvin Surya Balakrishnan Jaikannan, Sri Mihir Devapi Ungarala

---

## Dataset

* **Weather Data**: 5 years of historical hourly irradiance, temperature, and cloud cover from the Open-Meteo API across 30 San Diego County locations
* **Electricity Demand**: Regional EIA load data, temporally aligned and scaled to household level via a stochastic generative model
* **Tariff Schedules**: SDG&E TOU-DR tariff (on-peak: $0.599/kWh, off-peak: $0.528/kWh, super off-peak: $0.450/kWh), NEM 3.0 export compensation ($0.05–0.08/kWh)
* **Hardware Catalog**: 9 PV panel brands (REC Group, Aiko Solar, Canadian Solar, Maxeon, etc.) with efficiency (20.2–24.3%), cost ($0.16–$3.50/Wp), and rated power
* **Benchmark Scenarios**: 20 scenarios for unconstrained and budget-constrained evaluation; 54-scenario grid sweep (EVs, occupants, daytime presence); 243-scenario sweep (roof dimensions, budget, panel brand)

---

## Features

**Track A — LLM-Only Baseline**
* Structured hierarchical prompt with feature-engineered data context, retrieved panel/tariff knowledge, and an 8-step reasoning workflow
* Direct LLM output of panel count, annual production, cost savings, payback, ROI, and caveats — no solver invoked
* Hard constraints (budget, roof area) stated in prompt but compliance depends solely on generative behavior

**Track B — SolarInvestAgent (Agentic)**
* MILP optimizer (HiGHS via highspy) jointly solves for panel count (integer) and battery option (binary) minimizing annualized lifecycle cost
* Objective: annualized PV capex + battery capex + PV-weighted import cost − NEM export credit
* Constraints: hourly power balance over 8,760 timesteps, SoC bounds [10%–100%], charge/discharge exclusivity, roof area cap (~1.8m²/panel), budget feasibility
* Financial model: NPV and payback computed via deterministic multi-year cash-flow with degradation (0.5%/yr), utility inflation (6%/yr), ITC (30%), and O&M ($350–500/yr)
* Three-stage output validation (JSON syntax → schema bounds → domain logic) with automatic repair loop
* Two recommendation tiers per query: **optimal** (efficiency-driven) and **recommended** (budget- and area-constrained)
* Gradio chatbot interface with stateful multi-turn conversation and tool-triggered reasoning

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/Shubhanflash22/ECE-285-SolarInvestAgent.git
cd ECE-285-SolarInvestAgent

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install numpy pandas scipy highspy langchain langgraph gradio openai requests

# 4. Set your API keys
export OPENAI_API_KEY=your_key_here   # or equivalent for Grok
```

---

## Usage

1. **Generate data**: Run the data pipeline to fetch weather and load CSVs for your target locations
2. **Run Track A (LLM baseline)**:
   ```bash
   python pipeline_track_a.py --location "La Jolla" --budget 15000 --roof_area 7.5 --evs 0
   ```
3. **Run Track B (SolarInvestAgent)**:
   ```bash
   python pipeline_track_b.py --location "La Jolla" --budget 15000 --roof_area 7.5 --evs 0
   ```
4. **Launch the chatbot**:
   ```bash
   python app.py  # Opens Gradio interface at localhost:7860
   ```
5. **Run benchmark evaluation**:
   ```bash
   python evaluate.py --scenarios benchmark_20.json
   ```

---

## Methods

**Problem Formulation**

The agent minimizes total electricity lifecycle cost over a planning horizon:

min Ctotal = CPV + CBESS + CO&M + Σt [Pgrid_buy(t)·λTOU(t) − Pgrid_sell(t)·λNEM(t)]

subject to hourly power balance, SoC dynamics (ηch=ηdch=0.975, C-rate=0.5), SoC bounds [10%–100%], charge/discharge binary exclusivity, export cap (≤ available PV), roof area, and budget constraints.

**Stochastic Household Load Model**

Household load is synthesized from regional EIA data scaled by geographic (coastal/inland, latitude, urban proximity), demographic (household size, EV charging overlay at 7.2kW/EV), and daytime occupancy factors, with stochastic micro-grid variability — enabling realistic load profiles for any San Diego location without measured household data.

**Feature Engineering**

75+ domain-specific features are computed per location including solar potential (annual irradiance, peak sun hours), financial metrics (payback, NPV, ROI sensitivity at ±10% price perturbation), and risk indicators (coefficient of variation of weekly load and irradiance combined into a unified risk score).

**Retrieval-Augmented Context**

Both tracks share a RAG layer that injects domain knowledge on PV panel datasheets, battery specifications, tariff schedules, and installation practices into the reasoning context, grounding LLM responses in factual hardware and pricing data.

**Agentic Decision Loop (Track B)**

The LangGraph pipeline follows a perception–reasoning–action loop. Each session maintains full conversation history (no truncation). On receiving user inputs, the agent: (1) fetches live irradiance from Open-Meteo, (2) retrieves household load from EIA data, (3) pulls the applicable tariff schedule, (4) calls the MILP optimizer, (5) validates the output through the three-stage pipeline, and (6) synthesizes a grounded natural-language recommendation. Follow-up turns extend context without re-invoking the MILP, separating offline deterministic computation from online LLM interaction.

**Evaluation**

Four configurations are evaluated against a deterministic HiGHS solver as ground truth across N=20 benchmark scenarios using: panel-count RMSE/MAE, capex MAE/MAPE, and budget feasibility (fraction of scenarios where predicted CAPEX ≤ stated budget).

---

## Results

| Track | Panels RMSE | Panels MAE | Capex MAE ($) | Capex MAPE (%) | Budget Feasibility |
|---|---|---|---|---|---|
| Baseline (HiGHS GT) | 0.00 | 0.00 | 0 | 0% | 65.0% (unconstrained) |
| Track A (LLM-only) | 277.35 | 186.85 | 60,585 | 10,468.5% | 25.0% |
| **Track B1 (Agentic, reasoning)** | **20.05** | **14.10** | **26,902** | **1,365.2%** | **40.0%** |
| Track B2 (Agentic, non-reasoning) | 20.05 | 14.10 | 26,902 | 1,365.2% | 40.0% |

*Unconstrained sizing objective, N=20 scenarios.*

| Track | Panels RMSE | Capex MAE ($) | Budget Feasibility |
|---|---|---|---|
| Track A (LLM-only) | 86.44 | 18,220 | 85.0% |
| **Track B1/B2 (Agentic)** | **37.80** | **7,670** | 75.0% |

*Budget-constrained sizing objective, N=20 scenarios.*

**Key takeaways:**

* **Agentic beats LLM-only on accuracy**: Panel count RMSE is **13.8× lower** (20.05 vs. 277.35) and capex MAE is **2.3× lower** ($26,902 vs. $60,585) in unconstrained sizing — the MILP solver eliminates the systematic over-estimation that plagues direct LLM inference
* **LLMs hallucinate battery need**: Without a rigorous optimizer, Track A recommends batteries under stepwise tariffs where they are economically suboptimal; the MILP correctly drives BESS capacity to zero under SPT and positive under TOU/RTP
* **Reasoning mode doesn't change numbers**: Tracks B1 (reasoning) and B2 (non-reasoning) produce identical panel counts and capex on all 20 scenarios — the chain-of-thought step improves explanation quality but does not alter the MILP solution
* **Feasibility is enforced by construction**: The three-stage validation-repair loop ensures all agent outputs pass budget, roof area, and power-balance checks before delivery — something prompt-only approaches cannot guarantee
* **Sensitivity is monotone and physically meaningful**: Panel count scales near-linearly with roof area; each additional EV produces a consistent step increase in recommended capacity; location has negligible variance across the similar San Diego solar profiles

**Example agent trajectory** (La Jolla, budget $15,000, roof 7.5m², 1 occupant, no EVs):
- MILP output: 1 panel + BESS, CAPEX $14,199, annual savings $892, payback ~16 years
- Validation: Schema OK; CAPEX ≤ budget; SoC bounds [10%–100%] satisfied; power balance feasible over 8,760 hours
- Agent response: Grounded natural-language recommendation with tariff-specific reasoning

---

## Future Work

* **Multi-year stochastic optimization**: Replace the single-year MILP with a multi-stage stochastic program that re-optimizes annually over a 10–25 year horizon with dynamic hardware upgrade planning and non-linear degradation curves
* **Live tariff and incentive tracking**: Automated scraping of TOU rate updates and federal/state incentive changes, eliminating the need for manual parameter updates
* **Expanded building types**: Generalize from single-family residential to apartment complexes and small commercial buildings with shared battery dispatch, demand-charge tariffs, and community solar allocation
* **New energy markets**: Extend to deregulated markets such as Texas (ERCOT) with real-time pricing and distinct grid interconnection policies
* **Multi-agent reinforcement learning**: Replace the single deterministic solver with autonomous agents representing individual households, grid operators, and energy retailers negotiating dispatch schedules under non-stationary price signals

---

## Citation

If you use this work, please cite:

```bibtex
@software{ECE-285-SolarInvestAgent,
  author = {Shubhan Mital and Manasvin Surya Balakrishnan Jaikannan and Sri Mihir Devapi Ungarala},
  title  = {SolarInvestAgent: Agentic AI for Home Solar Investment},
  year   = {2026},
  url    = {https://github.com/Shubhanflash22/ECE-285-SolarInvestAgent.git}
}
```

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
