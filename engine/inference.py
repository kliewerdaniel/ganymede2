"""Inference layer — sovereignty-ranked providers with full event logging.

Implements ADR 006 (Inference sovereignty ladder):

- Level 1 (canonical): local Ollama — default for all inference
- Level 2: other local runtimes (OpenAI-compatible local servers: llama.cpp, vllm)
- Level 3: external providers — opt-in only, sovereignty_boundary_crossed=True

Design rules:
- Every call returns an InferenceResult carrying provider, model, operation,
  input/output hashes, latency, and sovereignty boundary status.
- Provider selection never fails silently: unreachable provider -> None ->
  the caller skips the operation (deterministic layer stands alone).
- Model output is UNTRUSTED data. Callers must validate before use.
- Inference is compile-time only and never required for compilation.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

import httpx
import yaml


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class InferenceResult:
    """Result of one inference call, with full provenance metadata."""
    ok: bool
    output: Any = None
    error: Optional[str] = None
    provider: str = ""
    model: str = ""
    operation: str = ""
    latency_seconds: float = 0.0
    input_hash: str = ""
    output_hash: str = ""
    sovereignty_crossed: bool = False
    params: Dict[str, Any] = field(default_factory=dict)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Prompt contracts (versioned — any change requires a version bump)
# ---------------------------------------------------------------------------

VERIFIER_PROMPT_VERSION = "1.0.0"
VERIFIER_PROMPT = """You are a strict verifier. Given a QUESTION and a PASSAGE, answer only YES or NO.
Answer YES only if the passage contains information that answers the question.
Answer NO if the passage does not contain the answer.
Do not use outside knowledge. Judge only from the passage.
Reply with exactly one word: YES or NO.

QUESTION: {question}

