# ADR 006: Inference sovereignty ladder — provider ranking and logging

**Status:** Accepted
**Date:** September 2026
**Deciders:** Conrad (Daniel Kliewer)
**Review trigger:** Before Phase 5 implementation begins, or when a new inference provider needs to be added to the ladder.

---

## Context

Ganymede 2.0 requires inference for several tasks: claim refinement, relationship proposal, narrative synthesis, and (optionally) verification. The question is which inference providers to use, how to rank them, and how to log their usage to maintain sovereignty boundaries.

Ganymede 1.x uses local Ollama exclusively. Atlas is model-free by default. The prompt's design notes call for a "sovereignty-ranked" inference layer with local as canonical, other local runtimes next, and external providers last (dev accelerator only).

---

## Decision

Define a **3-level inference sovereignty ladder** with explicit ranking, logging, and boundary enforcement.

### Sovereignty ladder

| Priority | Provider category | Examples | Sovereignty boundary | Use case |
|----------|------------------|----------|---------------------|----------|
| 1 (canonical) | Local Ollama | qwen3:8b, qwen3:4b, nomic-embed-text | None (local) | Default for all inference |
| 2 | Other local runtimes | llama.cpp, vllm, MLX | None (local) | Alternative local (performance, model availability) |
| 3 | Explicitly-marked external | OpenAI API, Anthropic API, etc. | Crossed (logged) | Dev accelerator only, never invisible |

### Inference interface

```python
class InferenceProvider(Protocol):
    def generate(self, prompt: str, *, model: str, params: dict) -> str: ...
    def embed(self, text: str, *, model: str) -> list[float]: ...
    def classify(self, text: str, *, model: str, labels: list[str]) -> dict: ...
    def extract(self, text: str, *, model: str, schema: dict) -> dict: ...
    def verify(self, question: str, passage: str, *, model: str) -> bool: ...
```

### Inference event logging

Every inference call produces a log entry:

```python
{
    "event_id": "evt-...",
    "provider": "ollama" | "llama.cpp" | "vllm" | "external:openai" | ...,
    "model": "qwen3:8b",
    "model_version": "...",
    "operation": "generate" | "embed" | "classify" | "extract" | "verify",
    "prompt_contract_version": "1.0.0",
    "input_hash": sha256(prompt + params),
    "output_hash": sha256(output),
    "latency_seconds": float,
    "sovereignty_boundary_crossed": bool,
    "timestamp": timestamp,
}
```

- `sovereignty_boundary_crossed=True` only for external providers.
- External provider usage is **visible** in the UI and **queryable** in the ledger.
- External provider usage is **never** the default; it must be explicitly configured.

### Provider selection logic

```python
def select_provider(operation: str, preferred: str | None = None) -> InferenceProvider:
    # 1. If preferred is specified and reachable, use it
    # 2. Otherwise, try local Ollama (canonical)
    # 3. Then try other local runtimes
    # 4. Then try external (if configured and operation allows)
    # 5. If all fail, return a "skipped" result (never a silent failure)
```

### Model configuration

```yaml
# config.yaml
inference:
  canonical: "ollama"
  local_runtimes:
    - name: "ollama"
      base_url: "http://localhost:11434"
      models: ["qwen3:8b", "qwen3:4b", "nomic-embed-text"]
    - name: "llama.cpp"
      base_url: "http://localhost:8080"
      models: ["qwen3-8b.gguf"]
  external:
    enabled: false  # default: disabled
    providers:
      - name: "openai"
        api_key_env: "OPENAI_API_KEY"
        models: ["gpt-4o-mini"]
  log_all_events: true
  prompt_contracts:
    verifier: "docs/specification/verifier-prompt.md@v1.0.0"
    extractor: "docs/specification/extractor-prompt.md@v1.0.0"
```

---

## Consequences

**Enables:**
- **Sovereignty**: local inference is the default; external is opt-in and visible
- **Reproducibility**: same operation can be replayed across providers and diffed
- **Auditability**: every inference event is logged with model, version, latency, boundary status
- **Graceful degradation**: absent model → operation is skipped, not failed

**Costs:**
- Inference event logging adds storage and latency
- Provider abstraction adds code complexity
- External provider support requires API key management

**Hardens:**
- The "sovereignty-ranked inference layer" principle
- The "every inference event logs provider, model, version, params" principle
- The "LLM reasoning only enters after deterministic stages" principle (inference is never required for compilation)

---

## Alternatives considered

### Fixed local-only (Ganymede 1.x model)
Rejected. Local-only is the default, but the prompt explicitly calls for a provider-agnostic layer with external providers as dev accelerators. Fixed local-only would prevent future model comparisons.

### Cloud-first with local fallback
Rejected. Sovereignty is a product requirement. Cloud-first would violate the "no outbound inference traffic by default" trust constraint.

### No inference layer (Atlas model)
Rejected. Atlas is model-free for research. Ganymede 2.0 needs inference for claim refinement, narrative synthesis, and (optionally) verification. The inference layer must be optional but available.

---

## References

- Ganymede 2.0 SPEC.md §6 (Inference sovereignty ladder)
- Ganymede 1.x `api/app/services/verifier.py` (Ollama verifier — what we're abstracting)
- Atlas `confidence.py` (model-free scoring — what we're extending with optional model refinement)
