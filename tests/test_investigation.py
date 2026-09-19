"""Tests for the investigation engine (Phase 10)."""

from __future__ import annotations

import pytest
from engine.investigation import (
    EvidenceTarget,
    InvestigationEngine,
    InvestigationPlan,
    _id,
)


class TestEvidenceTarget:
    def test_defaults(self):
        t = EvidenceTarget(target_type="document", description="find X")
        assert t.priority == 0.0
        assert t.source_hint == ""


class TestInvestigationPlan:
    def test_to_dict_has_required_fields(self):
        plan = InvestigationPlan(
            investigation_id="inv-test-001",
            question="test?",
            claim_ids=["clm-abc"],
            evidence_targets=[
                EvidenceTarget(target_type="document", description="find it")
            ],
        )
        d = plan.to_dict()
        assert d["investigation_id"] == "inv-test-001"
        assert d["question"] == "test?"
        assert d["status"] == "open"
        assert len(d["evidence_targets"]) == 1


class TestInvestigationEngine:
    def test_detects_contested(self):
        engine = InvestigationEngine(
            claims=[
                {"id": "c1", "text": "test claim", "status": "CONTESTED", "evidence_ids": ["e1"], "source_ids": ["s1"]},
            ]
        )
        plans = engine.detect_open_questions()
        assert len(plans) == 1
        assert plans[0].priority == 1.0
        assert "c1" in plans[0].claim_ids
        assert len(plans[0].evidence_targets) >= 2

    def test_detects_insufficient(self):
        engine = InvestigationEngine(
            claims=[
                {"id": "c2", "text": "needs evidence", "status": "INSUFFICIENT", "evidence_ids": [], "source_ids": []},
            ]
        )
        plans = engine.detect_open_questions()
        assert len(plans) == 1
        assert plans[0].priority == 0.8
        assert "c2" in plans[0].claim_ids

    def test_detects_contradiction(self):
        engine = InvestigationEngine(
            contradictions=[
                {"id": "con-1", "claim_a_id": "c3", "claim_b_id": "c4",
                 "text_a": "A is true", "text_b": "A is false",
                 "overlap": 0.75, "status": "open"},
            ],
            claims=[
                {"id": "c3", "text": "A is true", "status": "SUPPORTED", "evidence_ids": [], "source_ids": []},
                {"id": "c4", "text": "A is false", "status": "SUPPORTED", "evidence_ids": [], "source_ids": []},
            ],
        )
        plans = engine.detect_open_questions()
        assert len(plans) == 1
        assert plans[0].priority == 0.95
        assert "c3" in plans[0].claim_ids
        assert "c4" in plans[0].claim_ids

    def test_detects_unresolved(self):
        engine = InvestigationEngine(
            claims=[
                {"id": "c5", "text": "still unknown", "status": "UNRESOLVED", "evidence_ids": [], "source_ids": []},
            ]
        )
        plans = engine.detect_open_questions()
        assert len(plans) == 1
        assert plans[0].priority == 0.7

    def test_detects_contradicted(self):
        engine = InvestigationEngine(
            claims=[
                {"id": "c7", "text": "Chris was a software engineer", "status": "CONTRADICTED", "evidence_ids": [], "source_ids": []},
            ]
        )
        plans = engine.detect_open_questions()
        assert len(plans) == 1
        assert plans[0].priority == 1.0
        assert "c7" in plans[0].claim_ids

    def test_supported_not_flagged(self):
        engine = InvestigationEngine(
            claims=[
                {"id": "c6", "text": "established", "status": "SUPPORTED", "evidence_ids": ["e1"], "source_ids": ["s1"]},
            ]
        )
        plans = engine.detect_open_questions()
        assert len(plans) == 0

    def test_priority_ordering(self):
        engine = InvestigationEngine(
            claims=[
                {"id": "c1", "text": "low", "status": "UNRESOLVED", "evidence_ids": [], "source_ids": []},
                {"id": "c2", "text": "high", "status": "CONTESTED", "evidence_ids": ["e1"], "source_ids": []},
                {"id": "c3", "text": "mid", "status": "INSUFFICIENT", "evidence_ids": [], "source_ids": []},
            ]
        )
        plans = engine.detect_open_questions()
        assert len(plans) == 3
        assert plans[0].claim_ids == ["c2"]  # contested first
        assert plans[1].claim_ids == ["c3"]  # insufficient
        assert plans[2].claim_ids == ["c1"]  # unresolved last

    def test_dedupe(self):
        """Same claim set should not produce duplicate investigations."""
        engine = InvestigationEngine(
            claims=[
                {"id": "c1", "text": "x", "status": "CONTESTED", "evidence_ids": [], "source_ids": []},
            ]
        )
        # Running twice should still produce the same investigation ID
        plans1 = engine.detect_open_questions()
        plans2 = engine.detect_open_questions()
        assert len(plans1) == len(plans2)
        assert plans1[0].investigation_id == plans2[0].investigation_id
        assert plans1[0].claim_ids == plans2[0].claim_ids

    def test_build_work_queue(self):
        engine = InvestigationEngine(
            claims=[
                {"id": "c1", "text": "needs work", "status": "CONTESTED", "evidence_ids": [], "source_ids": []},
            ]
        )
        queue = engine.build_work_queue()
        assert isinstance(queue, list)
        assert len(queue) == 1
        assert queue[0]["investigation_id"] == _id("contested:c1")

    def test_existing_investigation_not_recreated(self):
        engine = InvestigationEngine(
            contradictions=[
                {"id": "con-1", "claim_a_id": "c1", "claim_b_id": "c2",
                 "text_a": "A", "text_b": "B", "overlap": 0.5, "status": "open",
                 "claim_ids": ["c1", "c2"]},
            ],
            claims=[
                {"id": "c1", "text": "A", "status": "SUPPORTED", "evidence_ids": [], "source_ids": []},
                {"id": "c2", "text": "B", "status": "SUPPORTED", "evidence_ids": [], "source_ids": []},
            ],
            existing_investigations=[
                {"investigation_id": "inv-existing", "claim_ids": ["c1", "c2"]},
            ],
        )
        plans = engine.detect_open_questions()
        assert len(plans) == 0
