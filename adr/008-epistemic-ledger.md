# ADR 008: Epistemic ledger — append-only DAG of events

**Status:** Accepted
**Date:** September 2026
**Deciders:** Conrad (Daniel Kliewer)
**Review trigger:** Before Phase 4 implementation begins, or when a new event type is proposed.

---

## Context

Ganymede 2.0 requires a complete, tamper-evident record of every operation that affects epistemic state: sources ingested, evidence extracted, claims proposed and evaluated, contradictions detected, investigations started, models evaluated, artifacts compiled. The question is how to structure this record and what guarantees it provides.

Atlas has a claim-level history (each claim retains its `history[]`), but no system-wide ledger. Ganymede 1.x has an `ingestion_status` column and audit log, but no full epistemic ledger. Ganymede 2.0 needs both: per-record history AND a system-wide event log.

---

## Decision

Use an **append-only event ledger** that records every operation affecting epistemic state. The ledger is a DAG (directed acyclic graph) where events link to parent events, forming a complete causal history.

### Event types

| Category | Event types |
|----------|-------------|
| Corpus | `SOURCE_INGESTED`, `SOURCE_REMOVED`, `SOURCE_RESTORED` |
| Extraction | `EVIDENCE_EXTRACTED`, `EVIDENCE_INVALIDATED`, `EVIDENCE_STALE` |
| Claims | `CLAIM_PROPOSED`, `CLAIM_SUPPORTED`, `CLAIM_CONTESTED`, `CLAIM_CONTRADICTED`, `CLAIM_RETRACTED`, `CLAIM_SUPERSEDED`, `CLAIM_VALIDATED`, `CLAIM_REOPENED` |
| Contradictions | `CONTRADICTION_DETECTED`, `CONTRADICTION_RESOLVED`, `CONTRADICTION_ACCEPTED` |
| Investigations | `INVESTIGATION_STARTED`, `INVESTIGATION_COMPLETED`, `INVESTIGATION_ABANDONED` |
| Inference | `MODEL_INVOKED`, `MODEL_SKIPPED`, `PROVIDER_SELECTED` |
| Artifacts | `ARTIFACT_COMPILED`, `ARTIFACT_DEPLOYED`, `ARTIFACT_RETRACTED` |
| System | `COMPILE_STARTED`, `COMPILE_COMPLETED`, `GATE_PASSED`, `GATE_FAILED` |

### Event schema

```python
@dataclass
class LedgerEvent:
    event_id: str                    # evt-<hash>
    event_type: str                  # one of the above
    actor: str                       # agent:corpus-cartographer, system:compiler, user:conrad, policy:lifecycle-gate
    operation: str                   # specific operation within the type
    inputs: Dict[str, Any]           # source IDs, evidence IDs, claim IDs, etc.
    outputs: Dict[str, Any]          # claim IDs, status changes, artifact paths, etc.
    input_hashes: list[str]          # content hashes of inputs
    output_hashes: list[str]         # content hashes of outputs
    model: Optional[Dict]            # inference event details (from ADR 006)
    policy_version: str              # policy version active at this event
    parent_event_id: Optional[str]    # links to causal parent (DAG structure)
    timestamp: float
    metadata: Dict[str, Any]         # flexible metadata
```

### DAG structure

- Every event has zero or more parent events.
- A `CLAIM_SUPPORTED` event parents the `EVIDENCE_EXTRACTED` events that provided the evidence.
- An `ARTIFACT_COMPILED` event parents the `CLAIM_SUPPORTED`, `CLAIM_CONTRADICTED`, etc. events that produced the claims in the artifact.
- The DAG is traversable forward (what did this event enable?) and backward (what caused this event?).

### Immutability

- Events are append-only. Never overwritten, never deleted.
- Event IDs are content-hash derived (deterministic).
- A changed event is a new event with a new ID, linked to the old event via `parent_event_id`.

### Storage

- PostgreSQL with a `ledger_events` table.
- JSONB columns for `inputs`, `outputs`, `metadata`.
- Indexes on `event_type`, `actor`, `policy_version`, `parent_event_id`, `timestamp`.
- Full table scan for DAG reconstruction is feasible for current scale. Add materialized paths if needed later.

### Query patterns

```python
# What happened to this claim?
events = query_ledger(refers_to_claim="clm-...", order_by="timestamp")

# What did this agent do?
events = query_ledger(actor="agent:corpus-cartographer", since="2026-09-19")

# What caused this event?
parents = get_ancestors(event_id="evt-...")

# What resulted from this event?
children = get_descendants(event_id="evt-...")

# What events crossed the sovereignty boundary?
events = query_ledger(model_sovereignty_boundary_crossed=True)
```

---

## Consequences

**Enables:**
- **Complete audit trail**: every operation is recorded and traceable
- **Causal reasoning**: the DAG structure enables "why did this happen?" queries
- **Epistemic regression detection**: compare ledger entries across compiles to find silent changes
- **Reproducibility**: replay the ledger to reconstruct any prior state

**Costs:**
- Storage overhead (every operation produces an event)
- Write overhead (every operation writes an event)
- DAG traversal queries can be slow at scale (mitigated by indexes)

**Hardens:**
- The "append-only epistemic ledger" principle
- The "auditable reasoning artifacts" principle
- The "epistemic reproducibility" principle

---

## Alternatives considered

### Per-record history only (Atlas model)
Rejected. Atlas's per-record `history[]` is sufficient for claim-level audit but doesn't capture system-wide events like `COMPILE_STARTED`, `MODEL_INVOKED`, or `ARTIFACT_COMPILED`. Ganymede 2.0 needs both.

### Blockchain / Merkle tree
Rejected for MVP. The append-only event log provides tamper-evidence through content hashing and DAG linkage. Full blockchain is overkill at this scale. Revisit if adversarial multi-party audit becomes a requirement.

### Separate audit log (Ganymede 1.x model)
Rejected. Ganymede 1.x's audit log is separate from the claim history. Ganymede 2.0 unifies them: the ledger IS the claim history, the agent history, and the system history.

---

## References

- Ganymede 2.0 SPEC.md §8 (Epistemic ledger)
- Ganymede 2.0 SPEC.md §4 (Claim lifecycle — history is part of the ledger)
- Atlas `ledger.py` (claim history — what we're extending to a full system ledger)
