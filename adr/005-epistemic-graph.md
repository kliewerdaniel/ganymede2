# ADR 005: Epistemic Graph model — versioned, revisable

**Status:** Accepted
**Date:** September 2026
**Deciders:** Conrad (Daniel Kliewer)
**Review trigger:** Before Phase 3 implementation begins, or when a claim state doesn't fit the model.

---

## Context

The Epistemic Graph is the system's interpretation of what can be inferred from the Evidence Graph. Unlike the Evidence Graph (immutable), the Epistemic Graph is versioned and revisable — but every revision is recorded, never overwritten. The question is what the Epistemic Graph contains, how status is derived, and how it communicates with the Evidence Graph.

---

## Decision

The Epistemic Graph contains **three record types**, all versioned, all history-retained:

### 1. Claims
```python
{
    "id": "clm-" + sha256(normalized_proposition + source_fingerprint),
    "text": "the claim proposition",
    "normalized": "normalized form for deduplication",
    "status": "UNEXAMINED" | "SUPPORTED" | "VALIDATED" | "CONTESTED" | "CONTRADICTED" | "INSUFFICIENT" | "UNRESOLVED" | "RETRACTED" | "SUPERSEDED",
    "confidence": float,  # 0-1, from confidence.py
    "confidence_terms": {"independence": ..., "reliability": ..., "recency": ..., "corroboration": ..., "contradiction_penalty": ...},
    "evidence_ids": ["ev-..."],  # references into Evidence Graph
    "source_ids": ["src-..."],  # derived from evidence
    "entity_ids": ["ent-..."],
    "contradiction_ids": ["con-..."],
    "derived_from": ["clm-..."],  # parent claims this was derived from
    "compiler_version": "1.0.0",
    "policy_version": "1.0.0",
    "history": [
        {
            "from_status": "UNEXAMINED",
            "to_status": "SUPPORTED",
            "at": timestamp,
            "reason": "evidence added: ev-...",
            "ledger_event_id": "evt-...",
        },
        # ... every state transition retained
    ],
    "_meta": {
        "content_hash": sha256(core_fields),  # for change detection
        "created_at": timestamp,
        "updated_at": timestamp,
    }
}
```

- `status` is a **pure function of evidence**. Recompute from evidence on every compile.
- `confidence` is a **pure function of evidence**. Recompute from evidence on every compile.
- `history[]` is append-only. Every state transition is retained.
- `derived_from` links to parent claims (for SUPERSEDED transitions).

### 2. Investigations
```python
{
    "id": "inv-" + sha256(question + source_fingerprint),
    "question": "the question being investigated",
    "status": "open" | "completed" | "abandoned",
    "claim_ids": ["clm-..."],  # claims this investigation produced
    "evidence_ids": ["ev-..."],  # evidence this investigation reviewed,
    "rationale": "human-readable summary",
    "created_at": timestamp,
    "completed_at": timestamp | None,
    "_meta": {...},
}
```

- An investigation is a deliberate act of inquiry. It is recorded in the ledger.
- `UNRESOLVED` claims require an investigation record (proof that a search was conducted).

### 3. Ledger Events
```python
{
    "id": "evt-" + sha256(actor + operation + inputs + timestamp),
    "actor": "agent:corpus-cartographer" | "system:compiler" | "user:conrad" | "policy:lifecycle-gate",
    "operation": "SOURCE_INGESTED" | "EVIDENCE_EXTRACTED" | "CLAIM_PROPOSED" | "CLAIM_SUPPORTED" | "CLAIM_CONTESTED" | "CLAIM_CONTRADICTED" | "CLAIM_RETRACTED" | "CLAIM_SUPERSEDED" | "CONTRADICTION_DETECTED" | "INVESTIGATION_STARTED" | "INVESTIGATION_COMPLETED" | "STATUS_CHANGED" | "ARTIFACT_COMPILED",
    "inputs": {...},  # source IDs, evidence IDs, etc.
    "outputs": {...},  # claim IDs, status changes, etc.
    "input_hashes": ["sha256-..."],
    "output_hashes": ["sha256-..."],
    "model": {  # if inference was used
        "provider": "ollama" | "llama.cpp" | "external:...",
        "model": "qwen3:8b",
        "version": "...",
        "params": {...},
        "prompt_contract_version": "1.0.0",
        "sovereignty_boundary_crossed": bool,
    } | None,
    "policy_version": "1.0.0",
    "parent_event_id": "evt-..." | None,  # DAG structure
    "timestamp": timestamp,
    "_meta": {...},
}
```

- Append-only. Never overwritten.
- Forms a DAG (parent_event_id links).
- Every state change, every agent proposal, every inference event is recorded.

### Communication with Evidence Graph

- Epistemic Graph holds references (`evidence_ids`, `source_ids`) into the Evidence Graph.
- Epistemic Graph **never** writes to the Evidence Graph.
- When the Evidence Graph changes (new source, removed source), the Epistemic Graph is **re-derived** for affected claims.
- The re-derivation is deterministic: same Evidence Graph state → same Epistemic Graph state.

---

## Consequences

**Enables:**
- Full auditability: every claim's history is retained
- Epistemic regression detection: a claim that was SUPPORTED but is now UNRESOLVED is a regression
- Agent accountability: every agent proposal is recorded in the ledger
- Policy versioning: claims carry the policy version that evaluated them

**Costs:**
- More storage (history is retained, not overwritten)
- Re-derivation on every compile (mitigated by content-hash gating — unchanged evidence → no re-derivation)

**Hardens:**
- The "never silently overwrite" principle
- The "agent must never be both investigator and judge" principle
- The "epistemic reproducibility" principle

---

## Alternatives considered

### Single store with type tags (Atlas model)
Rejected. See ADR 001. Physical separation enforces the mutability boundary.

### Event sourcing with separate projections
Rejected for MVP. The Epistemic Graph IS the projection of the Evidence Graph. Adding an intermediate event bus adds complexity without benefit at current scale.

---

## References

- Ganymede 2.0 SPEC.md §3 (Two-store separation)
- Ganymede 2.0 SPEC.md §4 (Claim lifecycle)
- Ganymede 2.0 SPEC.md §8 (Epistemic ledger)
- Atlas `ledger.py` (claim history pattern — what we're extending)
