"""Confidence scoring — a real function, not a vibe."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

DAY = 86400.0

WEIGHTS = {
    "independence": 0.40,
    "reliability": 0.25,
    "recency": 0.15,
    "corroboration": 0.20,
}

DEFAULT_RELIABILITY = 0.5
HALF_LIFE_DAYS = 540.0


@dataclass
class EvidenceRef:
    evidence_id: str
    source_id: str
    domain: str = ""
    author: str = ""
    stance: str = "support"
    reliability: Optional[float] = None
    timestamp: Optional[float] = None
    quote: str = ""
    similarity_to_siblings: float = 0.0

    def independence_key(self) -> str:
        return (self.domain or self.author or self.source_id).strip().lower()


@dataclass
class ConfidenceResult:
    score: float
    terms: Dict[str, float] = field(default_factory=dict)
    independent_sources: int = 0
    supporting: int = 0
    contradicting: int = 0
    contested: bool = False
    notes: List[str] = field(default_factory=list)

    def as_dict(self):
        return {
            "score": round(self.score, 4),
            "terms": {k: round(v, 4) for k, v in self.terms.items()},
            "independent_sources": self.independent_sources,
            "supporting": self.supporting,
            "contradicting": self.contradicting,
            "contested": self.contested,
            "notes": self.notes,
        }


def _independent_count(evs: Sequence[EvidenceRef]) -> int:
    return len({e.independence_key() for e in evs if e.independence_key()})


def _independence_term(n: int) -> float:
    if n <= 0:
        return 0.0
    return 1.0 - math.exp(-0.7 * n)


def _reliability_term(evs: Sequence[EvidenceRef], prior: float) -> float:
    if not evs:
        return 0.0
    vals = [prior if e.reliability is None else max(0.0, min(1.0, e.reliability)) for e in evs]
    best = max(vals)
    mean = sum(vals) / len(vals)
    return max(0.0, min(1.0, (2 * best + mean) / 3.0))


def _recency_term(evs: Sequence[EvidenceRef], now: float) -> float:
    stamps = [e.timestamp for e in evs if e.timestamp]
    if not stamps:
        return 0.5
    newest = max(stamps)
    age_days = max(0.0, (now - newest) / DAY)
    return float(0.5 ** (age_days / HALF_LIFE_DAYS))


def _corroboration_term(evs: Sequence[EvidenceRef]) -> float:
    if len(evs) < 2:
        return 0.0
    n_ind = _independent_count(evs)
    if n_ind < 2:
        return 0.1
    avg_sim = sum(min(1.0, max(0.0, e.similarity_to_siblings)) for e in evs) / len(evs)
    breadth = min(1.0, (n_ind - 1) / 3.0)
    return max(0.0, breadth * (1.0 - 0.8 * avg_sim))


def _contradiction_penalty(support, contra, prior):
    if not contra:
        return 1.0
    s_strength = _independence_term(_independent_count(support)) * _reliability_term(support, prior)
    c_strength = _independence_term(_independent_count(contra)) * _reliability_term(contra, prior)
    if s_strength <= 0:
        return 0.25
    ratio = c_strength / (s_strength + c_strength)
    return max(0.15, 1.0 - ratio)


def score_claim(
    evidence: Iterable[EvidenceRef],
    *,
    reliability_prior: float = DEFAULT_RELIABILITY,
    now: Optional[float] = None,
) -> ConfidenceResult:
    evs = list(evidence)
    now = now if now is not None else time.time()
    support = [e for e in evs if e.stance != "contradict"]
    contra = [e for e in evs if e.stance == "contradict"]

    if not support:
        return ConfidenceResult(
            score=0.0,
            terms={
                "independence": 0.0,
                "reliability": 0.0,
                "recency": 0.0,
                "corroboration": 0.0,
                "contradiction_penalty": 1.0,
            },
            supporting=0,
            contradicting=len(contra),
            contested=bool(contra),
            notes=["no supporting evidence: claim is asserted, not evidenced"],
        )

    terms = {
        "independence": _independence_term(_independent_count(support)),
        "reliability": _reliability_term(support, reliability_prior),
        "recency": _recency_term(support, now),
        "corroboration": _corroboration_term(support),
    }
    base = sum(WEIGHTS[k] * v for k, v in terms.items())
    penalty = _contradiction_penalty(support, contra, reliability_prior)
    score = max(0.0, min(1.0, base * penalty))

    notes = []
    if contra:
        notes.append(
            f"contested: {len(contra)} contradicting evidence item(s); penalty x{penalty:.2f}"
        )
    if not support:
        notes.append("no supporting evidence: claim is asserted, not evidenced")
    terms["contradiction_penalty"] = penalty

    return ConfidenceResult(
        score=score,
        terms=terms,
        independent_sources=_independent_count(support),
        supporting=len(support),
        contradicting=len(contra),
        contested=bool(contra),
        notes=notes,
    )
