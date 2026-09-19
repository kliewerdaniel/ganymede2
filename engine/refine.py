"""Model refinement — optional Stage 5 enhancement layer.

Implements the spec's "Optional model: claim refinement, relationship proposal"
with the gating rule: absent model -> deterministic layer stands alone.

Every refinement runs through the agent policy layer (ADR 007):
the Extractor agent proposes, PolicyEvaluator decides, only then does the
epistemic store change. Model output is UNTRUSTED data — it is validated
against schema before it can even become a proposal.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .inference import InferenceResult, InferenceProvider, log_inference_event, select_provider
from .policy import AgentProposal, PolicyEvaluator, ProposalOutcome

REFINEMENT_PROMPT_VERSION = "1.0.0"

# Cap on how much source text goes into a refinement prompt (context safety)
MAX_REFINEMENT_CHARS = 4000


# ---------------------------------------------------------------------------
# Refinement proposal types (validated model output)
# ---------------------------------------------------------------------------

@dataclass
class ClaimRefinement:
    """A model-proposed refinement of a raw extracted claim."""
    source_claim_id: str
    source_quote: str
    refined_text: str
    rationale: str
    confidence: float

    def to_proposal_outputs(self) -> Dict[str, Any]:
        return {
            "claim_id": self.source_claim_id,
            "refined_text": self.refined_text,
        }


@dataclass
class RelationshipProposal:
    """A model-proposed typed relationship between two entities."""
    source_entity: str
    target_entity: str
    relation_type: str
    evidence_quote: str
    rationale: str
    confidence: float

    def to_proposal_outputs(self) -> Dict[str, Any]:
        return {
            "source_entity": self.source_entity,
            "target_entity": self.target_entity,
            "relation_type": self.relation_type,
        }


@dataclass
class RefinementReport:
    """Summary of one refinement pass."""
    provider: str = ""
    model: str = ""
    claims_refined: int = 0
    claims_rejected_invalid: int = 0
    relationships_proposed: int = 0
    relationships_rejected_invalid: int = 0
    proposals_accepted: int = 0
    proposals_needs_review: int = 0
    proposals_rejected: int = 0
    inference_events: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt contracts (versioned)
# ---------------------------------------------------------------------------

CLAIM_REFINEMENT_PROMPT = """You are refining raw extracted claims for a knowledge graph.

Given a QUOTE from a source document, produce a cleaner, self-contained claim:
- Remove conversational noise ("Daniel:", "I think", filler)
- Keep the factual assertion intact — do NOT add information not in the quote
- Keep it one sentence
- If the quote is a question or contains no assertion, set refined_text to null

QUOTE: {quote}"""

CLAIM_REFINEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "refined_text": {"type": ["string", "null"]},
        "rationale": {"type": "string"},
    },
    "required": ["refined_text", "rationale"],
}

RELATIONSHIP_PROMPT = """You are proposing relationships between entities for a knowledge graph.

Given TEXT from a source document, identify at most one clear relationship
between two named entities that the text directly supports.
Allowed relation types: {relation_types}

Rules:
- Only use entities explicitly named in the text
- Only propose relationships the text directly states or clearly implies
- If no clear relationship exists, reply with an empty proposals list