PASSAGE: {passage}"""

EMBED_TRUNCATION_CHARS = 512  # nomic-embed-text: 2048-token ctx; 512 chars is safe


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------

class InferenceProvider(Protocol):
    name: str
    sovereignty_crossed: bool

    def generate(self, prompt: str, *, model: str, params: Optional[dict] = None) -> InferenceResult: ...
    def generate_structured(self, prompt: str, *, model: str, schema: dict, params: Optional[dict] = None) -> InferenceResult: ...
    def embed(self, text: str, *, model: str) -> InferenceResult: ...
    def classify(self, text: str, *, model: str, labels: List[str]) -> InferenceResult: ...
    def extract(self, prompt: str, *, model: str, schema: Optional[dict] = None) -> InferenceResult: ...
    def verify(self, question: str, passage: str, *, model: str) -> InferenceResult: ...
    def health(self) -> bool: ...


# ---------------------------------------------------------------------------
# Ollama provider (Level 1 — canonical, local)
# ---------------------------------------------------------------------------

class OllamaProvider:
    """Local Ollama provider. Sovereignty boundary: never crossed."""

    name = "ollama"
    sovereignty_crossed = False

    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # -- transport ----------------------------------------------------------

    def _post(self, path: str, payload: dict, timeout: float = None) -> dict:
        resp = httpx.post(
            f"{self.base_url}{path}",
            json=payload,
            timeout=timeout or self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def health(self) -> bool:
        try:
            httpx.get(f"{self.base_url}/api/tags", timeout=2)
            return True
        except Exception:
            return False

    # -- operations ---------------------------------------------------------

    def generate(self, prompt: str, *, model: str, params: Optional[dict] = None) -> InferenceResult:
        options = {"temperature": 0.0}
        if params:
            options.update(params)
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "think": False,  # qwen3 family: suppress thinking blocks (honored by 8b; 4b needs structured format)
            "options": options,
        }
        return self._generate(payload, model, options)

    def generate_structured(
        self, prompt: str, *, model: str, schema: dict, params: Optional[dict] = None
    ) -> InferenceResult:
        """Generate with Ollama structured output (JSON schema enforcement).

        This is the reliable way to get parseable output from thinking-mode
        models (qwen3:4b leaks reasoning into `response` even with think=false;
        structured format constrains generation to the schema).
        """
        options = {"temperature": 0.0}
        if params:
            options.update(params)
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "format": schema,
            "options": options,
        }
        return self._generate(payload, model, options)

    def _generate(self, payload: dict, model: str, options: dict) -> InferenceResult:
        start = time.time()
        input_hash = _sha(payload["prompt"] + json.dumps(options, sort_keys=True))
        try:
            data = self._post("/api/generate", payload)
            output = data.get("response", "")
            return InferenceResult(
                ok=True,
                output=output,
                provider=self.name,
                model=model,
                operation="generate",
                latency_seconds=time.time() - start,
                input_hash=input_hash,
                output_hash=_sha(output),
                sovereignty_crossed=self.sovereignty_crossed,
                params=options,
            )
        except Exception as e:
            return InferenceResult(
                ok=False,
                error=str(e),
                provider=self.name,
                model=model,
                operation="generate",
                latency_seconds=time.time() - start,
                input_hash=input_hash,
                sovereignty_crossed=self.sovereignty_crossed,
                params=options,
            )

    def embed(self, text: str, *, model: str) -> InferenceResult:
        # nomic-embed-text context limit — truncate to stay under it
        truncated = text[:EMBED_TRUNCATION_CHARS]
        payload = {"model": model, "prompt": truncated}
        start = time.time()
        input_hash = _sha(truncated)
        try:
            data = self._post("/api/embeddings", payload, timeout=60)
            output = data.get("embedding", [])
            return InferenceResult(
                ok=True,
                output=output,
                provider=self.name,
                model=model,
                operation="embed",
                latency_seconds=time.time() - start,
                input_hash=input_hash,
                output_hash=_sha(json.dumps(output)),
                sovereignty_crossed=self.sovereignty_crossed,
            )
        except Exception as e:
            return InferenceResult(
                ok=False,
                error=str(e),
                provider=self.name,
                model=model,
                operation="embed",
                latency_seconds=time.time() - start,
                input_hash=input_hash,
                sovereignty_crossed=self.sovereignty_crossed,
            )

    def classify(self, text: str, *, model: str, labels: List[str]) -> InferenceResult:
        label_list = ", ".join(labels)
        prompt = (
            f"Classify the TEXT into exactly one category from: {label_list}.\n"
            f"Reply with only the category name, nothing else.\n\nTEXT: {text}"
        )
        schema = {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": labels},
            },
            "required": ["category"],
        }
        result = self.generate_structured(prompt, model=model, schema=schema, params={"num_predict": 32})
        result.operation = "classify"
        if result.ok:
            try:
                parsed = json.loads(str(result.output))
                matched = parsed.get("category")
            except (json.JSONDecodeError, AttributeError):
                matched = self._match_label(str(result.output), labels)
            if matched not in labels:
                fallback = self._match_label(str(result.output), labels)
                if fallback is None:
                    return InferenceResult(
                        ok=False,
                        error=f"model output matched no label: {result.output!r}",
                        provider=self.name,
                        model=model,
                        operation="classify",
                        latency_seconds=result.latency_seconds,
                        input_hash=result.input_hash,
                        output_hash=result.output_hash,
                        sovereignty_crossed=self.sovereignty_crossed,
                    )
                matched = fallback
            result.output = matched
        return result

    @staticmethod
    def _match_label(output: str, labels: List[str]) -> Optional[str]:
        low = output.strip().lower()
        # exact / substring match, longest label first to avoid prefix collisions
        for label in sorted(labels, key=len, reverse=True):
            if label.lower() in low:
                return label
        return None

    def extract(self, prompt: str, *, model: str, schema: Optional[dict] = None) -> InferenceResult:
        # Structured output: schema enforcement beats parsing prose out of
        # thinking-mode models. Callers may pass a schema; otherwise we
        # default to a permissive object schema.
        json_schema = schema or {"type": "object"}
        result = self.generate_structured(prompt, model=model, schema=json_schema)
        result.operation = "extract"
        if not result.ok:
            return result
        parsed = self._parse_json(str(result.output))
        if parsed is None:
            return InferenceResult(
                ok=False,
                error=f"model output is not valid JSON: {str(result.output)[:200]!r}",
                provider=self.name,
                model=model,
                operation="extract",
                latency_seconds=result.latency_seconds,
                input_hash=result.input_hash,
                output_hash=result.output_hash,
                sovereignty_crossed=self.sovereignty_crossed,
                params=result.params,
            )
        result.output = parsed
        return result

    @staticmethod
    def _parse_json(text: str) -> Optional[Any]:
        """Parse JSON from model output, tolerating markdown fences and prose."""
        text = text.strip()
        # strip markdown code fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]
        # find outermost JSON object or array
        for opener, closer in (("{", "}"), ("[", "]")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start != -1 and end > start:
                candidate = text[start : end + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def verify(self, question: str, passage: str, *, model: str) -> InferenceResult:
        prompt = VERIFIER_PROMPT.format(question=question, passage=passage)
        schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string", "enum": ["YES", "NO"]},
            },
            "required": ["answer"],
        }
        result = self.generate_structured(prompt, model=model, schema=schema, params={"num_predict": 16})
        result.operation = "verify"
        if result.ok:
            answer = None
            try:
                parsed = json.loads(str(result.output))
                answer = parsed.get("answer", "")
            except (json.JSONDecodeError, AttributeError):
                answer = str(result.output).strip().upper()
            if str(answer).strip().upper().startswith("YES"):
                result.output = True
            elif str(answer).strip().upper().startswith("NO"):
                result.output = False
            else:
                return InferenceResult(
                    ok=False,
                    error=f"verifier output unparseable: {result.output!r}",
                    provider=self.name,
                    model=model,
                    operation="verify",
                    latency_seconds=result.latency_seconds,
                    input_hash=result.input_hash,
                    output_hash=result.output_hash,
                    sovereignty_crossed=self.sovereignty_crossed,
                )
        return result


# ---------------------------------------------------------------------------
# OpenAI-compatible provider (Level 2 local runtimes / Level 3 external)
# ---------------------------------------------------------------------------

class OpenAICompatProvider:
    """Any OpenAI-compatible /v1/chat/completions endpoint.

    Level 2 (local llama.cpp / vllm / MLX servers): sovereignty_crossed=False.
    Level 3 (external APIs): sovereignty_crossed=True — opt-in only.
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        *,
        api_key_env: Optional[str] = None,
        sovereignty_crossed: bool = False,
        timeout: float = 120.0,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.sovereignty_crossed = sovereignty_crossed
        self.timeout = timeout

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key_env:
            key = os.environ.get(self.api_key_env, "")
            if key:
                headers["Authorization"] = f"Bearer {key}"
        return headers

    def health(self) -> bool:
        try:
            httpx.get(f"{self.base_url}/models", headers=self._headers(), timeout=2)
            return True
        except Exception:
            return False

    def _chat(self, model: str, user_prompt: str, max_tokens: Optional[int] = None) -> InferenceResult:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": 0.0,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        start = time.time()
        input_hash = _sha(user_prompt)
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            output = resp.json()["choices"][0]["message"]["content"]
            return InferenceResult(
                ok=True,
                output=output,
                provider=self.name,
                model=model,
                operation="generate",
                latency_seconds=time.time() - start,
                input_hash=input_hash,
                output_hash=_sha(output),
                sovereignty_crossed=self.sovereignty_crossed,
                params={"temperature": 0.0},
            )
        except Exception as e:
            return InferenceResult(
                ok=False,
                error=str(e),
                provider=self.name,
                model=model,
                operation="generate",
                latency_seconds=time.time() - start,
                input_hash=input_hash,
                sovereignty_crossed=self.sovereignty_crossed,
            )

    def generate(self, prompt: str, *, model: str, params: Optional[dict] = None) -> InferenceResult:
        return self._chat(model, prompt)

    def generate_structured(
        self, prompt: str, *, model: str, schema: dict, params: Optional[dict] = None
    ) -> InferenceResult:
        # OpenAI-compatible structured output via response_format json_schema
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": schema},
            },
        }
        start = time.time()
        input_hash = _sha(prompt)
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            output = resp.json()["choices"][0]["message"]["content"]
            return InferenceResult(
                ok=True,
                output=output,
                provider=self.name,
                model=model,
                operation="generate",
                latency_seconds=time.time() - start,
                input_hash=input_hash,
                output_hash=_sha(output),
                sovereignty_crossed=self.sovereignty_crossed,
                params={"temperature": 0.0},
            )
        except Exception as e:
            return InferenceResult(
                ok=False,
                error=str(e),
                provider=self.name,
                model=model,
                operation="generate",
                latency_seconds=time.time() - start,
                input_hash=input_hash,
                sovereignty_crossed=self.sovereignty_crossed,
            )

    def embed(self, text: str, *, model: str) -> InferenceResult:
        start = time.time()
        truncated = text[:EMBED_TRUNCATION_CHARS]
        input_hash = _sha(truncated)
        try:
            resp = httpx.post(
                f"{self.base_url}/embeddings",
                json={"model": model, "input": truncated},
                headers=self._headers(),
                timeout=60,
            )
            resp.raise_for_status()
            output = resp.json()["data"][0]["embedding"]
            return InferenceResult(
                ok=True,
                output=output,
                provider=self.name,
                model=model,
                operation="embed",
                latency_seconds=time.time() - start,
                input_hash=input_hash,
                output_hash=_sha(json.dumps(output)),
                sovereignty_crossed=self.sovereignty_crossed,
            )
        except Exception as e:
            return InferenceResult(
                ok=False,
                error=str(e),
                provider=self.name,
                model=model,
                operation="embed",
                latency_seconds=time.time() - start,
                input_hash=input_hash,
                sovereignty_crossed=self.sovereignty_crossed,
            )

    def classify(self, text: str, *, model: str, labels: List[str]) -> InferenceResult:
        label_list = ", ".join(labels)
        prompt = (
            f"Classify the TEXT into exactly one category from: {label_list}.\n"
            f"Reply with only the category name, nothing else.\n\nTEXT: {text}"
        )
        result = self.generate_structured(prompt, model=model, schema={
            "type": "object",
            "properties": {"category": {"type": "string", "enum": labels}},
            "required": ["category"],
        })
        result.operation = "classify"
        if result.ok:
            try:
                parsed = json.loads(str(result.output))
                matched = parsed.get("category")
            except (json.JSONDecodeError, AttributeError):
                matched = None
            if matched not in labels:
                matched = OllamaProvider._match_label(str(result.output), labels)
            if matched is None:
                result.ok = False
                result.error = f"model output matched no label: {result.output!r}"
            else:
                result.output = matched
        return result

    def extract(self, prompt: str, *, model: str, schema: Optional[dict] = None) -> InferenceResult:
        # Structured output (response_format json_schema) beats parsing prose
        # out of thinking-mode models — mirrors the Ollama provider path.
        json_schema = schema or {"type": "object"}
        result = self.generate_structured(prompt, model=model, schema=json_schema)
        result.operation = "extract"
        if not result.ok:
            return result
        parsed = OllamaProvider._parse_json(str(result.output))
        if parsed is None:
            result.ok = False
            result.error = f"model output is not valid JSON: {str(result.output)[:200]!r}"
        else:
            result.output = parsed
        return result

    def verify(self, question: str, passage: str, *, model: str) -> InferenceResult:
        prompt = VERIFIER_PROMPT.format(question=question, passage=passage)
        result = self.generate_structured(prompt, model=model, schema={
            "type": "object",
            "properties": {"answer": {"type": "string", "enum": ["YES", "NO"]}},
            "required": ["answer"],
        })
        result.operation = "verify"
        if result.ok:
            answer = None
            try:
                parsed = json.loads(str(result.output))
                answer = parsed.get("answer", "")
            except (json.JSONDecodeError, AttributeError):
                answer = str(result.output).strip().upper()
            out = str(answer).strip().upper()
            if out.startswith("YES"):
                result.output = True
            elif out.startswith("NO"):
                result.output = False
            else:
                result.ok = False
                result.error = f"verifier output unparseable: {result.output!r}"
        return result


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: Dict[str, Any] = {
    "inference": {
        "canonical": "ollama",
        "local_runtimes": [
            {
                "name": "ollama",
                "base_url": "http://localhost:11434",
                "models": ["qwen3:8b", "qwen3:4b", "nomic-embed-text"],
            }
        ],
        "external": {"enabled": False, "providers": []},
        "log_all_events": True,
        "prompt_contracts": {
            "verifier": f"docs/specification/verifier-prompt.md@{VERIFIER_PROMPT_VERSION}",
        },
    }
}


