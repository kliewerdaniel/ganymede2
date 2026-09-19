"""Artifact IR and compiler.

Transforms the Epistemic Graph into a JSON-based Artifact IR,
then compiles that IR into simpler intermediates:
- Narrative document (Markdown)
- Knowledge graph (JSON)
- Character dossiers (Markdown + JSON)
- Timeline (JSON)
- Contradiction report (Markdown)
- Source inventory (JSON)
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class ClaimExport:
    id: str
    text: str
    normalized: str
    status: str
    confidence: float
    confidence_terms: Dict[str, Any] = field(default_factory=dict)
    evidence_ids: List[str] = field(default_factory=list)
    source_ids: List[str] = field(default_factory=list)
    entity_ids: List[str] = field(default_factory=list)
    contradiction_ids: List[str] = field(default_factory=list)
    derived_from: List[str] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    speakers: Dict[str, int] = field(default_factory=dict)  # speaker -> evidence count
    voice_class: Optional[str] = None  # model-derived, untrusted; excluded from fingerprint
    compiler_version: str = "0.1.0"
    policy_version: str = "0.1.0"


@dataclass
class EvidenceExport:
    id: str
    source_id: str
    structural_unit_id: Optional[str] = None
    claim_id: Optional[str] = None
    speaker: Optional[str] = None
    domain: Optional[str] = None
    author: Optional[str] = None
    stance: str = "support"
    quote: str = ""
    offset: int = 0
    timestamp: Optional[float] = None
    reliability: Optional[float] = None
    source_checksum: str = ""
    parser_version: str = "0.1.0"


@dataclass
class EntityExport:
    id: str
    name: str
    normalized: str
    mentions: int = 0
    entity_type: str = "unknown"
    source_ids: List[str] = field(default_factory=list)


@dataclass
class ContradictionExport:
    id: str
    claim_a_id: str
    claim_b_id: str
    text_a: str
    text_b: str
    overlap: float
    entity_id: Optional[str] = None
    sources_a: List[str] = field(default_factory=list)
    sources_b: List[str] = field(default_factory=list)
    status: str = "open"
    resolution: Optional[str] = None
    resolved_by: Optional[str] = None


@dataclass
class InvestigationExport:
    id: str
    question: str
    status: str = "open"
    claim_id: Optional[str] = None
    claim_ids: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    rationale: Optional[str] = None


@dataclass
class SourceExport:
    id: str
    source_type: str
    origin: str
    url: Optional[str] = None
    domain: Optional[str] = None
    author: Optional[str] = None
    fetched_at: float = 0.0
    checksum: str = ""
    parser_version: str = "0.1.0"
    normalization_version: str = "0.1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ViewIndex:
    """Pre-computed view data."""
    narrative: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    claims: List[Dict[str, Any]] = field(default_factory=list)
    chronology: List[Dict[str, Any]] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    provenance: List[Dict[str, Any]] = field(default_factory=list)
    investigations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class IntermediateIndex:
    """Pre-computed intermediate artifacts."""
    knowledge_graph: Dict[str, Any] = field(default_factory=dict)
    narrative_document: str = ""
    established_facts: List[Dict[str, Any]] = field(default_factory=list)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    contradiction_report: str = ""
    source_inventory: List[Dict[str, Any]] = field(default_factory=list)
    character_dossiers: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class ArtifactIR:
    """Two-phase artifact compiler output."""
    version: str = "0.1.0"
    compiled_at: float = 0.0
    compiler_version: str = "0.1.0"
    policy_version: str = "0.1.0"
    corpus_fingerprint: str = ""

    claims: List[ClaimExport] = field(default_factory=list)
    evidence_index: List[EvidenceExport] = field(default_factory=list)
    entity_index: List[EntityExport] = field(default_factory=list)
    contradictions: List[ContradictionExport] = field(default_factory=list)
    investigations: List[InvestigationExport] = field(default_factory=list)
    provenance_index: List[SourceExport] = field(default_factory=list)

    views: ViewIndex = field(default_factory=ViewIndex)
    intermediates: IntermediateIndex = field(default_factory=IntermediateIndex)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


def compute_corpus_fingerprint(claims: List[ClaimExport], evidence: List[EvidenceExport]) -> str:
    """Compute a deterministic fingerprint over corpus state.

    The fingerprint covers ONLY deterministic identity fields (IDs, normalized
    text, quotes) — never model-derived annotations or timestamps — and is
    order-independent: inputs are sorted by ID before hashing, so physical
    row order in the database (which UPDATEs can change) cannot alter it.
    """
    canonical = {
        "claims": sorted((c.id, _claim_hash_proxy(c)) for c in claims),
        "evidence": sorted((e.id, _evidence_hash_proxy(e)) for e in evidence),
    }
    payload = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


# Helper methods for fingerprinting
def _claim_hash_proxy(claim: ClaimExport) -> str:
    """Hash of claim identity fields."""
    return hashlib.sha256(f"{claim.id}:{claim.normalized}".encode()).hexdigest()


def _evidence_hash_proxy(evidence: EvidenceExport) -> str:
    """Hash of evidence identity fields."""
    return hashlib.sha256(f"{evidence.id}:{evidence.source_id}:{evidence.quote}".encode()).hexdigest()
