"""Agent policy layer — proposal-only, policy-evaluated.

Implements ADR 007: agents propose, policy evaluates, system commits.
No agent can directly mutate the Evidence Graph or Epistemic Graph.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ProposalOperation(str, Enum):
    INGEST = "INGEST"
    EXTRACT = "EXTRACT"
    CLAIM_PROPOSE = "CLAIM_PROPOSE"
    CLAIM_CONTRADICT = "CLAIM_CONTRADICT"
    EVALUATE_EVIDENCE = "EVALUATE_EVIDENCE"
    TEMPORAL_ORDER = "TEMPORAL_ORDER"
    CONTRADICT_DETECT = "CONTRADICT_DETECT"
    CONTRADICT_RESOLVE = "CONTRADICT_RESOLVE"
    CLAIM_MERGE = "CLAIM_MERGE"
    INVESTIGATION_PROPOSE = "INVESTIGATION_PROPOSE"
    ARTIFACT_COMPILE = "ARTIFACT_COMPILE"


class ProposalOutcome(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
    DEFERRED = "deferred"


# Agent → authorized operations
AGENT_AUTHORIZATION: Dict[str, List[ProposalOperation]] = {
    "corpus-cartographer": [
        ProposalOperation.INGEST,
        ProposalOperation.EXTRACT,
    ],
    "extractor": [
        ProposalOperation.EXTRACT,
        ProposalOperation.CLAIM_PROPOSE,
        ProposalOperation.CLAIM_CONTRADICT,
    ],
    "researcher": [
        ProposalOperation.EXTRACT,
        ProposalOperation.CLAIM_PROPOSE,
        ProposalOperation.EVALUATE_EVIDENCE,
    ],
    "evidence-analyst": [
        ProposalOperation.EVALUATE_EVIDENCE,
        ProposalOperation.CLAIM_CONTRADICT,
    ],
    "temporal-analyst": [
        ProposalOperation.TEMPORAL_ORDER,
        ProposalOperation.CLAIM_PROPOSE,
    ],
    "contradiction-analyst": [
        ProposalOperation.CONTRADICT_DETECT,
        ProposalOperation.CONTRADICT_RESOLVE,
    ],
    "synthesis-agent": [
        ProposalOperation.CLAIM_MERGE,
        ProposalOperation.INVESTIGATION_PROPOSE,
    ],
    "artifact-compiler": [
        ProposalOperation.ARTIFACT_COMPILE,
    ],
}


@dataclass
class AgentProposal:
    """A proposal from an agent. Proposal-only — no direct state mutation."""
    proposal_id: str
    agent_id: str
    agent_version: str
    operation: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    rationale: str
    confidence: float
    policy_version: str = "0.1.0"
    timestamp: float = field(default_factory=time.time)
    model: Optional[Dict[str, Any]] = None


@dataclass
class PolicyDecision:
    """Result of policy evaluation."""
    proposal_id: str
    outcome: str
    reason: str
    violations: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


def _generate_proposal_id(agent_id: str, operation: str, inputs: Dict) -> str:
    """Deterministic proposal ID."""
    canonical = f"{agent_id}:{operation}:{sorted(inputs.items())}"
    return f"prop-{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"


class PolicyEvaluator:
    """Evaluates agent proposals against epistemic policy."""

    def __init__(self, policy_version: str = "0.1.0"):
        self.policy_version = policy_version

    def evaluate(
        self,
        proposal: AgentProposal,
        *,
        existing_claim_ids: Optional[List[str]] = None,
        existing_evidence_ids: Optional[List[str]] = None,
    ) -> PolicyDecision:
        """Evaluate a proposal against all policy checks."""
        violations = []

        # 1. Schema validity
        schema_violations = self._check_schema(proposal)
        violations.extend(schema_violations)

        # 2. Authority scope
        auth_violations = self._check_authorization(proposal)
        violations.extend(auth_violations)

        # 3. Sovereignty boundary
        sov_violations = self._check_sovereignty(proposal)
        violations.extend(sov_violations)

        # 4. Conflict detection
        conflict_violations = self._check_conflicts(
            proposal,
            existing_claim_ids=existing_claim_ids or [],
            existing_evidence_ids=existing_evidence_ids or [],
        )
        violations.extend(conflict_violations)

        # 5. Epistemic invariants
        epistemic_violations = self._check_epistemic_invariants(proposal)
        violations.extend(epistemic_violations)

        if violations:
            return PolicyDecision(
                proposal_id=proposal.proposal_id,
                outcome=ProposalOutcome.REJECTED.value,
                reason=f"Policy violations: {'; '.join(violations)}",
                violations=violations,
            )

        # Check for conflicts that need review
        if self._has_conflicts(proposal, existing_claim_ids or []):
            return PolicyDecision(
                proposal_id=proposal.proposal_id,
                outcome=ProposalOutcome.NEEDS_REVIEW.value,
                reason="Proposal conflicts with existing claims",
            )

        return PolicyDecision(
            proposal_id=proposal.proposal_id,
            outcome=ProposalOutcome.ACCEPTED.value,
            reason="Proposal is policy-compliant",
        )

    def _check_schema(self, proposal: AgentProposal) -> List[str]:
        """Check proposal schema validity."""
        violations = []
        if not proposal.proposal_id:
            violations.append("missing proposal_id")
        if not proposal.agent_id:
            violations.append("missing agent_id")
        if not proposal.operation:
            violations.append("missing operation")
        if not proposal.rationale or len(proposal.rationale) < 10:
            violations.append("rationale too short (min 10 chars)")
        if not 0.0 <= proposal.confidence <= 1.0:
            violations.append(f"confidence {proposal.confidence} out of range [0, 1]")
        if proposal.operation not in [op.value for op in ProposalOperation]:
            violations.append(f"unknown operation: {proposal.operation}")
        return violations

    def _check_authorization(self, proposal: AgentProposal) -> List[str]:
        """Check if agent is authorized for this operation."""
        violations = []
        allowed = AGENT_AUTHORIZATION.get(proposal.agent_id, [])
        if not allowed:
            violations.append(f"unknown agent: {proposal.agent_id}")
        elif proposal.operation not in [op.value for op in allowed]:
            violations.append(
                f"agent '{proposal.agent_id}' not authorized for '{proposal.operation}'"
            )
        return violations

    def _check_sovereignty(self, proposal: AgentProposal) -> List[str]:
        """Check sovereignty boundary — external inference must be logged."""
        violations = []
        if proposal.model:
            model = proposal.model
            if not model.get("provider"):
                violations.append("model metadata missing 'provider'")
            if not model.get("model"):
                violations.append("model metadata missing 'model'")
            if model.get("sovereignty_boundary_crossed") and not model.get("logged"):
                violations.append("sovereignty boundary crossed but not logged")
        return violations

    def _check_conflicts(
        self,
        proposal: AgentProposal,
        existing_claim_ids: List[str],
        existing_evidence_ids: List[str],
    ) -> List[str]:
        """Check for conflicts with existing state."""
        violations = []
        if proposal.operation == ProposalOperation.CLAIM_PROPOSE.value:
            proposed_claim_id = proposal.outputs.get("claim_id")
            if proposed_claim_id and proposed_claim_id in existing_claim_ids:
                # Not a violation per se — will be handled as NEEDS_REVIEW
                pass
        return violations

    def _check_epistemic_invariants(self, proposal: AgentProposal) -> List[str]:
        """Check epistemic invariants."""
        violations = []

        # No self-judging: an agent cannot evaluate its own claims
        if proposal.operation == ProposalOperation.EVALUATE_EVIDENCE.value:
            claim_id = proposal.inputs.get("claim_id")
            # If the agent previously proposed this claim, flag it
            if claim_id and proposal.outputs.get("self_judging"):
                violations.append("agent cannot evaluate its own claims (no self-judging)")

        # No silent mutation: all changes must have rationale
        if proposal.operation in [
            ProposalOperation.CLAIM_PROPOSE.value,
            ProposalOperation.CLAIM_CONTRADICT.value,
        ]:
            if not proposal.rationale or len(proposal.rationale) < 20:
                violations.append("claim proposals require substantive rationale (min 20 chars)")

        return violations

    def _has_conflicts(self, proposal: AgentProposal, existing_claim_ids: List[str]) -> bool:
        """Check if proposal conflicts with existing claims."""
        if proposal.operation == ProposalOperation.CLAIM_PROPOSE.value:
            proposed_claim_id = proposal.outputs.get("claim_id")
            if proposed_claim_id and proposed_claim_id in existing_claim_ids:
                return True
        return False

    def create_ledger_event(
        self,
        proposal: AgentProposal,
        decision: PolicyDecision,
    ) -> Dict[str, Any]:
        """Create a ledger event for a proposal evaluation."""
        return {
            "id": f"evt-{hashlib.sha256(f'{proposal.proposal_id}-{decision.outcome}-{time.time()}'.encode()).hexdigest()[:32]}",
            "event_type": f"PROPOSAL_{decision.outcome.upper()}",
            "actor": f"agent:{proposal.agent_id}",
            "operation": proposal.operation,
            "inputs": {
                "proposal_id": proposal.proposal_id,
                "agent_id": proposal.agent_id,
                "confidence": proposal.confidence,
            },
            "outputs": {
                "outcome": decision.outcome,
                "reason": decision.reason,
                "violations": decision.violations,
            },
            "input_hashes": [proposal.proposal_id],
            "output_hashes": [],
            "model": proposal.model,
            "policy_version": self.policy_version,
            "parent_event_id": None,
            "metadata": {
                "agent_version": proposal.agent_version,
                "rationale": proposal.rationale,
            },
        }
