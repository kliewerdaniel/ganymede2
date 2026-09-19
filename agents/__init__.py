"""Ganymede 2.0 agent system — proposal-only, policy-evaluated.

Implements ADR 007: agents propose, policy evaluates, system commits.
No agent can directly mutate the Evidence Graph or Epistemic Graph.

Agent pipeline:
    CorpusCartographer → Extractor → Researcher → EvidenceAnalyst
                              ↓              ↓
                     TemporalAnalyst   ContradictionAnalyst
                              ↓              ↓
                     SynthesisAgent → ArtifactCompiler

Each agent produces proposals. The PolicyEvaluator decides: accept, reject,
needs_review, or defer. Accepted proposals are committed to the graph.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from engine.policy import (
    AgentProposal,
    PolicyEvaluator,
    ProposalOperation,
    ProposalOutcome,
    _generate_proposal_id,
)


class AgentBase(ABC):
    """Base class for all Ganymede agents."""

    agent_id: str = "base"
    agent_version: str = "0.1.0"
    authorized_operations: List[ProposalOperation] = []

    def __init__(self, policy_evaluator: PolicyEvaluator):
        self.policy = policy_evaluator

    @abstractmethod
    async def run(
        self,
        *,
        claims: List[Dict[str, Any]],
        evidence: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
        contradictions: List[Dict[str, Any]],
        investigations: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> List[AgentProposal]:
        """Run the agent and return proposals."""
        ...

    def propose(
        self,
        operation: ProposalOperation,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        rationale: str,
        confidence: float,
        model: Optional[Dict[str, Any]] = None,
    ) -> AgentProposal:
        """Create a proposal with this agent's identity."""
        proposal_id = _generate_proposal_id(self.agent_id, operation.value, inputs)
        return AgentProposal(
            proposal_id=proposal_id,
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            operation=operation.value,
            inputs=inputs,
            outputs=outputs,
            rationale=rationale,
            confidence=confidence,
            policy_version=self.policy.policy_version,
            model=model,
        )


class CorpusCartographer(AgentBase):
    """Identifies corpus structure, sources, and gaps."""

    agent_id = "corpus-cartographer"
    authorized_operations = [ProposalOperation.INGEST, ProposalOperation.EXTRACT]

    async def run(self, *, claims, evidence, sources, contradictions, investigations, context, **kwargs) -> List[AgentProposal]:
        proposals = []

        # Propose gap identification
        if len(sources) == 0:
            proposals.append(self.propose(
                ProposalOperation.INGEST,
                inputs={"corpus_dir": context.get("corpus_dir", "unknown")},
                outputs={"gap": "no_sources", "action": "ingest_required"},
                rationale="No sources found in Evidence Graph. Corpus ingestion required to proceed.",
                confidence=0.95,
            ))
        elif len(claims) < len(sources) * 2:
            proposals.append(self.propose(
                ProposalOperation.EXTRACT,
                inputs={"source_count": len(sources), "claim_count": len(claims)},
                outputs={"gap": "low_extraction_ratio", "target_claims": len(sources) * 3},
                rationale=f"Extraction ratio is low: {len(claims)} claims from {len(sources)} sources. More extraction needed.",
                confidence=0.8,
            ))

        return proposals


class ExtractorAgent(AgentBase):
    """Proposes evidence units, claims, and relationships."""

    agent_id = "extractor"
    authorized_operations = [ProposalOperation.EXTRACT, ProposalOperation.CLAIM_PROPOSE, ProposalOperation.CLAIM_CONTRADICT]

    async def run(self, *, claims, evidence, sources, contradictions, investigations, context, **kwargs) -> List[AgentProposal]:
        proposals = []

        # Propose claims for evidence units without claims
        unassigned = [e for e in evidence if not e.get("claim_id")]
        if unassigned:
            for ev in unassigned[:5]:  # Cap at 5 proposals per run
                claim_id = f"clm-{hashlib.sha256(ev['quote'].encode()).hexdigest()[:32]}"
                proposals.append(self.propose(
                    ProposalOperation.CLAIM_PROPOSE,
                    inputs={"evidence_id": ev["id"], "quote": ev["quote"][:200]},
                    outputs={"claim_id": claim_id, "text": ev["quote"][:200], "evidence_ids": [ev["id"]]},
                    rationale=f"Proposing claim from evidence unit {ev['id'][:12]} — quote contains assertable content.",
                    confidence=0.7,
                ))

        return proposals


