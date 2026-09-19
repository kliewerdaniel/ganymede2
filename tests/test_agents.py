"""Tests for the agent system (ADR 007 implementation)."""

from __future__ import annotations

import pytest
from engine.policy import (
    AgentProposal,
    PolicyEvaluator,
    ProposalOperation,
    ProposalOutcome,
)
from agents import (
    AgentRunner,
    ArtifactCompiler,
    ContradictionAnalyst,
    CorpusCartographer,
    EvidenceAnalyst,
    ExtractorAgent,
    ResearcherAgent,
    SynthesisAgent,
    TemporalAnalyst,
)


@pytest.fixture
def evaluator():
    return PolicyEvaluator()


@pytest.fixture
def sample_claims():
    return [
        {"id": "clm-abc123", "text": "Chris was a software engineer", "status": "SUPPORTED",
         "confidence": 0.48, "evidence_ids": ["ev-1"], "source_ids": ["src-1"]},
        {"id": "clm-def456", "text": "Not to replace him", "status": "CONTRADICTED",
         "confidence": 0.0, "evidence_ids": [], "source_ids": []},
        {"id": "clm-ghi789", "text": "A high confidence claim needing corroboration",
         "status": "SUPPORTED", "confidence": 0.75, "evidence_ids": ["ev-2"], "source_ids": ["src-1"]},
    ]


@pytest.fixture
def sample_evidence():
    return [
        {"id": "ev-1", "source_id": "src-1", "claim_id": "clm-abc123", "quote": "test", "reliability": 0.8,
         "timestamp": 1700000000.0},
        {"id": "ev-2", "source_id": "src-1", "claim_id": "clm-ghi789", "quote": "test2", "reliability": 0.9,
         "timestamp": 1700001000.0},
        {"id": "ev-3", "source_id": "src-2", "claim_id": None, "quote": "unassigned evidence", "reliability": 0.3,
         "timestamp": 1700002000.0},
    ]


@pytest.fixture
def sample_sources():
    return [
        {"id": "src-1", "type": "conversation", "origin": "test", "text": "test source 1"},
        {"id": "src-2", "type": "document", "origin": "test2", "text": "test source 2"},
    ]


class TestCorpusCartographer:
    def test_no_sources_proposes_ingest(self, evaluator):
        agent = CorpusCartographer(evaluator)
        proposals = asyncio_run(agent.run(
            claims=[], evidence=[], sources=[], contradictions=[], investigations=[],
            context={"corpus_dir": "test"},
        ))
        assert len(proposals) == 1
        assert proposals[0].operation == ProposalOperation.INGEST.value

    def test_low_extraction_ratio_proposes_extract(self, evaluator, sample_claims, sample_evidence, sample_sources):
        agent = CorpusCartographer(evaluator)
        proposals = asyncio_run(agent.run(
            claims=sample_claims, evidence=sample_evidence, sources=sample_sources,
            contradictions=[], investigations=[], context={},
        ))
        assert len(proposals) == 1
        assert proposals[0].operation == ProposalOperation.EXTRACT.value

    def test_authorized_operations(self, evaluator):
        agent = CorpusCartographer(evaluator)
        assert ProposalOperation.INGEST in agent.authorized_operations


class TestExtractorAgent:
    def test_proposes_claims_for_unassigned_evidence(self, evaluator, sample_claims, sample_evidence, sample_sources):
        agent = ExtractorAgent(evaluator)
        proposals = asyncio_run(agent.run(
            claims=sample_claims, evidence=sample_evidence, sources=sample_sources,
            contradictions=[], investigations=[], context={},
        ))
        # ev-3 has no claim_id
        assert len(proposals) >= 1
        assert proposals[0].operation == ProposalOperation.CLAIM_PROPOSE.value


class TestResearcherAgent:
    def test_proposes_external_lookup_for_high_conf_single_source(self, evaluator, sample_claims, sample_evidence, sample_sources):
        agent = ResearcherAgent(evaluator)
        proposals = asyncio_run(agent.run(
            claims=sample_claims, evidence=sample_evidence, sources=sample_sources,
            contradictions=[], investigations=[], context={},
        ))
        assert len(proposals) == 1
        assert proposals[0].operation == ProposalOperation.EXTRACT.value


