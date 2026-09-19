"""Artifact compiler — transforms Epistemic Graph into Artifact IR.

Phase 1: Query the Epistemic Graph and build the Artifact IR.
Phase 2: Compile the Artifact IR into simpler intermediates.
Phase 3 (scale): Write a sharded static artifact — a small index
(`artifact.json`) plus prefix-sharded data files under `data/` — so a
corpus of 10⁴-10⁵ claims remains loadable in a browser.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .artifact_ir import (
    ArtifactIR,
    ClaimExport,
    ContradictionExport,
    EvidenceExport,
    EntityExport,
    IntermediateIndex,
    InvestigationExport,
    SourceExport,
    ViewIndex,
    _claim_hash_proxy,
    _evidence_hash_proxy,
    compute_corpus_fingerprint,
)


class ArtifactCompiler:
    """Compiles the Epistemic Graph into an Artifact IR."""

    def __init__(
        self,
        claims: Optional[List[Dict[str, Any]]] = None,
        evidence: Optional[List[Dict[str, Any]]] = None,
        entities: Optional[List[Dict[str, Any]]] = None,
        contradictions: Optional[List[Dict[str, Any]]] = None,
        investigations: Optional[List[Dict[str, Any]]] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
    ):
        self.claims = claims or []
        self.evidence = evidence or []
        self.entities = entities or []
        self.contradictions = contradictions or []
        self.investigations = investigations or []
        self.sources = sources or []

    def compile(self) -> ArtifactIR:
        """Compile the full Artifact IR."""
        start = time.time()

        # Build export objects
        claim_exports = [self._build_claim(c) for c in self.claims]
        evidence_exports = [self._build_evidence(e) for e in self.evidence]
        entity_exports = [self._build_entity(e) for e in self.entities]
        contradiction_exports = [self._build_contradiction(c) for c in self.contradictions]
        investigation_exports = [self._build_investigation(i) for i in self.investigations]
        source_exports = [self._build_source(s) for s in self.sources]

        # Build view index
        views = self._build_views(
            claim_exports, evidence_exports, entity_exports,
            contradiction_exports, investigation_exports, source_exports,
        )

        # Build intermediate index
        intermediates = self._build_intermediates(
            claim_exports, evidence_exports, entity_exports,
            contradiction_exports, investigation_exports, source_exports,
        )

        # Compute fingerprint
        fingerprint = compute_corpus_fingerprint(claim_exports, evidence_exports)

        return ArtifactIR(
            version="0.1.0",
            compiled_at=time.time(),
            compiler_version="0.1.0",
            policy_version="0.1.0",
            corpus_fingerprint=fingerprint,
            claims=claim_exports,
            evidence_index=evidence_exports,
            entity_index=entity_exports,
            contradictions=contradiction_exports,
            investigations=investigation_exports,
            provenance_index=source_exports,
            views=views,
            intermediates=intermediates,
        )

    def _build_claim(self, claim: Dict[str, Any]) -> ClaimExport:
        return ClaimExport(
            id=claim["id"],
            text=claim["text"],
            normalized=claim.get("normalized", ""),
            status=claim.get("status", "UNEXAMINED"),
            confidence=claim.get("confidence", 0.0),
            confidence_terms=claim.get("confidence_terms", {}),
            evidence_ids=claim.get("evidence_ids", []),
            source_ids=claim.get("source_ids", []),
            entity_ids=claim.get("entity_ids", []),
            contradiction_ids=claim.get("contradiction_ids", []),
            derived_from=claim.get("derived_from", []),
            history=claim.get("history", []),
            compiler_version=claim.get("compiler_version", "0.1.0"),
            policy_version=claim.get("policy_version", "0.1.0"),
        )

    def _build_evidence(self, evidence: Dict[str, Any]) -> EvidenceExport:
        return EvidenceExport(
            id=evidence["id"],
            source_id=evidence["source_id"],
            structural_unit_id=evidence.get("structural_unit_id"),
            claim_id=evidence.get("claim_id"),
            domain=evidence.get("domain"),
            author=evidence.get("author"),
            stance=evidence.get("stance", "support"),
            quote=evidence.get("quote", ""),
            offset=evidence.get("offset", 0),
            timestamp=evidence.get("timestamp"),
            reliability=evidence.get("reliability"),
            source_checksum=evidence.get("source_checksum", ""),
            parser_version=evidence.get("parser_version", "0.1.0"),
        )

    def _build_entity(self, entity: Dict[str, Any]) -> EntityExport:
        return EntityExport(
            id=entity["id"],
            name=entity.get("name", ""),
            normalized=entity.get("normalized", ""),
            mentions=entity.get("mentions", 0),
            entity_type=entity.get("entity_type", "unknown"),
            source_ids=entity.get("source_ids", []),
        )

    def _build_contradiction(self, contradiction: Dict[str, Any]) -> ContradictionExport:
        return ContradictionExport(
            id=contradiction["id"],
            claim_a_id=contradiction["claim_a_id"],
            claim_b_id=contradiction["claim_b_id"],
            text_a=contradiction.get("text_a", ""),
            text_b=contradiction.get("text_b", ""),
            overlap=contradiction.get("overlap", 0.0),
            entity_id=contradiction.get("entity_id"),
            sources_a=contradiction.get("sources_a", []),
            sources_b=contradiction.get("sources_b", []),
            status=contradiction.get("status", "open"),
            resolution=contradiction.get("resolution"),
            resolved_by=contradiction.get("resolved_by"),
        )

    def _build_investigation(self, investigation: Dict[str, Any]) -> InvestigationExport:
        return InvestigationExport(
            id=investigation["id"],
            question=investigation.get("question", ""),
            status=investigation.get("status", "open"),
            claim_id=investigation.get("claim_id"),
            claim_ids=investigation.get("claim_ids", []),
            evidence_ids=investigation.get("evidence_ids", []),
            rationale=investigation.get("rationale"),
        )

    def _build_source(self, source: Dict[str, Any]) -> SourceExport:
        return SourceExport(
            id=source["id"],
            source_type=source.get("type", "document"),
            origin=source.get("origin", ""),
            url=source.get("url"),
            domain=source.get("domain"),
            author=source.get("author"),
            fetched_at=source.get("fetched_at", 0.0),
            checksum=source.get("checksum", ""),
            parser_version=source.get("parser_version", "0.1.0"),
            normalization_version=source.get("normalization_version", "0.1.0"),
            metadata=source.get("metadata", {}),
        )

    def _build_views(
        self,
        claims: List[ClaimExport],
        evidence: List[EvidenceExport],
        entities: List[EntityExport],
        contradictions: List[ContradictionExport],
        investigations: List[InvestigationExport],
        sources: List[SourceExport],
    ) -> ViewIndex:
        """Pre-compute view data."""
        # Narrative: SUPPORTED/VALIDATED claims ordered by confidence
        narrative_claims = [
            c for c in claims if c.status in ("SUPPORTED", "VALIDATED")
        ]
        narrative_claims.sort(key=lambda c: c.confidence, reverse=True)
        narrative = [
            {
                "claim_id": c.id,
                "text": c.text,
                "confidence": c.confidence,
                "evidence_ids": c.evidence_ids,
            }
            for c in narrative_claims
        ]

        # Evidence: grouped by source
        evidence_by_source: Dict[str, List[Dict]] = {}
        for e in evidence:
            sid = e.source_id
            if sid not in evidence_by_source:
                evidence_by_source[sid] = []
            evidence_by_source[sid].append({
                "evidence_id": e.id,
                "quote": e.quote,
                "stance": e.stance,
                "claim_id": e.claim_id,
                "offset": e.offset,
            })
        evidence_view = [
            {"source_id": sid, "units": units}
            for sid, units in evidence_by_source.items()
        ]

        # Claims: all claims with status
        claims_view = [
            {
                "claim_id": c.id,
                "text": c.text,
                "status": c.status,
                "confidence": c.confidence,
                "evidence_count": len(c.evidence_ids),
                "entity_ids": c.entity_ids,
            }
            for c in claims
        ]

        # Chronology: claims with timestamps (from evidence)
        # Use evidence timestamps as proxy for claim timestamps
        claim_timestamps: Dict[str, float] = {}
        for e in evidence:
            if e.timestamp and e.claim_id:
                if e.claim_id not in claim_timestamps:
                    claim_timestamps[e.claim_id] = e.timestamp
        chronology = [
            {
                "claim_id": c.id,
                "text": c.text,
                "timestamp": claim_timestamps.get(c.id),
                "status": c.status,
            }
            for c in claims
            if c.id in claim_timestamps
        ]
        chronology.sort(key=lambda x: x["timestamp"] or 0)

        # Contradictions
        contradictions_view = [
            {
                "contradiction_id": c.id,
                "claim_a_id": c.claim_a_id,
                "claim_b_id": c.claim_b_id,
                "text_a": c.text_a,
                "text_b": c.text_b,
                "overlap": c.overlap,
                "status": c.status,
            }
            for c in contradictions
        ]

        # Provenance: source-to-claim graph
        source_claims: Dict[str, List[str]] = {}
        for c in claims:
            for sid in c.source_ids:
                if sid not in source_claims:
                    source_claims[sid] = []
                source_claims[sid].append(c.id)
        provenance = [
            {
                "source_id": sid,
                "claim_ids": cids,
                "source_type": next((s.source_type for s in sources if s.id == sid), "unknown"),
            }
            for sid, cids in source_claims.items()
        ]

        # Investigations
        investigations_view = [
            {
                "investigation_id": i.id,
                "question": i.question,
                "status": i.status,
                "claim_ids": i.claim_ids,
            }
            for i in investigations
        ]

        return ViewIndex(
            narrative=narrative,
            evidence=evidence_view,
            claims=claims_view,
            chronology=chronology,
            contradictions=contradictions_view,
            provenance=provenance,
            investigations=investigations_view,
        )

    def _build_intermediates(
        self,
        claims: List[ClaimExport],
        evidence: List[EvidenceExport],
        entities: List[EntityExport],
        contradictions: List[ContradictionExport],
        investigations: List[InvestigationExport],
        sources: List[SourceExport],
    ) -> IntermediateIndex:
        """Pre-compute intermediate artifacts."""
        # Knowledge graph: entity co-occurrence + claim relationships
        knowledge_graph = self._build_knowledge_graph(claims, entities)

        # Narrative document: prose synthesis
        narrative_doc = self._build_narrative_document(claims, evidence)

        # Established facts: high-confidence claims
        established_facts = [
            {
                "claim_id": c.id,
                "text": c.text,
                "confidence": c.confidence,
                "evidence_ids": c.evidence_ids,
            }
            for c in claims
            if c.status in ("SUPPORTED", "VALIDATED") and c.confidence >= 0.4
        ]
        established_facts.sort(key=lambda x: x["confidence"], reverse=True)

        # Timeline: chronological event sequence
        timeline = self._build_timeline(claims, evidence)

        # Contradiction report
        contradiction_report = self._build_contradiction_report(contradictions, claims)

        # Source inventory
        source_inventory = [
            {
                "source_id": s.id,
                "type": s.source_type,
                "origin": s.origin,
                "domain": s.domain,
                "author": s.author,
                "fetched_at": s.fetched_at,
                "parser_version": s.parser_version,
            }
            for s in sources
        ]

        # Character dossiers: per-entity summaries
        character_dossiers = self._build_character_dossiers(claims, evidence, entities)

        return IntermediateIndex(
            knowledge_graph=knowledge_graph,
            narrative_document=narrative_doc,
            established_facts=established_facts,
            timeline=timeline,
            contradiction_report=contradiction_report,
            source_inventory=source_inventory,
            character_dossiers=character_dossiers,
        )

    def _build_knowledge_graph(
        self, claims: List[ClaimExport], entities: List[EntityExport]
    ) -> Dict[str, Any]:
        """Build a d3.js-compatible knowledge graph."""
        nodes = []
        links = []

        # Entity nodes
        entity_map: Dict[str, EntityExport] = {}
        for e in entities:
            nodes.append({
                "id": e.id,
                "name": e.name,
                "type": "entity",
                "mentions": e.mentions,
            })
            entity_map[e.id] = e

        # Claim nodes
        for c in claims:
            nodes.append({
                "id": c.id,
                "text": c.text[:80],
                "type": "claim",
                "status": c.status,
                "confidence": c.confidence,
            })

        # Links: claim → entity
        for c in claims:
            for eid in c.entity_ids:
                if eid in entity_map:
                    links.append({
                        "source": c.id,
                        "target": eid,
                        "type": "mentions",
                    })

        # Links: claim → claim (derived_from)
        for c in claims:
            for derived in c.derived_from:
                links.append({
                    "source": c.id,
                    "target": derived,
                    "type": "derived_from",
                })

        return {"nodes": nodes, "links": links}

    def _build_narrative_document(
        self, claims: List[ClaimExport], evidence: List[EvidenceExport]
    ) -> str:
        """Build a Markdown narrative document."""
        lines = ["# Narrative", ""]

        # Group claims by status
        supported = [c for c in claims if c.status in ("SUPPORTED", "VALIDATED")]
        supported.sort(key=lambda c: c.confidence, reverse=True)

        if supported:
            lines.append("## Established Facts")
            lines.append("")
            for c in supported:
                lines.append(f"- {c.text} (confidence: {c.confidence:.2f})")
            lines.append("")

        contested = [c for c in claims if c.status == "CONTESTED"]
        if contested:
            lines.append("## Contested Claims")
            lines.append("")
            for c in contested:
                lines.append(f"- {c.text}")
            lines.append("")

        insufficient = [c for c in claims if c.status == "INSUFFICIENT"]
        if insufficient:
            lines.append("## Insufficient Evidence")
            lines.append("")
            for c in insufficient:
                lines.append(f"- {c.text}")
            lines.append("")

        return "\n".join(lines)

    def _build_timeline(
        self, claims: List[ClaimExport], evidence: List[EvidenceExport]
    ) -> List[Dict[str, Any]]:
        """Build a chronological event sequence."""
        # Map evidence timestamps to claims
        claim_timestamps: Dict[str, float] = {}
        for e in evidence:
            if e.timestamp and e.claim_id:
                if e.claim_id not in claim_timestamps or e.timestamp < claim_timestamps[e.claim_id]:
                    claim_timestamps[e.claim_id] = e.timestamp

        timeline = []
        for c in claims:
            if c.id in claim_timestamps:
                timeline.append({
                    "claim_id": c.id,
                    "text": c.text,
                    "timestamp": claim_timestamps[c.id],
                    "status": c.status,
                })

        timeline.sort(key=lambda x: x["timestamp"])
        return timeline

    def _build_contradiction_report(
        self, contradictions: List[ContradictionExport], claims: List[ClaimExport]
    ) -> str:
        """Build a Markdown contradiction report."""
        lines = ["# Contradiction Report", ""]

        if not contradictions:
            lines.append("No contradictions detected.")
            return "\n".join(lines)

        claim_map = {c.id: c for c in claims}

        for con in contradictions:
            lines.append(f"## Contradiction {con.id[:12]}")
            lines.append("")
            lines.append(f"- **Claim A**: {con.text_a}")
            lines.append(f"- **Claim B**: {con.text_b}")
            lines.append(f"- **Overlap**: {con.overlap:.2f}")
            lines.append(f"- **Status**: {con.status}")
            if con.resolution:
                lines.append(f"- **Resolution**: {con.resolution}")
            lines.append("")

        return "\n".join(lines)

    def _build_character_dossiers(
        self,
        claims: List[ClaimExport],
        evidence: List[EvidenceExport],
        entities: List[EntityExport],
    ) -> Dict[str, Dict[str, Any]]:
        """Build per-entity character dossiers."""
        dossiers: Dict[str, Dict[str, Any]] = {}

        # Map claims to entities
        entity_claims: Dict[str, List[ClaimExport]] = {}
        for c in claims:
            for eid in c.entity_ids:
                if eid not in entity_claims:
                    entity_claims[eid] = []
                entity_claims[eid].append(c)

        # Map evidence to entities (via claims)
        entity_evidence: Dict[str, List[EvidenceExport]] = {}
        for c in claims:
            for eid in c.entity_ids:
                if eid not in entity_evidence:
                    entity_evidence[eid] = []
                for eid2 in c.evidence_ids:
                    ev = next((e for e in evidence if e.id == eid2), None)
                    if ev:
                        entity_evidence[eid].append(ev)

        for e in entities:
            claims_for_entity = entity_claims.get(e.id, [])
            evidence_for_entity = entity_evidence.get(e.id, [])

            dossiers[e.id] = {
                "name": e.name,
                "entity_type": e.entity_type,
                "mentions": e.mentions,
                "claims": [
                    {
                        "claim_id": c.id,
                        "text": c.text,
                        "status": c.status,
                        "confidence": c.confidence,
                    }
                    for c in claims_for_entity
                ],
                "evidence": [
                    {
                        "evidence_id": ev.id,
                        "quote": ev.quote,
                        "stance": ev.stance,
                        "source_id": ev.source_id,
                    }
                    for ev in evidence_for_entity
                ],
            }

        return dossiers

    # ------------------------------------------------------------------
    # Phase 3: sharded static artifact
    # ------------------------------------------------------------------

    def write_sharded_artifact(self, output_dir: Path, *, shard_size: int = 2000) -> Dict[str, Any]:
        """Write a scale-safe static artifact.

        Layout:
          artifact.json          — small index: version, fingerprint, counts,
                                   shard manifest, capped view summaries
          data/claims-<n>.json   — full claim records, shard n
          data/evidence-<n>.json — full evidence records, shard n
          data/entities.json     — entity index (capped to top by mentions)
          data/contradictions.json
          data/sources-<n>.json  — source inventory
          data/timeline.json     — full chronology
          data/narrative.md      — narrative document

        Returns a summary dict with counts and file sizes.
        """
        output_dir = Path(output_dir)
        data_dir = output_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        claim_exports = [self._build_claim(c) for c in self.claims]
        evidence_exports = [self._build_evidence(e) for e in self.evidence]
        entity_exports = [self._build_entity(e) for e in self.entities]
        contradiction_exports = [self._build_contradiction(c) for c in self.contradictions]
        investigation_exports = [self._build_investigation(i) for i in self.investigations]
        source_exports = [self._build_source(s) for s in self.sources]

        fingerprint = compute_corpus_fingerprint(claim_exports, evidence_exports)

        def shard(items: List[Any], name: str) -> List[str]:
            files = []
            for i in range(0, len(items), shard_size):
                chunk = items[i : i + shard_size]
                fname = f"{name}-{i // shard_size}.json"
                (data_dir / fname).write_text(
                    json.dumps(chunk, default=lambda o: o.__dict__, ensure_ascii=False),
                    encoding="utf-8",
                )
                files.append(f"data/{fname}")
            return files

        claim_shards = shard(claim_exports, "claims")
        evidence_shards = shard(evidence_exports, "evidence")
        source_shards = shard(source_exports, "sources")

        (data_dir / "entities.json").write_text(
            json.dumps(
                [e.__dict__ for e in entity_exports], default=str, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        (data_dir / "contradictions.json").write_text(
            json.dumps(
                [c.__dict__ for c in contradiction_exports], default=str, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        (data_dir / "timeline.json").write_text(
            json.dumps(self._build_timeline(claim_exports, evidence_exports), default=str, ensure_ascii=False),
            encoding="utf-8",
        )
        narrative_doc = self._build_narrative_document(claim_exports, evidence_exports)
        (data_dir / "narrative.md").write_text(narrative_doc, encoding="utf-8")

        # Capped view summaries for the index (full data lives in shards)
        NARRATIVE_CAP = 500
        narrative_summary = [
            {
                "claim_id": c.id,
                "text": c.text,
                "status": c.status,
                "confidence": c.confidence,
                "evidence_count": len(c.evidence_ids),
            }
            for c in sorted(
                (c for c in claim_exports if c.status in ("SUPPORTED", "VALIDATED")),
                key=lambda c: c.confidence,
                reverse=True,
            )[:NARRATIVE_CAP]
        ]

        status_counts: Dict[str, int] = {}
        for c in claim_exports:
            status_counts[c.status] = status_counts.get(c.status, 0) + 1

        index = {
            "version": "0.2.0",
            "compiled_at": time.time(),
            "compiler_version": "0.2.0",
            "policy_version": "0.1.0",
            "corpus_fingerprint": fingerprint,
            "counts": {
                "claims": len(claim_exports),
                "evidence": len(evidence_exports),
                "entities": len(entity_exports),
                "contradictions": len(contradiction_exports),
                "investigations": len(investigation_exports),
                "sources": len(source_exports),
            },
            "status_counts": status_counts,
            "shards": {
                "claims": claim_shards,
                "evidence": evidence_shards,
                "sources": source_shards,
                "entities": ["data/entities.json"],
                "contradictions": ["data/contradictions.json"],
                "timeline": ["data/timeline.json"],
                "narrative": ["data/narrative.md"],
            },
            "views": {
                "narrative": narrative_summary,
            },
            "intermediates": {
                "contradiction_report": self._build_contradiction_report(
                    contradiction_exports, claim_exports
                ),
            },
        }
        (output_dir / "artifact.json").write_text(
            json.dumps(index, default=str, ensure_ascii=False),
            encoding="utf-8",
        )

        return {
            "counts": index["counts"],
            "status_counts": status_counts,
            "claim_shards": len(claim_shards),
            "evidence_shards": len(evidence_shards),
            "fingerprint": fingerprint,
        }
