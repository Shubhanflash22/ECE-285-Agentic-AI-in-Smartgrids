"""
LLM Workflow Orchestrator
=========================
Runs feature engineering on 3 CSV files → RAG text file → LLM (Ollama / vLLM) → Output

Usage:
    python workflow.py --config config.yaml
    python workflow.py --elec data/electricity_data.csv \
                       --household data/household_data.csv \
                       --weather data/weather_data.csv \
                       --rag data/knowledge.txt \
                       --prompt "How many PV panels?" \
                       --backend ollama --model llama3
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import yaml

from pipeline import Pipeline
from config import WorkflowConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("workflow")


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="LLM Workflow: CSV × RAG → LLM → Output",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--config", type=str, help="Path to YAML config file (overrides all other flags)")

    # Data sources (feature engineering)
    g = p.add_argument_group("Data sources")
    g.add_argument("--elec",      type=str, default="data/electricity_data.csv", help="Electricity CSV")
    g.add_argument("--household", type=str, default="data/household_data.csv",   help="Household CSV")
    g.add_argument("--weather",   type=str, default="data/weather_data.csv",     help="Weather CSV")
    g.add_argument("--rag",       type=str, help="Path to RAG knowledge text file")
    g.add_argument("--panels",    type=int,   default=10,    help="Assumed PV panel count")
    g.add_argument("--occupants", type=int,   default=4,     help="Household occupants")
    g.add_argument("--sqm",       type=float, default=150.0, help="House area m²")
    g.add_argument("--price",     type=float, default=0.31,  help="Electricity $/kWh")

    # Prompt
    p.add_argument("--prompt", type=str, help="User prompt / question")
    p.add_argument("--prompt-file", type=str, help="Path to a text file containing the prompt")

    # LLM backend
    b = p.add_argument_group("LLM backend")
    b.add_argument("--backend", choices=["ollama", "vllm"], default="ollama")
    b.add_argument("--model", type=str, default="llama3", help="Model name / path")
    b.add_argument("--host",  type=str, default="http://localhost:11434", help="Ollama/vLLM host URL")
    b.add_argument("--max-tokens", type=int, default=2048)
    b.add_argument("--temperature", type=float, default=0.2)

    # RAG settings
    r = p.add_argument_group("RAG settings")
    r.add_argument("--chunk-size",    type=int, default=500,  help="Characters per RAG chunk")
    r.add_argument("--chunk-overlap", type=int, default=50,   help="Overlap between chunks")
    r.add_argument("--top-k",         type=int, default=3,    help="Top-k RAG chunks to retrieve")

    # Output
    o = p.add_argument_group("Output")
    o.add_argument("--output", type=str, default="output.txt", help="Path to save the LLM response")
    o.add_argument("--verbose", action="store_true")

    return p


def load_config(args) -> WorkflowConfig:
    """Build a WorkflowConfig from CLI args or YAML file."""
    if args.config:
        with open(args.config) as f:
            raw = yaml.safe_load(f)
        return WorkflowConfig.from_dict(raw)

    prompt_text = args.prompt or ""
    if args.prompt_file:
        prompt_text = Path(args.prompt_file).read_text(encoding="utf-8")

    return WorkflowConfig(
        electricity_csv=args.elec,
        household_csv=args.household,
        weather_csv=args.weather,
        fe_num_panels=args.panels,
        fe_occupants=args.occupants,
        fe_house_sqm=args.sqm,
        fe_price_per_kwh=args.price,
        rag_path=args.rag,
        prompt=prompt_text,
        backend=args.backend,
        model=args.model,
        host=args.host,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        top_k=args.top_k,
        output_path=args.output,
    )


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = load_config(args)
    config.validate()

    logger.info("Starting LLM workflow")
    logger.info("  Backend : %s  |  Model: %s", config.backend, config.model)
    logger.info("  Feature-engineering CSVs: %s, %s, %s",
                config.electricity_csv, config.household_csv, config.weather_csv)
    logger.info("  RAG file : %s", config.rag_path)

    t0 = time.perf_counter()
    pipeline = Pipeline(config)
    result = pipeline.run()
    elapsed = time.perf_counter() - t0

    # ── Save output ──
    out_path = Path(config.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result, encoding="utf-8")

    logger.info("Done in %.1f s – output saved to %s", elapsed, out_path)
    print("\n" + "═" * 60)
    print(result)
    print("═" * 60)


if __name__ == "__main__":
    main()
