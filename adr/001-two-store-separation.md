# ADR 001: Two-store separation — Evidence Graph vs Epistemic Graph

**Status:** Accepted
**Date:** September 2026
**Deciders:** Conrad (Daniel Kliewer)
**Review trigger:** Before Phase 2 implementation begins.

---

## Context

Ganymede 2.0 must distinguish between what exists in the corpus (historical, immutable) and what the system believes can be inferred from it (interpretation, versioned, revisable). These are fundamentally different epistemic categories. Conflating them — as most RAG systems do — creates an architecture where interpretation contaminates evidence, and revisions to claims silently destroy the history of what was believed and why.

The question is whether this separation is conceptual (two views over one store) or architectural (two distinct stores with different mutability guarantees).

---

## Decision

Use **two physically distinct stores** with different mutability semantics:

| Aspect | Evidence Graph | Epistemic Graph |
|--------|----------------|-----------------|
| **Nature** | Historical record of what was in the corpus | Current interpretation of what can be inferred |
| **Contents** | sources, extractions, evidence spans, source checksums, contradiction records | claims, confidence scores, status, derived_from links, investigation history, ledger events |
| **Mutability** | Append-only. Raw objects are never deleted (sources may be marked `removed` but the record persists). Extractions are immutable once written. | Status is a pure function of evidence, recomputed each compile. History is appended, never overwritten. Claims are never deleted — only transitioned to RETRACTED/SUPERSEDED. |
| **Provenance model** | Source ID + char offset + parser version + content hash + normalization version | Claim ID + evidence refs + compiler version + policy version + parent event IDs |
| **Change detection** | Content-hash gated. Identical source + identical parser + identical checksum = no write. The changelog stays silent. | Evidence-change gated. Claims whose evidence fingerprint is unchanged keep their status. Claims with new/removed evidence are re-evaluated. |
| **Answer to** | "What did the corpus contain?" | "What can we legitimately establish from it?" |

The two stores communicate in one direction only: Evidence Graph → Epistemic Graph. The Epistemic Graph holds references (evidence IDs, source IDs) into the Evidence Graph, never the reverse. This prevents interpretation from contaminating evidence.

---

## Consequences

**Enables:**
- Clean separation of "what the record says" from "what we think it means"
- Epistemic reproducibility: "this claim was SUPPORTED under corpus version A, parser version B, inference provider C, epistemic policy D"
- Safe corpus revision: adding/removing sources only affects the Evidence Graph; the Epistemic Graph re-derives
- Auditability: the Epistemic Graph's ledger records every interpretation change, while the Evidence Graph's append-only log records every corpus change
- Determinism: identical Evidence Graph inputs produce identical Epistemic Graph outputs (the core guarantee)

**Costs:**
- Two stores to maintain, back up, and keep in sync
- Querying across both stores requires explicit joins (claim→evidence, evidence→downstream claims)
- Storage overhead (evidence is referenced by both stores)

**Hardens:**
- The "never silently overwrite" principle: both stores are append-only
- The "agent must never be both investigator and judge" principle: agents propose to the Epistemic Graph, which references but never mutates the Evidence Graph
- The "negative knowledge is first-class" principle: the Epistemic Graph can distinguish "no evidence found" (UNRESOLVED) from "evidence found but insufficient" (INSUFFICIENT) because it knows what was searched

---

## Alternatives considered

### Single store with type tags
Rejected. If evidence and claims live in the same store, a buggy agent or a corrupted lifecycle transition can destroy evidence. The mutability guarantees are enforced by the store boundary, not by a `record_type` column. Physical separation is the enforceable version of the conceptual distinction.

### Two views over one Atlas-style store
Rejected. Atlas is a research tool with a single append-only store and a small corpus. Ganymede 2.0's corpus is larger, the litigation domain has regulatory implications for evidence handling, and the two-store separation is a product requirement (you can show a lawyer the Evidence Graph without any interpretation layered on top).

### Event sourcing with separate projections
Rejected for MVP. The Evidence Graph IS the event store for corpus events. The Epistemic Graph IS the projection. Adding an intermediate event bus adds latency and complexity without a clear benefit at the current scale.

---

## References

- Ganymede 2.0 SPEC.md §3 (Two-store separation)
- Atlas `store.py` (single-store pattern — what we're diverging from)
- Atlas `ledger.py` (claim history pattern — what we're extending)
