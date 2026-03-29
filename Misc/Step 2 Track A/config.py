"""
core/config.py – Centralised configuration for the LLM workflow.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class WorkflowConfig:
    # ── Feature-engineering data sources ───────────────────────
    # Location – drives data extraction (weather + household)
    fe_latitude: float = 32.7157
    fe_longitude: float = -117.1611

    electricity_csv: Optional[str] = "data/electricity_data.csv"
    household_csv: Optional[str] = "data/household_data.csv"
    weather_csv: Optional[str] = "data/weather_data.csv"
    fe_num_panels: int = 10
    fe_occupants: int = 4
    fe_house_sqm: float = 150.0
    fe_price_per_kwh: float = 0.31
    fe_num_evs: int = 0           # Number of EVs the household owns
    fe_pv_budget: float = 10000.0 # Budget for PV installation (USD)

    # ── RAG ───────────────────────────────────────────────────
    rag_path: Optional[str] = None      # knowledge text file for RAG

    # ── Prompt ────────────────────────────────────────────────
    prompt: str = ""

    # ── LLM backend ───────────────────────────────────────────
    backend: str = "ollama"             # "ollama" | "vllm"
    model: str = "llama3"
    host: str = "http://localhost:11434"
    max_tokens: int = 2048
    temperature: float = 0.2

    # ── RAG settings ──────────────────────────────────────────
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 3

    # ── Output ────────────────────────────────────────────────
    output_path: str = "output.txt"
    feature_output_path: str = "outputs/feature_outputs.txt"

    # ── Extra / advanced ──────────────────────────────────────
    system_prompt: str = (
        "You are a helpful data analyst. "
        "Use the provided data context and knowledge base to answer accurately."
    )

    # ─────────────────────────────────────────────────────────

    def validate(self):
        """Raise ValueError for obvious misconfiguration."""
        valid_backends = {"ollama", "vllm"}
        if self.backend not in valid_backends:
            raise ValueError(f"backend must be one of {valid_backends}, got '{self.backend}'")

        # CSV files are regenerated from lat/lon on each run, so we
        # no longer require them to exist before the pipeline starts.

        if self.rag_path and not Path(self.rag_path).is_file():
            raise FileNotFoundError(f"RAG file not found: {self.rag_path}")

        if not self.prompt.strip():
            raise ValueError("prompt is empty – please provide a prompt via --prompt or --prompt-file")

    # ─────────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowConfig":
        """Construct from a parsed YAML dict."""
        fe   = d.get("feature_engineering", {})
        data = d.get("data", {})
        llm  = d.get("llm", {})
        rag  = d.get("rag", {})
        out  = d.get("output", {})

        return cls(
            fe_latitude=fe.get("latitude", 32.7157),
            fe_longitude=fe.get("longitude", -117.1611),
            electricity_csv=fe.get("electricity_csv", "data/electricity_data.csv"),
            household_csv=fe.get("household_csv", "data/household_data.csv"),
            weather_csv=fe.get("weather_csv", "data/weather_data.csv"),
            fe_num_panels=fe.get("num_panels", 10),
            fe_occupants=fe.get("occupants", 4),
            fe_house_sqm=fe.get("house_sqm", 150.0),
            fe_price_per_kwh=fe.get("price_per_kwh", 0.31),
            fe_num_evs=fe.get("num_evs", 0),
            fe_pv_budget=fe.get("pv_budget", 10000.0),
            rag_path=data.get("rag_file"),
            prompt=d.get("prompt", ""),
            backend=llm.get("backend", "ollama"),
            model=llm.get("model", "llama3"),
            host=llm.get("host", "http://localhost:11434"),
            max_tokens=llm.get("max_tokens", 2048),
            temperature=llm.get("temperature", 0.2),
            chunk_size=rag.get("chunk_size", 500),
            chunk_overlap=rag.get("chunk_overlap", 50),
            top_k=rag.get("top_k", 3),
            output_path=out.get("path", "output.txt"),
            feature_output_path=out.get("feature_path", "outputs/feature_outputs.txt"),
            system_prompt=d.get(
                "system_prompt",
                "You are a helpful data analyst. "
                "Use the provided data context and knowledge base to answer accurately.",
            ),
        )
