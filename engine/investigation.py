"""Phase 10 — Autonomous Investigation Loop.

When a claim's status is INSUFFICIENT, CONTESTED, or a new contradiction
appears, Ganymede proposes investigations. An agent (configured) carries
them out; results feed back into the Epistemic Graph.

This engine:
1. Detects open investigations from the Epistemic Graph
2. Produces an ordered queue (priority: contested > insufficient > unresolved)
3. Each investigation is a self-contained work package with evidence targets
4. Results come back as new evidence proposals (through PolicyEvaluator)

The loop itself is external — driven by `ganymede investigate` CLI or the
investigation scheduler. This module provides the analysis primitives and
work-queue construction.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class EvidenceTarget:
    """A specific thing to look for."""
    target_type: str  # "document", "interview", "record", "corroboration"
    description: str
    source_hint: str = ""
    priority: float = 0.0


@dataclass
class InvestigationPlan:
    """A work package for an investigation."""
    investigation_id: str
    question: str
    status: str = "open"
    claim_ids: List[str] = field(default_factory=list)
    evidence_targets: List[EvidenceTarget] = field(default_factory=list)
    rationale: str = ""
    created_at: float = 0.0
    priority: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "investigation_id": self.investigation_id,
            "question": self.question,
            "status": self.status,
            "claim_ids": self.claim_ids,
            "evidence_targets": [asdict(t) for t in self.evidence_targets],
            "rationale": self.rationale,
            "created_at": self.created_at,
            "priority": self.priority,
        }


def _id(seed: str) -> str:
    return "inv-" + hashlib.sha256(seed.encode()).hexdigest()[:16]


class InvestigationEngine:
    """Detects open questions in the Epistemic Graph and produces plans."""

    def __init__(
        self,
        claims: List[Dict[str, Any]] = None,
        evidence: List[Dict[str, Any]] = None,
        contradictions: List[Dict[str, Any]] = None,
        existing_investigations: List[Dict[str, Any]] = None,
    ):
        self.claims = claims or []
        self.evidence = evidence or []
        self.contradictions = contradictions or []
        self.existing_investigations = existing_investigations or []

    def detect_open_questions(self) -> List[InvestigationPlan]:
        """Scan the Epistemic Graph for gaps that merit investigation."""
        plans: List[InvestigationPlan] = []
        seen_claims: set = set()

        # 1. Contradicted claims — highest priority (paired claims found by
        #    the contradiction detector with opposite polarity)
        for c in self.claims:
            if c.get("status") == "CONTRADICTED":
                cid = c["id"]
                if cid in seen_claims:
                    continue
                seen_claims.add(cid)
                plans.append(self._plan_for_contested(c))

        # 2. Contested claims
        for c in self.claims:
            if c.get("status") == "CONTESTED":
                cid = c["id"]
                if cid in seen_claims:
                    continue
                seen_claims.add(cid)
                plans.append(self._plan_for_contested(c))

        # 3. Insufficient evidence
        for c in self.claims:
            if c.get("status") == "INSUFFICIENT":
                cid = c["id"]
                if cid in seen_claims:
                    continue
                seen_claims.add(cid)
                plans.append(self._plan_for_insufficient(c))

        # 4. Contradictions without investigation
        for con in self.contradictions:
            inv_exists = any(
                set(con.get("claim_ids", [])) & set(inv.get("claim_ids", []))
                for inv in self.existing_investigations
            )
            if inv_exists:
                continue
            plans.append(self._plan_for_contradiction(con))

        # 5. Unresolved temporal claims
        for c in self.claims:
            if c.get("status") == "UNRESOLVED":
                cid = c["id"]
                if cid in seen_claims:
                    continue
                seen_claims.add(cid)
                plans.append(self._plan_for_unresolved(c))

        # Deduplicate by claim set
        plans = self._dedupe(plans)

        # Sort: contested first, then by priority desc
        plans.sort(key=lambda p: p.priority, reverse=True)

        return plans

    def _plan_for_contested(self, claim: Dict[str, Any]) -> InvestigationPlan:
        """Build an investigation plan for a contested claim."""
        claim_id = claim["id"]
        text = claim.get("text", "")
        evidence_ids = claim.get("evidence_ids", [])
        source_ids = claim.get("source_ids", [])

        targets = [
            EvidenceTarget(
                target_type="corroboration",
                description=f"Find additional sources corroborating or refuting: {text[:120]}",
                source_hint=source_ids[0] if source_ids else "",
                priority=1.0,
            ),
            EvidenceTarget(
                target_type="document",
                description=f"Locate primary documents that directly address: {text[:120]}",
                priority=0.9,
            ),
            EvidenceTarget(
                target_type="interview",
                description=f"Identify witnesses or participants who could confirm or deny: {text[:120]}",
                priority=0.7,
            ),
        ]

        return InvestigationPlan(
            investigation_id=_id(f"contested:{claim_id}"),
            question=f"What evidence supports or contradicts the claim that {text[:100]}?",
            status="open",
            claim_ids=[claim_id],
            evidence_targets=targets,
            rationale=f"Claim {claim_id[:12]} is CONTESTED — model refinement detected conflict. Need corroboration or refutation.",
            created_at=time.time(),
            priority=1.0,
        )

    def _plan_for_insufficient(self, claim: Dict[str, Any]) -> InvestigationPlan:
        """Build a plan for a claim with insufficient evidence."""
        claim_id = claim["id"]
        text = claim.get("text", "")

        targets = [
            EvidenceTarget(
                target_type="document",
                description=f"Find primary source that establishes: {text[:120]}",
                priority=0.9,
            ),
            EvidenceTarget(
                target_type="record",
                description=f"Search public records, logs, or databases for: {text[:120]}",
                priority=0.8,
            ),
        ]

        return InvestigationPlan(
            investigation_id=_id(f"insufficient:{claim_id}"),
            question=f"What evidence would establish whether {text[:100]}?",
            status="open",
            claim_ids=[claim_id],
            evidence_targets=targets,
            rationale=f"Claim {claim_id[:12]} has INSUFFICIENT status — evidence gap identified at compile time.",
            created_at=time.time(),
            priority=0.8,
        )

    def _plan_for_contradiction(self, con: Dict[str, Any]) -> InvestigationPlan:
        """Build a plan for an open contradiction."""
        claim_a = con.get("text_a", "")[:80]
        claim_b = con.get("text_b", "")[:80]

        targets = [
            EvidenceTarget(
                target_type="corroboration",
                description=f"Resolve contradiction: '{claim_a}' vs '{claim_b}'",
                priority=1.0,
            ),
            EvidenceTarget(
                target_type="document",
                description=f"Find authoritative source that adjudicates between these two claims",
                priority=0.9,
            ),
        ]

        return InvestigationPlan(
            investigation_id=_id(f"contradiction:{con.get('id', con.get('claim_a_id', 'unknown'))}"),
            question=f"Which claim is correct: '{claim_a}' or '{claim_b}'?",
            status="open",
            claim_ids=[con.get("claim_a_id", ""), con.get("claim_b_id", "")],
            evidence_targets=targets,
            rationale=f"Open contradiction (overlap={con.get('overlap', 0):.2f}) requires adjudication.",
            created_at=time.time(),
            priority=0.95,
        )

    def _plan_for_unresolved(self, claim: Dict[str, Any]) -> InvestigationPlan:
        """Build a plan for an unresolved claim."""
        claim_id = claim["id"]
        text = claim.get("text", "")

        targets = [
            EvidenceTarget(
                target_type="document",
                description=f"Find evidence that resolves the status of: {text[:120]}",
                priority=0.85,
            ),
        ]

        return InvestigationPlan(
            investigation_id=_id(f"unresolved:{claim_id}"),
            question=f"What is the correct status of the claim that {text[:100]}?",
            status="open",
            claim_ids=[claim_id],
            evidence_targets=targets,
            rationale=f"Claim {claim_id[:12]} is UNRESOLVED — needs evidence to determine status.",
            created_at=time.time(),
            priority=0.7,
        )

    def _dedupe(self, plans: List[InvestigationPlan]) -> List[InvestigationPlan]:
        """Deduplicate by claim-id set."""
        seen: set = set()
        unique: List[InvestigationPlan] = []
        for p in plans:
            key = frozenset(p.claim_ids)
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique

    def build_work_queue(self) -> List[Dict[str, Any]]:
        """Produce a JSON-serializable work queue."""
        plans = self.detect_open_questions()
        return [p.to_dict() for p in plans]
