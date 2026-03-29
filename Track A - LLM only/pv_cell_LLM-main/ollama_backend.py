"""
backends/ollama_backend.py – Calls a local Ollama server via its REST API.

Requires: pip install requests
Ollama must be running: `ollama serve`
Pull your model first: `ollama pull llama3`
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class OllamaBackend:
    """
    Uses Ollama's /api/chat endpoint (streaming supported).

    Parameters
    ----------
    host  : Ollama server URL, e.g. "http://localhost:11434"
    model : Model tag, e.g. "llama3", "mistral", "gemma2"
    """

    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3"):
        self.host  = host.rstrip("/")
        self.model = model
        self._endpoint = f"{self.host}/api/chat"
        logger.info("OllamaBackend initialised – %s @ %s", model, host)

    # ─────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model":   self.model,
            "messages": messages,
            "stream":  True,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }

        logger.debug("POST %s  (model=%s, max_tokens=%d)", self._endpoint, self.model, max_tokens)

        try:
            response = requests.post(
                self._endpoint,
                json=payload,
                stream=True,
                timeout=300,
            )
        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                f"Could not connect to Ollama at {self.host}. "
                "Make sure Ollama is running (`ollama serve`)."
            )

        # Helpful errors for common cases (e.g., missing model)
        if response.status_code == 404:
            detail = response.text.strip()
            raise RuntimeError(
                f"Ollama returned 404 for model '{self.model}'. "
                f"Pull it first: `ollama pull {self.model}`. "
                f"Server response: {detail or 'model not found'}"
            )

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            detail = response.text.strip()
            raise RuntimeError(
                f"Ollama request failed with status {response.status_code}: {detail}"
            ) from exc

        # ── Stream and collect ────────────────────────────────
        parts = []
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            try:
                chunk = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            content = chunk.get("message", {}).get("content", "")
            if content:
                parts.append(content)

            if chunk.get("done"):
                break

        full_response = "".join(parts).strip()
        logger.info("Ollama response: %d chars", len(full_response))
        return full_response

    # ─────────────────────────────────────────────────────────

    def list_models(self) -> list[str]:
        """Helper – list available models on the Ollama server."""
        r = requests.get(f"{self.host}/api/tags", timeout=10)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
