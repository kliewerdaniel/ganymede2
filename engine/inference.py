"""Inference layer — provider-agnostic with sovereignty ranking."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, Optional, Protocol

import httpx


class InferenceProvider(Protocol):
    def generate(self, prompt: str, *, model: str, params: dict) -> str: ...
    def embed(self, text: str, *, model: str) -> list[float]: ...


class OllamaProvider:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url

    def generate(self, prompt: str, *, model: str, params: dict = None) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if params:
            payload["options"] = params

        resp = httpx.post(f"{self.base_url}/api/generate", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("response", "")

    def embed(self, text: str, *, model: str) -> list[float]:
        payload = {"model": model, "prompt": text}
        resp = httpx.post(f"{self.base_url}/api/embeddings", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json().get("embedding", [])


def get_provider(name: str = None) -> Optional[InferenceProvider]:
    """Get an inference provider by name. Returns None if not available."""
    name = os.environ.get("INFERENCE_PROVIDER", "ollama")

    if name == "ollama":
        url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        # Quick health check
        try:
            httpx.get(f"{url}/api/tags", timeout=2)
            return OllamaProvider(url)
        except Exception:
            return None

    return None


def log_inference_event(
    *,
    provider: str,
    model: str,
    operation: str,
    input_hash: str,
    output_hash: str,
    latency: float,
    sovereignty_crossed: bool,
    policy_version: str = "0.1.0",
) -> Dict:
    """Create a ledger event for an inference call."""
    return {
        "event_type": "MODEL_INVOKED",
        "actor": "system:inference",
        "operation": operation,
        "inputs": {"model": model, "provider": provider},
        "outputs": {"output_hash": output_hash},
        "input_hashes": [input_hash],
        "output_hashes": [output_hash],
        "model": {
            "provider": provider,
            "model": model,
            "operation": operation,
            "sovereignty_boundary_crossed": sovereignty_crossed,
        },
        "policy_version": policy_version,
        "metadata": {"latency_seconds": latency},
    }
