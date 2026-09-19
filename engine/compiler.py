"""Ingestion compiler — 6-stage pipeline from sources to claim graph.

Stages:
1. Acquisition    → read source files
2. Canonicalization → common envelope
3. Structural parsing → format-specific decomposition
4. Evidence unit creation → smallest provenance-bearing objects
5. Semantic extraction → deterministic (optional model refinement)
6. Claim graph construction → merge, score, assign lifecycle
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import canonicalize as canon
from . import lifecycle
from .confidence import EvidenceRef, score_claim
from .contradictions import mine_contradictions
from .extract import extract_source
from .store_evidence import EvidenceGraphStore
from .store_epistemic import EpistemicGraphStore


COMPILER_VERSION = "0.1.0"
POLICY_VERSION = "0.1.0"


@dataclass
class CompileReport:
    cycle: int = 0
    mode: str = "full"
    seconds: float = 0.0
    sources_seen: int = 0
    sources_extracted: int = 0
    sources_cached: int = 0
    structural_units: int = 0
    evidence_units: int = 0
    claims_proposed: int = 0
    claims_new: int = 0
    claims_updated: int = 0
    contradictions_detected: int = 0
    ledger_events: int = 0
    errors: List[str] = field(default_factory=list)

    def __str__(self):
        lines = [
            f"compile #{self.cycle} ({self.mode}) in {self.seconds:.2f}s",
            f" sources_seen={self.sources_seen} extracted={self.sources_extracted} cached={self.sources_cached}",
            f" structural_units={self.structural_units}",
            f" evidence_units={self.evidence_units}",
            f" claims_proposed={self.claims_proposed} new={self.claims_new} updated={self.claims_updated}",
            f" contradictions_detected={self.contradictions_detected}",
            f" ledger_events={self.ledger_events}",
        ]
        if self.errors:
            lines.append(f" errors={len(self.errors)}")
            for e in self.errors[:5]:
                lines.append(f"  - {e}")
        return "\n".join(lines)


class Compiler:
    def __init__(
        self,
        *,
        evidence_store: EvidenceGraphStore = None,
        epistemic_store: EpistemicGraphStore = None,
    ):
        self.evidence_store = evidence_store or EvidenceGraphStore()
        self.epistemic_store = epistemic_store or EpistemicGraphStore()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def compile_sources(self, sources: List[Dict], cycle: int = 0) -> CompileReport:
        """Compile a list of source records through the full pipeline."""
        import asyncio
        report = CompileReport(cycle=cycle, mode="full")
        start = time.time()

        report.sources_seen = len(sources)

        all_extractions = []
        for source in sources:
            try:
                new_id = await self.evidence_store.put_source(source)
                if new_id is None:
                    # Source was cached — still process structural units + evidence
                    pass
                else:
                    report.sources_extracted += 1

                # Stage 3: Structural parsing
                units = canon.structural_parse(source)
                for u in units:
                    await self.evidence_store.put_structural_unit(u)
                    report.structural_units += 1

                # Stage 4 + 5: Evidence unit creation + Semantic extraction
                extraction = extract_source(
                    source,
                    structural_units=units,
                    parser_version=source["parser_version"],
                )
                all_extractions.append(extraction)

            except Exception as e:
                report.errors.append(f"source {source.get('id', '?')}: {e}")

        # Stage 6: Claim graph construction
        if all_extractions:
            await self._build_claim_graph(all_extractions, report)

        # Stage 6b: Persist evidence units (after claims exist for FK integrity)
        if all_extractions:
            for extraction in all_extractions:
                for ev in extraction.evidence:
                    ev_record = {
                        **ev,
                        "claim_id": None,  # FK to claims — linked via claim.evidence_ids
                        "source_id": extraction.source_id,
                        "parser_version": "1.0.0",
                        "source_checksum": extraction.source_checksum,
                    }
                    await self.evidence_store.put_evidence_unit(ev_record)
                    report.evidence_units += 1

        report.seconds = time.time() - start
        return report

    async def compile_corpus_dir(self, corpus_dir: str, cycle: int = 0) -> CompileReport:
        """Compile all source files in a directory."""
        import asyncio
        sources = self._acquire_corpus(corpus_dir)
        report = await self.compile_sources(sources, cycle=cycle)
        report.mode = "full"
        return report

    async def incremental_compile(self, corpus_dir: str, cycle: int,
                                   previous_sources: List[Dict]) -> CompileReport:
        """Compile only sources that changed since the last cycle."""
        import asyncio
        current_sources = self._acquire_corpus(corpus_dir)
        current_checksums = {s["checksum"]: s for s in current_sources}
        previous_checksums = {s["checksum"]: s for s in previous_sources}

        changed = []
        for checksum, source in current_checksums.items():
            if checksum not in previous_checksums:
                changed.append(source)

        # Handle removed sources
        removed_checksums = set(previous_checksums.keys()) - set(current_checksums.keys())
        for checksum in removed_checksums:
            source = previous_checksums[checksum]
            await self.evidence_store.mark_source_removed(source["id"])

        report = await self.compile_sources(changed, cycle=cycle)
        report.mode = "incremental"
        return report

    # ------------------------------------------------------------------
    # Stage 1: Acquisition (file system)
    # ------------------------------------------------------------------

    def _acquire_corpus(self, corpus_dir: str) -> List[Dict]:
        """Read all source files from a directory."""
        sources = []
        corpus_path = Path(corpus_dir)
        if not corpus_path.exists():
            return sources

        for file_path in corpus_path.iterdir():
            if file_path.is_file() and not file_path.name.startswith("."):
                try:
                    source = canon.read_source_file(file_path)
                    if source:
                        sources.append(source)
                except Exception as e:
                    # Visible failure — never silently skip
                    print(f"WARNING: failed to read {file_path}: {e}")
        return sources

    # ------------------------------------------------------------------
    # Stage 6: Claim graph construction
    # ------------------------------------------------------------------

    async def _build_claim_graph(self, extractions: List, report: CompileReport):
        """Merge extractions, detect contradictions, score, and store claims."""
        import asyncio

        # Merge all extractions
        merged = self._merge_extractions(extractions)

        # Detect contradictions
        contradictions = mine_contradictions(merged["claims"])
        report.contradictions_detected = len(contradictions)

        # Score and store claims
        for claim in merged["claims"]:
            claim_id = claim["id"]

            # Gather evidence refs for this claim
            evidence_refs = [
                EvidenceRef(
                    evidence_id=ev["id"],
                    source_id=ev["source_id"],
                    domain=ev.get("domain", ""),
                    author=ev.get("author", ""),
                    stance=ev.get("stance", "support"),
                    reliability=ev.get("reliability"),
                    timestamp=ev.get("timestamp"),
                    quote=ev.get("quote", ""),
                )
                for ev in merged["evidence"]
                if ev.get("claim_id") == claim_id
            ]

            # Score the claim
            score_result = score_claim(evidence_refs)

            # Determine lifecycle status
            status = lifecycle.initial_status(
                evidence_refs=evidence_refs,
                confidence=score_result.score,
                has_contradictions=claim_id in [c["claim_a_id"] for c in contradictions] + [c["claim_b_id"] for c in contradictions],
            )

            # Store the claim
            claim_record = {
                "id": claim_id,
                "text": claim["text"],
                "normalized": canon.normalize_text(claim["text"]),
                "status": status.value,
                "confidence": score_result.score,
                "confidence_terms": score_result.terms,
                "evidence_ids": [er.evidence_id for er in evidence_refs],
                "source_ids": claim.get("source_ids", []),
                "entity_ids": claim.get("entity_ids", []),
                "contradiction_ids": [
                    c["id"] for c in contradictions
                    if c["claim_a_id"] == claim_id or c["claim_b_id"] == claim_id
                ],
                "derived_from": claim.get("derived_from", []),
                "compiler_version": COMPILER_VERSION,
                "policy_version": POLICY_VERSION,
                "status_reason": "initial extraction",
            }

            result = await self.epistemic_store.put_claim(claim_record)
            if result:
                # Check if new or updated
                existing = await self.epistemic_store.get_claim(claim_id)
                if existing and existing.get("history"):
                    report.claims_updated += 1
                else:
                    report.claims_new += 1
                report.claims_proposed += 1

        # Store contradictions
        for con in contradictions:
            await self.evidence_store.put_contradiction(con)

        # Record ledger events
        await self._record_compile_events(report, len(merged["claims"]), len(contradictions))

    def _merge_extractions(self, extractions: List) -> Dict:
        """Merge per-source extractions into a single set."""
        all_claims = {}
        all_evidence = {}
        all_entities = {}
        all_relationships = {}

        for ext in extractions:
            for claim in ext.claims:
                cid = claim["id"]
                if cid in all_claims:
                    all_claims[cid]["source_ids"] = list(
                        set(all_claims[cid]["source_ids"]) | set(claim.get("source_ids", []))
                    )
                else:
                    all_claims[cid] = {**claim}

            for ev in ext.evidence:
                all_evidence[ev["id"]] = {**ev}

            for ent in ext.entities:
                eid = ent["id"]
                if eid in all_entities:
                    all_entities[eid]["mentions"] += ent.get("mentions", 0)
                else:
                    all_entities[eid] = {**ent}

            for rel in ext.relationships:
                rid = rel["id"]
                if rid in all_relationships:
                    all_relationships[rid]["co_count"] += rel.get("co_count", 1)
                else:
                    all_relationships[rid] = {**rel}

        return {
            "claims": list(all_claims.values()),
            "evidence": list(all_evidence.values()),
            "entities": list(all_entities.values()),
            "relationships": list(all_relationships.values()),
        }

    async def _record_compile_events(self, report: CompileReport, num_claims: int, num_contradictions: int):
        """Record compile completion in the ledger."""
        event = {
            "id": f"evt-{hashlib.sha256(f'compile-{report.cycle}-{time.time()}'.encode()).hexdigest()[:32]}",
            "event_type": "COMPILE_COMPLETED",
            "actor": "system:compiler",
            "operation": "compile",
            "inputs": {"cycle": report.cycle, "mode": report.mode},
            "outputs": {
                "sources_seen": report.sources_seen,
                "sources_extracted": report.sources_extracted,
                "claims_proposed": num_claims,
                "contradictions_detected": num_contradictions,
            },
            "input_hashes": [],
            "output_hashes": [],
            "model": None,
            "policy_version": POLICY_VERSION,
            "parent_event_id": None,
            "metadata": {"compiler_version": COMPILER_VERSION},
        }
        await self.epistemic_store.put_ledger_event(event)
        report.ledger_events += 1
