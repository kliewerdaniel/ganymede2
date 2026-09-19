# ADR 011: Negative knowledge — first-class epistemic states

**Status:** Accepted
**Date:** September 2026
**Deciders:** Conrad (Daniel Kliewer)
**Review trigger:** Before Phase 2 implementation begins, or when a new epistemic state doesn't fit the existing categories.

---

## Context

Ganymede 2.0 must distinguish between several kinds of "no answer" — not finding evidence, finding insufficient evidence, finding direct contradiction, and having evidence removed. These are fundamentally different epistemic states, not variations of "no answer." The question is how to model these states and ensure they're queryable, auditable, and distinct.

Ganymede 1.x's verifier handles this with a binary YES/NO, but the 21/21 answer-absent gate is a blunt instrument: it can't distinguish "no evidence found" from "evidence found but weak." Atlas handles this through confidence thresholds, but conflates "no evidence" with "insufficient evidence."

---

## Decision

Model negative knowledge as **four distinct first-class states** in the Epistemic Graph, with explicit ledger events for each.

### Negative knowledge taxonomy

| State | Meaning | Distinct from | Ledger event |
|-------|---------|---------------|--------------|
| `UNRESOLVED` | Search was conducted; no evidence found | "No answer" — searching is a deliberate act, recorded in the ledger | `INVESTIGATION_COMPLETED` with outcome `unresolved` |
| `INSUFFICIENT` | Evidence found but below support threshold | "Weak answer" — there's something, but not enough to support a claim | `CLAIM_SUPPORTED` → `CLAIM_INSUFFICIENT` when evidence is too weak |
| `CONTRADICTED` | Evidence directly contradicts this claim | "Opposite answer" — the corpus says the opposite | `CLAIM_CONTRADICTED` when contradicting evidence dominates |
| `RETRACTED` | Evidence was removed or invalidated | "Used to know this" — the supporting evidence is gone | `CLAIM_RETRACTED` when supporting evidence is deleted |

### UNRESOLVED — "I looked and didn't find anything"

- Requires an **investigation record** proving that a search was conducted.
- The investigation records: what was searched, which sources were queried, what query was used, what evidence (if any) was found, and why it was insufficient.
- `UNRESOLVED` is distinct from `INSUFFICIENT`: in `UNRESOLVED`, no evidence was found at all. In `INSUFFICIENT`, some evidence was found but it was too weak to support the claim.

### INSUFFICIENT — "I found something, but not enough"

- Evidence exists but is below the confidence threshold for `SUPPORTED`.
- The evidence is retained (not deleted) and displayed to the user.
- `INSUFFICIENT` is a signal to the user: "there might be something here, but we can't establish it yet."
- The system may propose additional sources or investigations to resolve `INSUFFICIENT` claims.

### CONTRADICTED — "The corpus says the opposite"

- Contradicting evidence dominates supporting evidence.
- Both sides are retained (never silently overwritten).
- `CONTRADICTED` is a signal to the user: "the evidence points the other way."
- Resolution requires explicit action (resolve the contradiction, accept the tension, or remove a source).

### RETRACTED — "I used to believe this, but the evidence is gone"

- DELETE-driven: supporting evidence was removed or invalidated.
- The claim record and its history are retained, never silently dropped.
- `RETRACTED` is a signal to the user: "this was once supported, but the evidence was removed."
- The system tracks which sources, if re-ingested, would un-retract the claim.

### Query interface

```python
# What does Ganymede know?
supported = query_claims(status="SUPPORTED", min_confidence=0.7)

# What does Ganymede NOT know (and why)?
not_known = query_claims(status=["UNRESOLVED", "INSUFFICIENT", "CONTRADICTED", "RETRACTED"])

# What was searched for and not found?
unresolved = query_claims(status="UNRESOLVED")
for claim in unresolved:
    investigation = get_investigation(claim.investigation_id)
    print(f"Searched: {investigation.query}, found: {investigation.evidence_found}")

# What used to be known?
retracted = query_claims(status="RETRACTED")
for claim in retracted:
    print(f"Was: {claim.history[-2].to_status} at {claim.history[-2].at}")
    print(f"Because: {claim.history[-1].reason}")
```

---

## Consequences

**Enables:**
- **Honest epistemic reporting**: the system can say "we looked and found nothing" vs. "we found something weak" vs. "we found the opposite" — these are different statements with different implications.
- **Investigation prioritization**: `INSUFFICIENT` claims can be prioritized for additional investigation (more sources, better queries).
- **Regression detection**: a claim that was `SUPPORTED` but is now `RETRACTED` is a regression — the system surfaces this.
- **User trust**: users can see exactly what was searched, what was found, and why a claim is in its current state.

**Costs:**
- Four distinct states to implement and explain
- `UNRESOLVED` requires investigation records (more storage, more complexity)
- The distinction between `INSUFFICIENT` and `UNRESOLVED` may be confusing to users (mitigated by clear UI and documentation)

**Hardens:**
- The "negative knowledge is first-class" principle
- The "no silent mutation" principle (retained history)
- The "epistemic reproducibility" principle (every state is traceable to evidence)

---

## Alternatives considered

### Binary answer/no-answer (Ganymede 1.x model)
Rejected. The 21/21 answer-absent gate is a good start, but it doesn't distinguish "no evidence found" from "evidence found but weak." This distinction is critical for a system that claims to be an "epistemic compiler."

### Confidence threshold only (Atlas model)
Rejected. Atlas's confidence score is a measure of strength, not a measure of epistemic category. A claim with confidence 0.1 because it has one weak source is different from a claim with confidence 0.1 because it has one weak source AND one strong contradiction. The discrete states capture this; a scalar score doesn't.

### Three states (no RETRACTED)
Rejected. RETRACTED is necessary because it captures a real-world event: "the source that supported this claim was removed." Without RETRACTED, a claim that loses its evidence would silently drop to INSUFFICIENT or UNRESOLVED, losing the historical fact that it was once supported.

---

## References

- Ganymede 2.0 SPEC.md §11 (Negative knowledge)
- Ganymede 2.0 SPEC.md §4 (Claim lifecycle — states include UNRESOLVED, INSUFFICIENT, CONTRADICTED, RETRACTED)
- Ganymede 1.x ADR 008/009 (answer verification — what we're generalizing)
- Atlas `confidence.py` (confidence scoring — complementary to, not a replacement for, the state machine)
