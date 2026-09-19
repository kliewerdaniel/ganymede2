"""Lifecycle — 8-state claim lifecycle state machine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from .confidence import EvidenceRef


class ClaimStatus(str, Enum):
    UNEXAMINED = "UNEXAMINED"
    SUPPORTED = "SUPPORTED"
    VALIDATED = "VALIDATED"
    CONTESTED = "CONTESTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"
    UNRESOLVED = "UNRESOLVED"
    RETRACTED = "RETRACTED"
    SUPERSEDED = "SUPERSEDED"


# Legal transitions: from_state → {to_states}
LEGAL_TRANSITIONS = {
    ClaimStatus.UNEXAMINED: {
        ClaimStatus.SUPPORTED, ClaimStatus.INSUFFICIENT, ClaimStatus.UNRESOLVED,
        ClaimStatus.UNEXAMINED,  # self-loop (no change)
    },
    ClaimStatus.SUPPORTED: {
        ClaimStatus.VALIDATED, ClaimStatus.CONTESTED, ClaimStatus.CONTRADICTED,
        ClaimStatus.INSUFFICIENT, ClaimStatus.RETRACTED, ClaimStatus.SUPERSEDED,
        ClaimStatus.SUPPORTED,  # self-loop
    },
    ClaimStatus.VALIDATED: {
        ClaimStatus.CONTESTED, ClaimStatus.CONTRADICTED, ClaimStatus.RETRACTED,
        ClaimStatus.SUPERSEDED, ClaimStatus.VALIDATED,
    },
    ClaimStatus.CONTESTED: {
        ClaimStatus.CONTRADICTED, ClaimStatus.SUPPORTED, ClaimStatus.SUPERSEDED,
        ClaimStatus.CONTESTED,
    },
    ClaimStatus.CONTRADICTED: {
        ClaimStatus.SUPERSEDED, ClaimStatus.CONTRADICTED,
    },
    ClaimStatus.INSUFFICIENT: {
        ClaimStatus.SUPPORTED, ClaimStatus.UNRESOLVED, ClaimStatus.SUPERSEDED,
        ClaimStatus.INSUFFICIENT,
    },
    ClaimStatus.UNRESOLVED: {
        ClaimStatus.SUPPORTED, ClaimStatus.INSUFFICIENT, ClaimStatus.SUPERSEDED,
        ClaimStatus.UNRESOLVED,
    },
    ClaimStatus.RETRACTED: {
        ClaimStatus.SUPERSEDED, ClaimStatus.RETRACTED,
    },
    ClaimStatus.SUPERSEDED: {
        ClaimStatus.SUPERSEDED,
    },
}


def is_legal_transition(from_status: ClaimStatus, to_status: ClaimStatus) -> bool:
    """Check if a transition is legal."""
    return to_status in LEGAL_TRANSITIONS.get(from_status, set())


def initial_status(
    evidence_refs: List[EvidenceRef],
    confidence: float,
    has_contradictions: bool = False,
) -> ClaimStatus:
    """Determine the initial lifecycle status from evidence and confidence."""
    if not evidence_refs:
        return ClaimStatus.UNRESOLVED

    supporting = [e for e in evidence_refs if e.stance != "contradict"]
    contradicting = [e for e in evidence_refs if e.stance == "contradict"]

    if not supporting:
        return ClaimStatus.CONTRADICTED

    if confidence < 0.2:
        return ClaimStatus.INSUFFICIENT

    if has_contradictions and confidence < 0.5:
        return ClaimStatus.CONTESTED

    if confidence >= 0.7:
        # Check for multiple independent sources
        independent = len({e.independence_key() for e in supporting})
        if independent >= 2:
            return ClaimStatus.VALIDATED
        return ClaimStatus.SUPPORTED

    return ClaimStatus.SUPPORTED


@dataclass
class LifecycleReport:
    passed: bool = False
    no_op_stable: bool = False
    no_illegal_skip: bool = False
    invalidations_justified: bool = False
    transitions_observed: List[dict] = None

    def __post_init__(self):
        if self.transitions_observed is None:
            self.transitions_observed = []
