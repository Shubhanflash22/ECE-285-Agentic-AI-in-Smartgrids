"""
pipeline.py – Main orchestration:
    feature_engineering → RAG → PromptBuilder → LLM → output.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from config import WorkflowConfig
from data_extractor import regenerate_all
from feature_engineering import extract_all_features, format_for_llm
from retriever import RAGRetriever
from prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


class Pipeline:
    """
    High-level workflow:

        feature_engineering ──┐
                              ├──► PromptBuilder ──► LLM Backend ──► output text
        RAGRetriever ─────────┘
    """

    def __init__(self, config: WorkflowConfig):
        self.config = config
        self._backend = None

    # ─────────────────────────────────────────────────────────
    # Public
    # ─────────────────────────────────────────────────────────

    def run(self) -> str:
        cfg = self.config

        # ── 0. Regenerate data CSVs from lat/lon ─────────────
        logger.info("Regenerating data CSVs for (%.4f, %.4f) …",
                     cfg.fe_latitude, cfg.fe_longitude)
        regenerate_all(
            latitude=cfg.fe_latitude,
            longitude=cfg.fe_longitude,
            weather_csv=cfg.weather_csv,
            household_csv=cfg.household_csv,
            electricity_csv=cfg.electricity_csv,
        )

        # ── 1. Feature engineering ────────────────────────────
        logger.info("Running feature engineering on CSV data …")
        df_elec = pd.read_csv(cfg.electricity_csv)
        df_household = pd.read_csv(cfg.household_csv)
        df_weather = pd.read_csv(cfg.weather_csv)
        logger.info("  Loaded: %s, %s, %s",
                    cfg.electricity_csv, cfg.household_csv, cfg.weather_csv)

        features = extract_all_features(
            df_elec, df_weather, df_household,
            num_panels=cfg.fe_num_panels,
            occupants=cfg.fe_occupants,
            house_sqm=cfg.fe_house_sqm,
            price_per_kwh=cfg.fe_price_per_kwh,
            num_evs=cfg.fe_num_evs,
            pv_budget=cfg.fe_pv_budget,
        )
        feature_context = format_for_llm(features)

        # Save feature-engineered summary
        fe_out = Path(cfg.feature_output_path)
        fe_out.parent.mkdir(parents=True, exist_ok=True)
        fe_out.write_text(feature_context, encoding="utf-8")
        logger.info("  Feature summary saved to %s (%d chars)", fe_out, len(feature_context))

        # ── 2. Build RAG context ──────────────────────────────
        rag_context: Optional[str] = None
        if cfg.rag_path:
            logger.info("Building RAG index from %s …", cfg.rag_path)
            retriever = RAGRetriever(
                chunk_size=cfg.chunk_size,
                chunk_overlap=cfg.chunk_overlap,
            )
            retriever.index(cfg.rag_path)
            rag_context = retriever.retrieve(cfg.prompt, top_k=cfg.top_k)
            logger.info("  Retrieved %d RAG chunk(s)", cfg.top_k)

        # ── 3. Build final prompt ─────────────────────────────
        logger.info("Building final prompt …")
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
        logger.debug("Prompt length: %d chars", len(final_prompt))

        # ── 4. Call LLM ───────────────────────────────────────
        logger.info("Calling LLM backend: %s / %s …", cfg.backend, cfg.model)
        backend = self._get_backend()
        response = backend.generate(
            prompt=final_prompt,
            system=cfg.system_prompt,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
        )

        return response

    # ─────────────────────────────────────────────────────────
    # Private
    # ─────────────────────────────────────────────────────────

    def _get_backend(self):
        """Lazy-initialise and cache the chosen LLM backend."""
        if self._backend is None:
            cfg = self.config
            if cfg.backend == "ollama":
                from ollama_backend import OllamaBackend
                self._backend = OllamaBackend(host=cfg.host, model=cfg.model)

            elif cfg.backend == "vllm":
                from vllm_backend import VLLMBackend
                self._backend = VLLMBackend(host=cfg.host, model=cfg.model)

            else:
                raise ValueError(f"Unknown backend: {cfg.backend}")

        return self._backend
