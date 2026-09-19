"""Tests for the agent policy layer."""

import pytest
from engine.policy import (
    AgentProposal,
    PolicyEvaluator,
    ProposalOperation,
    ProposalOutcome,
    AGENT_AUTHORIZATION,
)


class TestPolicyEvaluator:
    def _make_proposal(self, **kwargs):
        defaults = {
            "proposal_id": "prop-test123",
            "agent_id": "extractor",
            "agent_version": "0.1.0",
            "operation": "CLAIM_PROPOSE",
            "inputs": {"source_id": "src-abc"},
            "outputs": {"claim_id": "clm-xyz"},
            "rationale": "This is a substantive rationale for the proposal.",
            "confidence": 0.8,
        }
        defaults.update(kwargs)
        return AgentProposal(**defaults)

    def test_valid_proposal_accepted(self):
        evaluator = PolicyEvaluator()
        proposal = self._make_proposal()
        decision = evaluator.evaluate(proposal)
        assert decision.outcome == ProposalOutcome.ACCEPTED.value

    def test_missing_agent_id_rejected(self):
        evaluator = PolicyEvaluator()
        proposal = self._make_proposal(agent_id="")
        decision = evaluator.evaluate(proposal)
        assert decision.outcome == ProposalOutcome.REJECTED.value
        assert any("agent_id" in v for v in decision.violations)

    def test_unauthorized_operation_rejected(self):
        evaluator = PolicyEvaluator()
        proposal = self._make_proposal(
            agent_id="corpus-cartographer",
            operation="CLAIM_MERGE",
        )
        decision = evaluator.evaluate(proposal)
        assert decision.outcome == ProposalOutcome.REJECTED.value
        assert any("not authorized" in v for v in decision.violations)

    def test_unknown_agent_rejected(self):
        evaluator = PolicyEvaluator()
        proposal = self._make_proposal(agent_id="unknown-agent")
        decision = evaluator.evaluate(proposal)
        assert decision.outcome == ProposalOutcome.REJECTED.value
        assert any("unknown agent" in v for v in decision.violations)

    def test_short_rationale_rejected(self):
        evaluator = PolicyEvaluator()
        proposal = self._make_proposal(rationale="short")
        decision = evaluator.evaluate(proposal)
        assert decision.outcome == ProposalOutcome.REJECTED.value

    def test_confidence_out_of_range_rejected(self):
        evaluator = PolicyEvaluator()
        proposal = self._make_proposal(confidence=1.5)
        decision = evaluator.evaluate(proposal)
        assert decision.outcome == ProposalOutcome.REJECTED.value
        assert any("confidence" in v for v in decision.violations)

    def test_conflict_needs_review(self):
        evaluator = PolicyEvaluator()
        proposal = self._make_proposal(
            outputs={"claim_id": "clm-existing"},
        )
        decision = evaluator.evaluate(
            proposal,
            existing_claim_ids=["clm-existing"],
        )
        assert decision.outcome == ProposalOutcome.NEEDS_REVIEW.value

    def test_sovereignty_boundary_logged(self):
        evaluator = PolicyEvaluator()
        proposal = self._make_proposal(
            model={
                "provider": "ollama",
                "model": "qwen3:8b",
                "sovereignty_boundary_crossed": True,
                "logged": True,
            }
        )
        decision = evaluator.evaluate(proposal)
        assert decision.outcome == ProposalOutcome.ACCEPTED.value

    def test_sovereignty_boundary_not_logged_rejected(self):
        evaluator = PolicyEvaluator()
        proposal = self._make_proposal(
            model={
                "provider": "ollama",
                "model": "qwen3:8b",
                "sovereignty_boundary_crossed": True,
                "logged": False,
            }
        )
        decision = evaluator.evaluate(proposal)
        assert decision.outcome == ProposalOutcome.REJECTED.value
        assert any("sovereignty" in v for v in decision.violations)

    def test_ledger_event_created(self):
        evaluator = PolicyEvaluator()
        proposal = self._make_proposal()
        decision = evaluator.evaluate(proposal)
        event = evaluator.create_ledger_event(proposal, decision)
        assert event["event_type"] == "PROPOSAL_ACCEPTED"
        assert event["actor"] == "agent:extractor"
        assert event["policy_version"] == "0.1.0"

    def test_authorization_map_complete(self):
        """Every agent has at least one authorized operation."""
        for agent_id, ops in AGENT_AUTHORIZATION.items():
            assert len(ops) > 0, f"Agent {agent_id} has no authorized operations"

    def test_all_operations_have_agents(self):
        """Every operation is authorized for at least one agent."""
        flat = set()
        for ops in AGENT_AUTHORIZATION.values():
            flat.update(ops)
        for op in ProposalOperation:
            assert op in flat, f"Operation {op} has no authorized agent"
