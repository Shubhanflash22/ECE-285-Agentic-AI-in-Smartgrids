"""
backends/vllm_backend.py – Calls a vLLM OpenAI-compatible server.

vLLM exposes an OpenAI-compatible REST API, so we use the `openai` SDK
(or raw requests as fallback).

Start vLLM server:
    python -m vllm.entrypoints.openai.api_server \
        --model meta-llama/Meta-Llama-3-8B-Instruct \
        --port 8000

Requires (one of):
    pip install openai            ← preferred
    pip install requests          ← fallback
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


class VLLMBackend:
    """
    Calls a vLLM server's OpenAI-compatible /v1/chat/completions endpoint.

    Parameters
    ----------
    host  : Base URL of the vLLM server, e.g. "http://localhost:8000"
    model : Model name as registered in vLLM (must match --model flag used at startup)
    """

    def __init__(
        self,
        host: str = "http://localhost:8000",
        model: str = "meta-llama/Meta-Llama-3-8B-Instruct",
    ):
        self.host  = host.rstrip("/")
        self.model = model
        logger.info("VLLMBackend initialised – %s @ %s", model, host)

    # ─────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> str:
        """Try openai SDK first, fall back to raw requests."""
        try:
            return self._generate_openai(prompt, system, max_tokens, temperature)
        except ImportError:
            logger.warning("openai package not found – falling back to raw HTTP")
            return self._generate_requests(prompt, system, max_tokens, temperature)

    # ─────────────────────────────────────────────────────────
    # Implementation: openai SDK
    # ─────────────────────────────────────────────────────────

    def _generate_openai(self, prompt, system, max_tokens, temperature) -> str:
        from openai import OpenAI

        client = OpenAI(
            base_url=f"{self.host}/v1",
            api_key="EMPTY",  # vLLM doesn't require a real key
        )

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        result = response.choices[0].message.content.strip()
        logger.info("vLLM (openai SDK) response: %d chars", len(result))
        return result

    # ─────────────────────────────────────────────────────────
    # Implementation: raw requests
    # ─────────────────────────────────────────────────────────

    def _generate_requests(self, prompt, system, max_tokens, temperature) -> str:
        import requests

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model":       self.model,
            "messages":    messages,
            "max_tokens":  max_tokens,
            "temperature": temperature,
        }

        endpoint = f"{self.host}/v1/chat/completions"
        try:
            r = requests.post(endpoint, json=payload, timeout=300)
            r.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                f"Could not connect to vLLM at {self.host}. "
                "Make sure the vLLM server is running."
            )

        data   = r.json()
        result = data["choices"][0]["message"]["content"].strip()
        logger.info("vLLM (requests) response: %d chars", len(result))
        return result