class TestEvidenceAnalyst:
    def test_flags_low_reliability_evidence(self, evaluator, sample_claims, sample_evidence, sample_sources):
        agent = EvidenceAnalyst(evaluator)
        proposals = asyncio_run(agent.run(
            claims=sample_claims, evidence=sample_evidence, sources=sample_sources,
            contradictions=[], investigations=[], context={},
        ))
        # ev-3 has reliability 0.3
        assert len(proposals) == 1
        assert proposals[0].operation == ProposalOperation.EVALUATE_EVIDENCE.value


class TestTemporalAnalyst:
    def test_proposes_temporal_ordering(self, evaluator, sample_claims, sample_evidence, sample_sources):
        agent = TemporalAnalyst(evaluator)
        proposals = asyncio_run(agent.run(
            claims=sample_claims, evidence=sample_evidence, sources=sample_sources,
            contradictions=[], investigations=[], context={},
        ))
        # ev-3 has timestamp
        assert len(proposals) == 1
        assert proposals[0].operation == ProposalOperation.TEMPORAL_ORDER.value


class TestContradictionAnalyst:
    def test_proposes_resolution_for_open_contradictions(self, evaluator, sample_claims, sample_evidence, sample_sources):
        agent = ContradictionAnalyst(evaluator)
        contradictions = [
            {"id": "con-1", "status": "open", "claim_a_id": "a", "claim_b_id": "b",
             "text_a": "A", "text_b": "B", "overlap": 0.5},
        ]
        proposals = asyncio_run(agent.run(
            claims=sample_claims, evidence=sample_evidence, sources=sample_sources,
            contradictions=contradictions, investigations=[], context={},
        ))
        assert len(proposals) == 1
        assert proposals[0].operation == ProposalOperation.CONTRADICT_RESOLVE.value


class TestSynthesisAgent:
    def test_proposes_investigation_for_contested(self, evaluator, sample_claims, sample_evidence, sample_sources):
        agent = SynthesisAgent(evaluator)
        proposals = asyncio_run(agent.run(
            claims=sample_claims, evidence=sample_evidence, sources=sample_sources,
            contradictions=[], investigations=[], context={},
        ))
        assert len(proposals) == 1
        assert proposals[0].operation == ProposalOperation.INVESTIGATION_PROPOSE.value


class TestArtifactCompiler:
    def test_proposes_artifact_compilation(self, evaluator, sample_claims, sample_evidence, sample_sources):
        agent = ArtifactCompiler(evaluator)
        proposals = asyncio_run(agent.run(
            claims=sample_claims, evidence=sample_evidence, sources=sample_sources,
            contradictions=[], investigations=[], context={},
        ))
        assert len(proposals) == 1
        assert proposals[0].operation == ProposalOperation.ARTIFACT_COMPILE.value

    def test_no_proposal_if_no_supported(self, evaluator, sample_evidence, sample_sources):
        agent = ArtifactCompiler(evaluator)
        all_contested = [
            {"id": "c1", "text": "x", "status": "CONTRADICTED", "confidence": 0,
             "evidence_ids": [], "source_ids": []},
        ]
        proposals = asyncio_run(agent.run(
            claims=all_contested, evidence=sample_evidence, sources=sample_sources,
            contradictions=[], investigations=[], context={},
        ))
        assert len(proposals) == 0


class TestAgentRunner:
    def test_full_pipeline(self, evaluator, sample_claims, sample_evidence, sample_sources):
        runner = AgentRunner()
        result = asyncio_run(runner.run_pipeline(
            claims=sample_claims, evidence=sample_evidence, sources=sample_sources,
            contradictions=[], investigations=[], context={},
        ))
        assert result["agents_run"] == 8
        assert result["total_proposals"] > 0

    def test_selective_agents(self, evaluator, sample_claims, sample_evidence, sample_sources):
        runner = AgentRunner()
        result = asyncio_run(runner.run_pipeline(
            claims=sample_claims, evidence=sample_evidence, sources=sample_sources,
            contradictions=[], investigations=[], context={},
            agent_ids=["corpus-cartographer", "extractor"],
        ))
        assert result["agents_run"] == 2

    def test_results_tracked(self, evaluator, sample_claims, sample_evidence, sample_sources):
        runner = AgentRunner()
        asyncio_run(runner.run_pipeline(
            claims=sample_claims, evidence=sample_evidence, sources=sample_sources,
            contradictions=[], investigations=[], context={},
        ))
        assert len(runner.results) > 0


def asyncio_run(coro):
    """Run an async coroutine synchronously."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
