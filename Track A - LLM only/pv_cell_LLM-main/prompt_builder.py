"""
prompt_builder.py – Assembles the feature-engineered data summary, RAG passages,
and the user prompt into a single well-structured prompt for the LLM.
"""

from __future__ import annotations

from typing import List, Optional


SEPARATOR = "─" * 60


class PromptBuilder:
    """
    Builds the final prompt by combining:
      1. Feature-engineered data summary (from feature_engineering.py)
      2. RAG knowledge passages
      3. The user's question / instruction

    Parameters
    ----------
    system_prompt : The top-level instruction for the model.
    max_chars     : Hard cap on total prompt length (characters).
                    If exceeded, the feature context is truncated.
    """

    def __init__(
        self,
        system_prompt: str = "",
        max_chars: int = 32_000,
    ):
        self.system_prompt = system_prompt
        self.max_chars     = max_chars

    # ─────────────────────────────────────────────────────────

    def build(
        self,
        user_prompt: str,
        feature_context: Optional[str] = None,
        rag_context:     Optional[str] = None,
    ) -> str:
        """
        Returns the fully assembled prompt string.

        Parameters
        ----------
        user_prompt     : The raw user question or instruction.
        feature_context : Pre-computed feature-engineered summary string.
        rag_context     : Retrieved knowledge passages (from RAGRetriever).
        """
        sections: List[str] = []

        # ── Feature-engineered data ───────────────────────────
        if feature_context:
            sections.append("## DATA CONTEXT (Feature-Engineered Summary)")
            sections.append(
                "The following is a pre-computed, feature-engineered summary "
                "derived from the electricity, household, and weather datasets. "
                "Use these numbers to answer the question accurately."
            )
            sections.append("")
            sections.append(feature_context)
            sections.append(SEPARATOR)

        # ── RAG knowledge ─────────────────────────────────────
        if rag_context:
            sections.append("")
            sections.append("## KNOWLEDGE BASE (retrieved passages)")
            sections.append(
                "The following passages were retrieved from the knowledge base "
                "and are relevant to the user's question."
            )
            sections.append("")
            sections.append(rag_context)
            sections.append(SEPARATOR)

        # ── User question ─────────────────────────────────────
        sections.append("")
        sections.append("## QUESTION / INSTRUCTION")
        sections.append(user_prompt.strip())
        sections.append("")
        sections.append(
            "Please provide a thorough, accurate response based on the data "
            "summary and knowledge passages above. Cite specific figures or "
            "passages where relevant."
        )

        full_prompt = "\n".join(sections)

        # ── Hard length cap ───────────────────────────────────
        if len(full_prompt) > self.max_chars:
            full_prompt = self._truncate(
                full_prompt,
                user_prompt,
                feature_context,
                rag_context,
            )

        return full_prompt

    # ─────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────

    def _truncate(
        self,
        full_prompt: str,
        user_prompt: str,
        feature_context: Optional[str],
        rag_context:     Optional[str],
    ) -> str:
        """
        Truncate feature context to fit within max_chars,
        preserving the user prompt and RAG context in full.
        """
        overhead = len(user_prompt) + (len(rag_context) if rag_context else 0) + 2000
        budget = max(self.max_chars - overhead, 2000)

        truncated_features = feature_context
        if feature_context and len(feature_context) > budget:
            truncated_features = feature_context[:budget] + "\n… [truncated]"

        return self.build(
            user_prompt=user_prompt,
            feature_context=truncated_features if truncated_features != feature_context else None,
            rag_context=rag_context,
        )
