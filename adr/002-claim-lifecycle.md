# ADR 002: Claim lifecycle — 8-state superset

**Status:** Accepted
**Date:** September 2026
**Deciders:** Conrad (Daniel Kliewer)
**Review trigger:** Before Phase 3 implementation begins, or when a claim lifecycle transition fails to map to a real corpus event.

---

## Context

Hermes Atlas implements a 6-state claim lifecycle (`candidate → supported → validated → contested → invalidated → superseded`) that has been benchmark-proven on two fixed corpora with a hand-labeled gold set. That design is sound and tested. However, Ganymede 2.0 requires richer epistemic vocabulary:

- Atlas conflates "no evidence found" with "evidence insufficient" — both are handled by confidence thresholds, not lifecycle states.
- Atlas's `invalidated` is DELETE-driven only (source removed). Ganymede 2.0 needs to distinguish "source removed" from "source was never there."
- Atlas has no `UNRESOLVED` state — a claim that was searched for but not found is indistinguishable from one that was never examined.

The question is whether to adopt Atlas's 6-state model as-is, extend it to a 7-state superset, or define a new 8-state model.

---

## Decision

Define an **8-state superset** that extends Atlas's model with three new states while preserving all of Atlas's tested invariants.

### State vocabulary

| State | Meaning | Evidence condition |
|-------|---------|-------------------|
| `UNEXAMINED` | Claim extracted, not yet evaluated | No evaluation run against this claim |
| `SUPPORTED` | Evidence supports this claim | Supporting evidence above confidence threshold |
| `VALIDATED` | Multiple independent sources corroborate | ≥2 independent sources, high confidence, no strong contradiction |
| `CONTESTED` | Both supporting and contradicting evidence exist | Mixed evidence with both sides above noise floor |
| `CONTRADICTED` | Evidence directly contradicts this claim | Contradicting evidence dominates supporting evidence |
| `INSUFFICIENT` | Some evidence exists but below support threshold | Weak, sparse, or low-reliability evidence |
| `UNRESOLVED` | No supporting evidence found after deliberate search | Search was conducted; no evidence located |
| `RETRACTED` | Was SUPPORTED/VALIDATED; supporting evidence was removed or invalidated | DELETE-driven: the evidence that supported this claim is gone |

**Note:** Atlas's `candidate` state maps to `UNEXAMINED`. Atlas's `invalidated` maps to `RETRACTED`. Atlas's `superseded` is preserved as-is — it is a separate transition from `RETRACTED` (superseded = replaced by a better claim, not retracted due to evidence removal).

### State machine

```
                   ┌──────────────────────────────────────┐
                   │                                      ▼
UNEXAMINED ──→ SUPPORTED ──→ VALIDATED ──→ CONTESTED ──→ CONTRADICTED
     │              │              │            │
     ▼              ▼              ▼            ▼
INSUFFICIENT    RETRACTED    SUPERSEDED    SUPERSEDED
     │              ▲              ▲            ▲
     ▼              │              │            │
UNRESOLVED ─────────┴──────────────┴────────────┘
              (evidence removed or found contradicting)
```

**Legal transitions (from → to):**
- UNEXAMINED → SUPPORTED, INSUFFICIENT, UNRESOLVED
- SUPPORTED → VALIDATED, CONTESTED, CONTRADICTED, INSUFFICIENT, RETRACTED, SUPERSEDED
- VALIDATED → CONTESTED, CONTRADICTED, RETRACTED, SUPERSEDED
- CONTESTED → CONTRADICTED, SUPPORTED, SUPERSEDED
- CONTRADICTED → SUPERSEDED (only via a replacement claim)
- INSUFFICIENT → SUPPORTED, UNRESOLVED, SUPERSEDED
- UNRESOLVED → SUPPORTED, INSUFFICIENT, SUPERSEDED
- RETRACTED → SUPERSEDED (only via a replacement claim)
- SUPERSEDED → (terminal state; no exits)

**Illegal transitions (examples):**
- UNEXAMINED → VALIDATED (skip SUPPORTED)
- INSUFFICIENT → VALIDATED (skip SUPPORTED)
- UNRESOLVED → VALIDATED (skip SUPPORTED)
- RETRACTED → SUPPORTED (must go through SUPERSEDED with a new claim)
- Any state → UNEXAMINED (no re-examination from prior state)

### Invariants (extended from Atlas)

1. **No-op stability** — A no-op recompile (no evidence changed) does not move any claim's state.
2. **No illegal skips** — Every written state is the one evidence dictates. The state machine is a pure function of evidence, not of prior state.
3. **Invalidations are justified** — A claim becomes `RETRACTED` ONLY when its supporting evidence is removed or directly contradicted. The claim record and its history are retained, never silently dropped.
4. **Contradictions are preserved** — A contradicted claim pair survives delta recompiles without being dropped.
5. **UNRESOLVED is distinct** — A claim that was searched for but not found is `UNRESOLVED`, not `INSUFFICIENT`. Searching is a deliberate act, recorded in the ledger.
6. **History is never dropped** — Every state transition is appended to the claim's `history[]` list. The history is the full provenance of belief.

---

## Consequences

**Enables:**
- **Negative knowledge as first-class:** INSUFFICIENT and UNRESOLVED are distinct, queryable states. A user can ask "what did Ganymede look for and not find?" and get a real answer.
- **Epistemic regression detection:** A claim that was SUPPORTED in compile N but UNRESOLVED in compile N+1 is a regression. The compiler surfaces this, never conceals it.
- **Auditability:** The full history of every claim is retained. A lawyer can see "this claim was SUPPORTED on 2026-09-19, RETRACTED on 2026-09-25 because source X was removed."
- **Atlas compatibility:** The 6-state Atlas model is a subset. Atlas's benchmark-proved invariants are preserved.

**Costs:**
- More states to implement and test
- The state machine is more complex than Atlas's
- `UNRESOLVED` requires a "search was conducted" ledger entry — this is a new event type not present in Atlas

**Hardens:**
- The "never silently overwrite" principle: SUPERSEDED and RETRACTED retain history
- The "agent must never be both investigator and judge" principle: agents propose state transitions; the policy layer evaluates them against the state machine
- The "epistemic reproducibility" principle: the state machine is a pure function of evidence, so two compiles of the same evidence produce the same state

---

## Alternatives considered

### Adopt Atlas's 6-state model as-is
Rejected. Atlas's model doesn't distinguish "no evidence found" from "evidence insufficient." This is a real epistemic distinction that Ganymede 2.0 requires (the prompt's "negative knowledge is first-class" commitment). Atlas's model also has no `UNEXAMINED` state — every claim is evaluated immediately. Ganymede 2.0 needs `UNEXAMINED` for claims that are extracted but not yet evaluated (e.g., claims from a new source that hasn't been through the full compiler yet).

### Define a 7-state model (Atlas + UNRESOLVED)
Rejected. This covers the negative knowledge gap but doesn't address the "evidence searched, found insufficient" vs. "no evidence found" distinction. Both are real epistemic states with different implications for what to do next.

### Use a continuous confidence score instead of discrete states
Rejected. A confidence score is a measure of strength, not a measure of epistemic category. A claim with confidence 0.1 because it has one weak source is different from a claim with confidence 0.1 because it has one weak source AND one strong contradiction. The discrete states capture this; a scalar score doesn't.

---

## References

- Ganymede 2.0 SPEC.md §4 (Claim lifecycle)
- Atlas `lifecycle.py` (6-state model — what we're extending)
- Atlas `ledger.py` (claim history pattern — what we're preserving)
- Atlas `confidence.py` (scoring function — complementary to, not a replacement for, the state machine)
