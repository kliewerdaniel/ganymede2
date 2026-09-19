"""Tests for the artifact compiler."""

import pytest
from engine.artifact_compiler import ArtifactCompiler


class TestArtifactCompiler:
    def _make_claims(self):
        return [
            {
                "id": "clm-1",
                "text": "Chris was a software engineer.",
                "normalized": "chris was a software engineer",
                "status": "SUPPORTED",
                "confidence": 0.8,
                "evidence_ids": ["ev-1"],
                "source_ids": ["src-1"],
                "entity_ids": ["ent-chris"],
                "contradiction_ids": [],
            },
            {
                "id": "clm-2",
                "text": "Chris was a musician.",
                "normalized": "chris was a musician",
                "status": "VALIDATED",
                "confidence": 0.9,
                "evidence_ids": ["ev-2"],
                "source_ids": ["src-1"],
                "entity_ids": ["ent-chris"],
                "contradiction_ids": [],
            },
            {
                "id": "clm-3",
                "text": "Chris was born in Seattle.",
                "normalized": "chris was born in seattle",
                "status": "CONTESTED",
                "confidence": 0.3,
                "evidence_ids": [],
                "source_ids": [],
                "entity_ids": ["ent-chris"],
                "contradiction_ids": ["con-1"],
            },
        ]

    def _make_evidence(self):
        return [
            {
                "id": "ev-1",
                "source_id": "src-1",
                "claim_id": "clm-1",
                "quote": "He worked as a software engineer.",
                "stance": "support",
                "offset": 0,
                "source_checksum": "abc",
                "parser_version": "0.1.0",
            },
            {
                "id": "ev-2",
                "source_id": "src-1",
                "claim_id": "clm-2",
                "quote": "He played guitar and wrote songs.",
                "stance": "support",
                "offset": 0,
                "source_checksum": "abc",
                "parser_version": "0.1.0",
            },
        ]

    def _make_entities(self):
        return [
            {"id": "ent-chris", "name": "Chris", "normalized": "chris", "mentions": 5},
        ]

    def _make_contradictions(self):
        return [
            {
                "id": "con-1",
                "claim_a_id": "clm-1",
                "claim_b_id": "clm-3",
                "text_a": "Chris was a software engineer.",
                "text_b": "Chris was born in Seattle.",
                "overlap": 0.3,
                "status": "open",
            },
        ]

    def test_compile_creates_ir(self):
        compiler = ArtifactCompiler(
            claims=self._make_claims(),
            evidence=self._make_evidence(),
            entities=self._make_entities(),
            contradictions=self._make_contradictions(),
        )
        ir = compiler.compile()
        assert ir.version == "0.1.0"
        assert len(ir.claims) == 3
        assert len(ir.evidence_index) == 2
        assert len(ir.entity_index) == 1
        assert len(ir.contradictions) == 1

    def test_narrative_view_filters_by_status(self):
        compiler = ArtifactCompiler(
            claims=self._make_claims(),
            evidence=self._make_evidence(),
            entities=self._make_entities(),
        )
        ir = compiler.compile()
        narrative = ir.views.narrative
        assert len(narrative) == 2
        # Should be ordered by confidence (descending)
        assert narrative[0]["claim_id"] == "clm-2"
        assert narrative[1]["claim_id"] == "clm-1"

    def test_evidence_view_grouped_by_source(self):
        compiler = ArtifactCompiler(
            claims=self._make_claims(),
            evidence=self._make_evidence(),
            entities=self._make_entities(),
        )
        ir = compiler.compile()
        evidence = ir.views.evidence
        assert len(evidence) == 1  # One source
        assert evidence[0]["source_id"] == "src-1"
        assert len(evidence[0]["units"]) == 2

    def test_chronology_requires_timestamps(self):
        compiler = ArtifactCompiler(
            claims=self._make_claims(),
            evidence=self._make_evidence(),  # No timestamps
            entities=self._make_entities(),
        )
        ir = compiler.compile()
        assert len(ir.views.chronology) == 0

    def test_knowledge_graph_has_nodes_and_links(self):
        compiler = ArtifactCompiler(
            claims=self._make_claims(),
            evidence=self._make_evidence(),
            entities=self._make_entities(),
        )
        ir = compiler.compile()
        kg = ir.intermediates.knowledge_graph
        assert len(kg["nodes"]) > 0
        # Entity nodes + claim nodes
        assert len(kg["nodes"]) == 4  # 1 entity + 3 claims

    def test_narrative_document_markdown(self):
        compiler = ArtifactCompiler(
            claims=self._make_claims(),
            evidence=self._make_evidence(),
            entities=self._make_entities(),
        )
        ir = compiler.compile()
        doc = ir.intermediates.narrative_document
        assert "# Narrative" in doc
        assert "## Established Facts" in doc
        assert "## Contested Claims" in doc

    def test_established_facts_filtered(self):
        compiler = ArtifactCompiler(
            claims=self._make_claims(),
            evidence=self._make_evidence(),
            entities=self._make_entities(),
        )
        ir = compiler.compile()
        facts = ir.intermediates.established_facts
        # SUPPORTED with confidence >= 0.4 → clm-1 (0.8) and clm-2 (0.9)
        assert len(facts) >= 2

    def test_contradiction_report_generated(self):
        compiler = ArtifactCompiler(
            claims=self._make_claims(),
            contradictions=self._make_contradictions(),
        )
        ir = compiler.compile()
        report = ir.intermediates.contradiction_report
        assert "# Contradiction Report" in report
        assert "Claim A" in report

    def test_character_dossiers(self):
        compiler = ArtifactCompiler(
            claims=self._make_claims(),
            evidence=self._make_evidence(),
            entities=self._make_entities(),
        )
        ir = compiler.compile()
        dossiers = ir.intermediates.character_dossiers
        assert "ent-chris" in dossiers
        assert len(dossiers["ent-chris"]["claims"]) == 3

    def test_source_inventory(self):
        compiler = ArtifactCompiler(
            sources=[
                {"id": "src-1", "type": "document", "origin": "bio.txt"},
            ],
        )
        ir = compiler.compile()
        assert len(ir.intermediates.source_inventory) == 1
        assert ir.intermediates.source_inventory[0]["source_id"] == "src-1"

    def test_corpus_fingerprint_deterministic(self):
        compiler = ArtifactCompiler(
            claims=self._make_claims(),
            evidence=self._make_evidence(),
            entities=self._make_entities(),
        )
        ir1 = compiler.compile()
        ir2 = compiler.compile()
        assert ir1.corpus_fingerprint == ir2.corpus_fingerprint

    def test_corpus_fingerprint_changes_with_data(self):
        compiler1 = ArtifactCompiler(
            claims=self._make_claims(),
            evidence=self._make_evidence(),
        )
        ir1 = compiler1.compile()

        claims2 = self._make_claims() + [
            {
                "id": "clm-extra",
                "text": "Extra claim.",
                "normalized": "extra claim",
                "status": "SUPPORTED",
                "confidence": 0.5,
            }
        ]
        compiler2 = ArtifactCompiler(claims=claims2, evidence=self._make_evidence())
        ir2 = compiler2.compile()

        assert ir1.corpus_fingerprint != ir2.corpus_fingerprint

    def test_ir_json_serializable(self):
        compiler = ArtifactCompiler(
            claims=self._make_claims(),
            evidence=self._make_evidence(),
            entities=self._make_entities(),
        )
        ir = compiler.compile()
        json_str = ir.to_json()
        assert len(json_str) > 0
        # Should be valid JSON
        import json
        parsed = json.loads(json_str)
        assert parsed["version"] == "0.1.0"
        assert len(parsed["claims"]) == 3