def load_inference_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Load inference config from config.yaml, falling back to defaults."""
    if path is None:
        # walk up from this file to find config.yaml (project root)
        for parent in Path(__file__).resolve().parents:
            candidate = parent / "config.yaml"
            if candidate.exists():
                path = str(candidate)
                break
    if path is None or not Path(path).exists():
        return DEFAULT_CONFIG
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if "inference" in data else DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# Provider selection (the sovereignty ladder)
# ---------------------------------------------------------------------------

def select_provider(
    preferred: Optional[str] = None,
    *,
    config: Optional[Dict[str, Any]] = None,
    allow_external: bool = True,
) -> Optional[InferenceProvider]:
    """Select an inference provider by the sovereignty ladder.

    1. preferred (if named and reachable)
    2. config canonical (default: local Ollama)
    3. other configured local runtimes, in order
    4. external providers — only if config enables them AND allow_external
    5. None (caller must skip the operation — never a silent failure)
    """
    cfg = (config or load_inference_config())["inference"]

    def build_runtime(rt: dict, crossed: bool) -> InferenceProvider:
        if rt.get("type") == "ollama" or rt["name"] == "ollama":
            return OllamaProvider(rt["base_url"])
        return OpenAICompatProvider(
            rt["name"],
            rt["base_url"],
            api_key_env=rt.get("api_key_env"),
            sovereignty_crossed=crossed,
        )
    local_runtimes = cfg.get("local_runtimes", [])
    externals = cfg.get("external", {})
    external_enabled = bool(externals.get("enabled")) and allow_external
    external_providers = externals.get("providers", []) if external_enabled else []

    # 1. preferred
    if preferred:
        for rt in local_runtimes:
            if rt["name"] == preferred:
                p = build_runtime(rt, crossed=False)
                if p.health():
                    return p
        for rt in external_providers:
            if rt["name"] == preferred:
                p = build_runtime(rt, crossed=True)
                if p.health():
                    return p

    # 2. canonical
    canonical = cfg.get("canonical", "ollama")
    for rt in local_runtimes:
        if rt["name"] == canonical:
            p = build_runtime(rt, crossed=False)
            if p.health():
                return p

    # 3. other local runtimes
    for rt in local_runtimes:
        if rt["name"] != canonical:
            p = build_runtime(rt, crossed=False)
            if p.health():
                return p

    # 4. external (opt-in)
    for rt in external_providers:
        p = build_runtime(rt, crossed=True)
        if p.health():
            return p

    # 5. nothing reachable
    return None


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------

def log_inference_event(
    result: InferenceResult,
    *,
    prompt_contract_version: Optional[str] = None,
    policy_version: str = "0.1.0",
) -> Dict[str, Any]:
    """Convert an InferenceResult into a ledger-ready MODEL_INVOKED event."""
    event_id = "evt-" + hashlib.sha256(
        f"{result.operation}-{result.input_hash}-{result.output_hash}-{time.time()}".encode()
    ).hexdigest()[:32]
    return {
        "id": event_id,
        "event_type": "MODEL_INVOKED",
        "actor": "system:inference",
        "operation": result.operation,
        "inputs": {
            "provider": result.provider,
            "model": result.model,
            "input_hash": result.input_hash,
        },
        "outputs": {
            "ok": result.ok,
            "output_hash": result.output_hash,
            "error": result.error,
        },
        "input_hashes": [result.input_hash],
        "output_hashes": [result.output_hash] if result.output_hash else [],
        "model": {
            "provider": result.provider,
            "model": result.model,
            "operation": result.operation,
            "sovereignty_boundary_crossed": result.sovereignty_crossed,
            "logged": True,
            "prompt_contract_version": prompt_contract_version,
        },
        "policy_version": policy_version,
        "parent_event_id": None,
        "metadata": {
            "latency_seconds": result.latency_seconds,
            "params": result.params,
        },
    }
