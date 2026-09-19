# ADR 007: Agent authority model — proposal-only, policy-evaluated

**Status:** Accepted
**Date:** September 2026
**Deciders:** Conrad (Daniel Kliewer)
**Review trigger:** Before Phase 6 implementation begins, or when a new agent role is proposed.

---

## Context

Ganymede 2.0's agent system must enforce a strict separation: agents propose operations, but the system's policy layer evaluates and commits them. The agent is never both investigator and judge of its own claims. The question is how to structure this proposal/evaluation cycle, what authority agents actually have, and how to prevent silent mutation of epistemic state.

Atlas uses a "loop" with personas (Skeptic, etc.) that generate questions and evaluate claims. Atlas's agents are more autonomous — they can directly propose and evaluate claims within the loop. Ganymede 2.0 needs a stricter model because the litigation domain requires stronger accountability.

---

## Decision

Agents are **proposal-only**. They emit typed proposals that the policy layer evaluates against schema and policy before committing. No agent can directly mutate the Evidence Graph or Epistemic Graph.

### Agent proposal schema

```python
@dataclass
class AgentProposal:
    proposal_id: str
    agent_id: str                    # e.g., "corpus-cartographer", "extractor"
    agent_version: str               # semantic version of the agent
    operation: str                   # INGEST, EXTRACT, CLAIM_PROPOSE, CLAIM_CONTRADICT, etc.
    inputs: Dict[str, Any]           # source IDs, evidence IDs, claim IDs, etc.
    outputs: Dict[str, Any]          # proposed claims, status changes, etc.
    rationale: str                   # human-readable reasoning
    confidence: float                # agent's self-reported confidence [0, 1]
    policy_version: str              # policy version evaluated against
    timestamp: float
    model: Optional[Dict]            # if inference was used (from ADR 006)
```

### Agent roles (proposal-only)

| Agent | Proposes | Never does |
|-------|----------|------------|
| `CorpusCartographer` | New sources, corpus structure, gap identification | Directly ingest sources |
| `Extractor` | Evidence units, claims, relationships | Directly write to Evidence Graph |
| `Researcher` | External lookups (scoped, logged) | Directly add external evidence |
| `EvidenceAnalyst` | Evidence evaluations, reliability scores | Directly change evidence records |
| `TemporalAnalyst` | Temporal orderings, event sequences | Directly modify claims |
| `ContradictionAnalyst` | Contradiction detections, resolutions | Directly resolve contradictions |
| `SynthesisAgent` | Claim merges, narrative structures | Directly create artifacts |
| `ArtifactCompiler` | Artifact views, narrative orderings | Directly deploy artifacts |

### Policy layer evaluation

The policy layer evaluates every proposal against:

1. **Schema validity** — Does the proposal conform to the schema?
2. **Epistemic policy compliance** — Does the proposal violate any epistemic invariants? (no silent mutation, no self-judging, no evidence contamination)
3. **Sovereignty boundary** — Was external inference used? Is it logged?
4. **Conflict detection** — Does the proposal conflict with existing claims? (triggers contradiction detection)
5. **Authority scope** — Is the agent authorized for this operation?

### Evaluation outcomes

| Outcome | Meaning | Action |
|---------|---------|--------|
| `accepted` | Proposal is valid and policy-compliant | Commit to Epistemic Graph, record in ledger |
| `rejected` | Proposal violates policy | Record rejection in ledger, return to agent with reason |
| `needs_review` | Proposal is valid but conflicts with existing claims | Queue for human review, record in ledger |
| `deferred` | Proposal requires information not yet available | Queue for re-evaluation when information arrives |

### Ledger recording

Every proposal evaluation is recorded as a ledger event:

```python
{
    "id": "evt-...",
    "actor": "agent:extractor",
    "operation": "CLAIM_PROPOSED",
    "inputs": {"proposal_id": "prop-...", "agent_id": "extractor"},
    "outputs": {"claim_id": "clm-...", "outcome": "accepted"},
    "policy_version": "1.0.0",
    "parent_event_id": None,
    "timestamp": ...,
}
```

---

## Consequences

**Enables:**
- **Accountability**: every agent action is recorded and evaluable
- **Safety**: no agent can silently corrupt epistemic state
- **Auditability**: the full history of agent proposals and their outcomes is retained
- **Flexibility**: new agents can be added without changing the policy layer (they just emit proposals)

**Costs:**
- Proposal/evaluation cycle adds latency
- Policy layer adds code complexity
- Agents cannot act autonomously (by design)

**Hardens:**
- The "agent must never be both investigator and judge" principle
- The "no silent mutation" principle
- The "epistemic reproducibility" principle

---

## Alternatives considered

### Autonomous agents (Atlas model)
Rejected. Atlas's loop allows agents to propose and evaluate claims within the same loop. This is appropriate for a research tool but not for a system where epistemic state has legal implications. Ganymede 2.0 needs stronger accountability.

### Human-in-the-loop for every proposal
Rejected. This would be too slow for a system that may process hundreds of claims. The policy layer handles routine proposals; humans review only conflicts and edge cases.

### Fixed agent roles (no extensibility)
Rejected. The agent system must be extensible — new agents should be able to be added without changing the policy layer.

---

## References

- Ganymede 2.0 SPEC.md §7 (Agent system)
- Atlas `loop.py` (autonomous loop — what we're diverging from)
- Atlas `personas.py` (persona-based question generation — what we're extending)