class ResearcherAgent(AgentBase):
    """Proposes external lookups and evidence evaluation."""

    agent_id = "researcher"
    authorized_operations = [ProposalOperation.EXTRACT, ProposalOperation.CLAIM_PROPOSE, ProposalOperation.EVALUATE_EVIDENCE]

    async def run(self, *, claims, evidence, sources, contradictions, investigations, context, **kwargs) -> List[AgentProposal]:
        proposals = []

        # Propose external lookups for high-confidence claims from single sources
        for c in claims:
            if c.get("confidence", 0) > 0.6 and len(c.get("source_ids", [])) == 1:
                proposals.append(self.propose(
                    ProposalOperation.EXTRACT,
                    inputs={"claim_id": c["id"], "text": c.get("text", "")[:200]},
                    outputs={"action": "external_lookup", "source_hint": c["source_ids"][0]},
                    rationale=f"High-confidence claim {c['id'][:12]} from single source — propose external corroboration lookup.",
                    confidence=0.6,
                ))
                break  # One proposal per run

        return proposals


class EvidenceAnalyst(AgentBase):
    """Evaluates evidence reliability and detects conflicts."""

    agent_id = "evidence-analyst"
    authorized_operations = [ProposalOperation.EVALUATE_EVIDENCE, ProposalOperation.CLAIM_CONTRADICT]

    async def run(self, *, claims, evidence, sources, contradictions, investigations, context, **kwargs) -> List[AgentProposal]:
        proposals = []

        # Flag evidence units with low reliability for revalidation
        for ev in evidence:
            if ev.get("reliability") is not None and ev["reliability"] < 0.4:
                proposals.append(self.propose(
                    ProposalOperation.EVALUATE_EVIDENCE,
                    inputs={"evidence_id": ev["id"], "reliability": ev["reliability"]},
                    outputs={"action": "revalidate", "evidence_id": ev["id"]},
                    rationale=f"Evidence {ev['id'][:12]} has low reliability ({ev['reliability']:.2f}) — flag for revalidation.",
                    confidence=0.75,
                ))
                break

        return proposals


class TemporalAnalyst(AgentBase):
    """Proposes temporal orderings for claims with timestamps."""

    agent_id = "temporal-analyst"
    authorized_operations = [ProposalOperation.TEMPORAL_ORDER, ProposalOperation.CLAIM_PROPOSE]

    async def run(self, *, claims, evidence, sources, contradictions, investigations, context, **kwargs) -> List[AgentProposal]:
        proposals = []

        # Find claims with evidence that has timestamps
        dated_evidence = [e for e in evidence if e.get("timestamp")]
        if len(dated_evidence) >= 2:
            # Propose temporal ordering
            sorted_ev = sorted(dated_evidence, key=lambda e: e["timestamp"])
            proposals.append(self.propose(
                ProposalOperation.TEMPORAL_ORDER,
                inputs={"evidence_ids": [e["id"] for e in sorted_ev[:5]]},
                outputs={"ordering": [e["id"] for e in sorted_ev[:5]], "timestamps": [e["timestamp"] for e in sorted_ev[:5]]},
                rationale=f"Propose temporal ordering for {len(sorted_ev[:5])} dated evidence units.",
                confidence=0.85,
            ))

        return proposals


class ContradictionAnalyst(AgentBase):
    """Proposes contradiction detections and resolutions."""

    agent_id = "contradiction-analyst"
    authorized_operations = [ProposalOperation.CONTRADICT_DETECT, ProposalOperation.CONTRADICT_RESOLVE]

    async def run(self, *, claims, evidence, sources, contradictions, investigations, context, **kwargs) -> List[AgentProposal]:
        proposals = []

        # Propose resolution for open contradictions
        open_cons = [c for c in contradictions if c.get("status") == "open"]
        for con in open_cons[:2]:
            proposals.append(self.propose(
                ProposalOperation.CONTRADICT_RESOLVE,
                inputs={"contradiction_id": con["id"], "claim_a_id": con["claim_a_id"], "claim_b_id": con["claim_b_id"]},
                outputs={"action": "propose_resolution", "method": "source_priority"},
                rationale=f"Open contradiction {con['id'][:12]} — propose resolution by source priority ranking.",
                confidence=0.5,
            ))

        return proposals