TEXT: {text}"""

RELATIONSHIP_SCHEMA = {
    "type": "object",
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_entity": {"type": "string"},
                    "target_entity": {"type": "string"},
                    "relation_type": {"type": "string"},
                    "evidence_quote": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["source_entity", "target_entity", "relation_type", "evidence_quote", "rationale"],
            },
        },
    },
    "required": ["proposals"],
}

ALLOWED_RELATION_TYPES = [
    "family_of",
    "friend_of",
    "worked_at",
    "studied_at",
    "lived_in",
    "member_of",
    "creator_of",
    "influenced_by",
    "located_in",
    "co_worker_of",
]


# ---------------------------------------------------------------------------
# Validation of untrusted model output
# ---------------------------------------------------------------------------

def _valid_confidence(value: Any) -> Optional[float]:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return None
    return c if 0.0 <= c <= 1.0 else None


def validate_claim_refinement(
    model_output: Any, *, source_claim_id: str, source_quote: str
) -> Optional[ClaimRefinement]:
    """Validate untrusted model output into a ClaimRefinement, or None."""
    if not isinstance(model_output, dict):
        return None
    refined = model_output.get("refined_text")
    rationale = model_output.get("rationale", "")
    if not isinstance(refined, str) or not refined.strip():
        return None
    if not isinstance(rationale, str) or len(rationale) < 10:
        return None
    refined = refined.strip()
    if len(refined) > 400:
        return None
    # The refinement must not be a pure copy with nothing improved AND must
    # not be wildly longer than the source (hallucination guard)
    if len(refined) > len(source_quote) * 3 + 50:
        return None
    confidence = _valid_confidence(model_output.get("confidence", 0.5)) or 0.5
    return ClaimRefinement(
        source_claim_id=source_claim_id,
        source_quote=source_quote,
        refined_text=refined,
        rationale=rationale,
        confidence=confidence,
    )


def validate_relationship_proposals(model_output: Any) -> List[RelationshipProposal]:
    """Validate untrusted model output into a list of RelationshipProposal."""
    proposals: List[RelationshipProposal] = []
    if not isinstance(model_output, dict):
        return proposals
    raw_list = model_output.get("proposals")
    if not isinstance(raw_list, list):
        return proposals
    for raw in raw_list[:5]:  # cap at 5 per source
        if not isinstance(raw, dict):
            continue
        source = raw.get("source_entity")
        target = raw.get("target_entity")
        rel_type = raw.get("relation_type")
        quote = raw.get("evidence_quote", "")
        rationale = raw.get("rationale", "")
        if not all(isinstance(x, str) and x.strip() for x in (source, target, rel_type)):
            continue
        if rel_type not in ALLOWED_RELATION_TYPES:
            continue
        if not isinstance(quote, str) or not quote.strip():
            continue
        if not isinstance(rationale, str) or len(rationale) < 10:
            continue
        confidence = _valid_confidence(raw.get("confidence", 0.5)) or 0.5
        proposals.append(
            RelationshipProposal(
                source_entity=source.strip() if source else "",
                target_entity=target.strip() if target else "",
                relation_type=rel_type,
                evidence_quote=quote.strip(),
                rationale=rationale,
                confidence=confidence,
            )
        )
    return proposals


# ---------------------------------------------------------------------------
# Refinement pass
# ---------------------------------------------------------------------------

@dataclass
class RefinementTarget:
    """One raw claim offered for refinement."""
    claim_id: str
    text: str
    quote: str


def refine_claims(
    targets: List[RefinementTarget],
    *,
    provider: Optional[InferenceProvider] = None,
    model: str = "qwen3:8b",
    evaluator: Optional[PolicyEvaluator] = None,
    existing_claim_ids: Optional[List[str]] = None,
    max_targets: int = 20,
) -> RefinementReport:
    """Refine raw claims through the model + policy pipeline.

    Pipeline per target:
      model.extract (validated) -> Extractor agent proposal -> policy evaluate
    The deterministic layer stands alone: no provider -> empty report, no error.
    """
    report = RefinementReport()
    if provider is None:
        provider = select_provider()
    if provider is None:
        report.errors.append("no inference provider available — refinement skipped")
        return report
    if evaluator is None:
        evaluator = PolicyEvaluator()

    report.provider = provider.name
    report.model = model

    for target in targets[:max_targets]:
        prompt = CLAIM_REFINEMENT_PROMPT.format(quote=target.quote[:MAX_REFINEMENT_CHARS])
        result = provider.extract(prompt, model=model, schema=CLAIM_REFINEMENT_SCHEMA)
        report.inference_events.append(log_inference_event(
            result, prompt_contract_version=REFINEMENT_PROMPT_VERSION
        ))
        if not result.ok:
            report.errors.append(f"claim {target.claim_id}: {result.error}")
            continue

        refinement = validate_claim_refinement(
            result.output, source_claim_id=target.claim_id, source_quote=target.quote
        )
        if refinement is None:
            report.claims_rejected_invalid += 1
            continue

        proposal = AgentProposal(
            proposal_id=_proposal_id("extractor", "CLAIM_PROPOSE", target.claim_id, refinement.refined_text),
            agent_id="extractor",
            agent_version="0.1.0",
            operation="CLAIM_PROPOSE",
            inputs={"source_claim_id": target.claim_id, "source_quote": target.quote},
            outputs=refinement.to_proposal_outputs(),
            rationale=refinement.rationale,
            confidence=refinement.confidence,
            model={
                "provider": provider.name,
                "model": model,
                "sovereignty_boundary_crossed": provider.sovereignty_crossed,
                "logged": True,
                "prompt_contract_version": REFINEMENT_PROMPT_VERSION,
            },
        )
        decision = evaluator.evaluate(proposal, existing_claim_ids=existing_claim_ids or [])
        if decision.outcome == ProposalOutcome.ACCEPTED.value:
            report.proposals_accepted += 1
        elif decision.outcome == ProposalOutcome.NEEDS_REVIEW.value:
            report.proposals_needs_review += 1
        else:
            report.proposals_rejected += 1
        report.claims_refined += 1

    return report


def propose_relationships(
    texts: List[Dict[str, str]],
    *,
    provider: Optional[InferenceProvider] = None,
    model: str = "qwen3:8b",
    evaluator: Optional[PolicyEvaluator] = None,
    max_texts: int = 10,
) -> RefinementReport:
    """Propose typed relationships from source texts through the model + policy pipeline.

    texts: list of {"source_id": ..., "text": ...} dicts.
    """
    report = RefinementReport()
    if provider is None:
        provider = select_provider()
    if provider is None:
        report.errors.append("no inference provider available — refinement skipped")
        return report
    if evaluator is None:
        evaluator = PolicyEvaluator()

    report.provider = provider.name
    report.model = model

    for item in texts[:max_texts]:
        text = item.get("text", "")
        if not text.strip():
            continue
        prompt = RELATIONSHIP_PROMPT.format(
            relation_types=", ".join(ALLOWED_RELATION_TYPES),
            text=text[:MAX_REFINEMENT_CHARS],
        )
        result = provider.extract(prompt, model=model, schema=RELATIONSHIP_SCHEMA)
        report.inference_events.append(log_inference_event(
            result, prompt_contract_version=REFINEMENT_PROMPT_VERSION
        ))
        if not result.ok:
            report.errors.append(f"source {item.get('source_id', '?')}: {result.error}")
            continue

        proposals = validate_relationship_proposals(result.output)
        if not proposals:
            report.relationships_rejected_invalid += 1
            continue

        for rel in proposals:
            proposal = AgentProposal(
                proposal_id=_proposal_id("extractor", "CLAIM_PROPOSE", rel.source_entity, rel.target_entity, rel.relation_type),
                agent_id="extractor",
                agent_version="0.1.0",
                operation="CLAIM_PROPOSE",
                inputs={
                    "source_id": item.get("source_id", ""),
                    "evidence_quote": rel.evidence_quote,
                },
                outputs=rel.to_proposal_outputs(),
                rationale=rel.rationale,
                confidence=rel.confidence,
                model={
                    "provider": provider.name,
                    "model": model,
                    "sovereignty_boundary_crossed": provider.sovereignty_crossed,
                    "logged": True,
                    "prompt_contract_version": REFINEMENT_PROMPT_VERSION,
                },
            )
            decision = evaluator.evaluate(proposal)
            if decision.outcome == ProposalOutcome.ACCEPTED.value:
                report.proposals_accepted += 1
            elif decision.outcome == ProposalOutcome.NEEDS_REVIEW.value:
                report.proposals_needs_review += 1
            else:
                report.proposals_rejected += 1
            report.relationships_proposed += 1

    return report


def _proposal_id(*parts: str) -> str:
    return "prop-" + hashlib.sha256(":".join(parts).encode()).hexdigest()[:32]