class SynthesisAgent(AgentBase):
    """Proposes claim merges and investigation launches."""

    agent_id = "synthesis-agent"
    authorized_operations = [ProposalOperation.CLAIM_MERGE, ProposalOperation.INVESTIGATION_PROPOSE]

    async def run(self, *, claims, evidence, sources, contradictions, investigations, context, **kwargs) -> List[AgentProposal]:
        proposals = []

        # Propose investigation for contested claims
        contested = [c for c in claims if c.get("status") in ("CONTESTED", "CONTRADICTED")]
        for c in contested[:2]:
            inv_id = f"inv-{hashlib.sha256(c['id'].encode()).hexdigest()[:16]}"
            proposals.append(self.propose(
                ProposalOperation.INVESTIGATION_PROPOSE,
                inputs={"claim_id": c["id"], "status": c["status"]},
                outputs={"investigation_id": inv_id, "question": f"Resolve status of: {c.get('text', '')[:100]}"},
                rationale=f"Claim {c['id'][:12]} is {c['status']} — propose investigation to gather additional evidence.",
                confidence=0.9,
            ))

        return proposals


class ArtifactCompiler(AgentBase):
    """Proposes artifact compilations."""

    agent_id = "artifact-compiler"
    authorized_operations = [ProposalOperation.ARTIFACT_COMPILE]

    async def run(self, *, claims, evidence, sources, contradictions, investigations, context, **kwargs) -> List[AgentProposal]:
        proposals = []

        # Propose artifact compilation if there are supported claims
        supported = [c for c in claims if c.get("status") in ("SUPPORTED", "VALIDATED")]
        if supported:
            proposals.append(self.propose(
                ProposalOperation.ARTIFACT_COMPILE,
                inputs={"supported_claims": len(supported), "total_claims": len(claims)},
                outputs={"action": "compile_artifact", "output_format": "nextjs_static"},
                rationale=f"{len(supported)} supported claims ready for artifact compilation.",
                confidence=0.95,
            ))

        return proposals


# Agent registry
AGENT_REGISTRY: Dict[str, type] = {
    "corpus-cartographer": CorpusCartographer,
    "extractor": ExtractorAgent,
    "researcher": ResearcherAgent,
    "evidence-analyst": EvidenceAnalyst,
    "temporal-analyst": TemporalAnalyst,
    "contradiction-analyst": ContradictionAnalyst,
    "synthesis-agent": SynthesisAgent,
    "artifact-compiler": ArtifactCompiler,
}


class AgentRunner:
    """Runs agents in sequence and processes their proposals."""

    def __init__(self, policy_evaluator: Optional[PolicyEvaluator] = None):
        self.policy = policy_evaluator or PolicyEvaluator()
        self.results: List[Dict[str, Any]] = []

    async def run_pipeline(
        self,
        *,
        claims: List[Dict[str, Any]],
        evidence: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
        contradictions: List[Dict[str, Any]],
        investigations: List[Dict[str, Any]],
        context: Dict[str, Any],
        agent_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run the full agent pipeline and return results."""
        if agent_ids is None:
            agent_ids = list(AGENT_REGISTRY.keys())

        all_proposals = []
        all_decisions = []
        agent_summaries = {}

        for agent_id in agent_ids:
            agent_cls = AGENT_REGISTRY.get(agent_id)
            if agent_cls is None:
                continue

            agent = agent_cls(self.policy)
            proposals = await agent.run(
                claims=claims,
                evidence=evidence,
                sources=sources,
                contradictions=contradictions,
                investigations=investigations,
                context=context,
            )

            decisions = []
            for proposal in proposals:
                decision = self.policy.evaluate(
                    proposal,
                    existing_claim_ids=[c["id"] for c in claims],
                    existing_evidence_ids=[e["id"] for e in evidence],
                )
                decisions.append({
                    "proposal": proposal,
                    "decision": decision,
                })

            agent_summaries[agent_id] = {
                "proposals": len(proposals),
                "accepted": sum(1 for d in decisions if d["decision"].outcome == ProposalOutcome.ACCEPTED.value),
                "rejected": sum(1 for d in decisions if d["decision"].outcome == ProposalOutcome.REJECTED.value),
                "needs_review": sum(1 for d in decisions if d["decision"].outcome == ProposalOutcome.NEEDS_REVIEW.value),
            }

            all_proposals.extend(proposals)
            all_decisions.extend(decisions)

        self.results = all_decisions

        return {
            "agents_run": len(agent_ids),
            "total_proposals": len(all_proposals),
            "accepted": sum(1 for s in agent_summaries.values() for _ in range(s["accepted"])),
            "rejected": sum(1 for s in agent_summaries.values() for _ in range(s["rejected"])),
            "needs_review": sum(1 for s in agent_summaries.values() for _ in range(s["needs_review"])),
            "by_agent": agent_summaries,
        }
