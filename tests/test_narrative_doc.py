"""Tests for the voice-aware narrative document.

The narrative document (narrative.md) must follow the same ordering
policy as the narrative view: personal voice first, other
human-grounded claims second, machine-derived claims last — instead
of raw confidence order, which lets assistant boilerplate outrank the
corpus subject's own life material.
"""

import re

from engine.artifact_compiler import ArtifactCompiler, narrative_key
from engine.artifact_ir import ClaimExport, EvidenceExport


def _claim(cid, text, conf, speakers, voice=None, status="SUPPORTED"):
    return {
        "id": cid,
        "text": text,
        "normalized": text.lower(),
        "status": status,
        "confidence": conf,
        "evidence_ids": [],
        "source_ids": [],
        "entity_ids": [],
        "contradiction_ids": [],
        "speakers": speakers,
        "voice_class": voice,
    }


def _evidence(eid, cid, speaker):
    return {
        "id": eid,
        "source_id": "src-1",
        "claim_id": cid,
        "speaker": speaker,
        "quote": "q",
        "offset": 0,
        "source_checksum": "c",
        "parser_version": "1",
    }


class TestVoiceAwareNarrativeDocument:
    def _compile(self, claims, evidence):
        comp = ArtifactCompiler(claims=claims, evidence=evidence)
        return comp.compile()

    def test_personal_tier_leads_document(self):
        # Machine claim with the HIGHEST confidence must not lead the doc.
        claims = [
            _claim("clm-machine", "We'll notify you when your image is ready.", 0.99, {"assistant": 2}, "technical"),
            _claim("clm-personal", "My name is Dariusz, from Poland.", 0.40, {"user": 1}, "personal"),
        ]
        evidence = [
            _evidence("ev-0", "clm-machine", "assistant"),
            _evidence("ev-1", "clm-personal", "user"),
        ]
        ir = self._compile(claims, evidence)
        doc = ir.intermediates.narrative_document

        personal_idx = doc.index("My name is Dariusz")
        machine_idx = doc.index("We'll notify you")
        assert personal_idx < machine_idx, (
            "personal-voice claim must appear before machine boilerplate"
        )

    def test_document_has_three_tiers(self):
        claims = [
            _claim("clm-machine", "Machine claim.", 0.9, {"assistant": 1}, "technical"),
            _claim("clm-personal", "Personal claim.", 0.5, {"user": 1}, "personal"),
            _claim("clm-human", "Human claim.", 0.5, {"user": 1}, "technical"),
        ]
        evidence = [
            _evidence("ev-0", "clm-machine", "assistant"),
            _evidence("ev-1", "clm-personal", "user"),
            _evidence("ev-2", "clm-human", "user"),
        ]
        ir = self._compile(claims, evidence)
        doc = ir.intermediates.narrative_document
        assert "## In Their Own Words" in doc
        assert "## Grounded in Human Voices" in doc
        assert "## Machine-Derived Context" in doc
        # Ordering of section headers in the document
        assert doc.index("## In Their Own Words") < doc.index("## Grounded in Human Voices")
        assert doc.index("## Grounded in Human Voices") < doc.index("## Machine-Derived Context")

    def test_unclassified_claim_lands_in_human_tier(self):
        # voice_class is untrusted/optional — absence must not demote a
        # human-grounded claim into the machine tier.
        claims = [
            _claim("clm-novoice", "Human claim without voice class.", 0.5, {"user": 2}, None),
            _claim("clm-machine", "Machine claim.", 0.9, {"assistant": 1}, "technical"),
        ]
        evidence = [
            _evidence("ev-0", "clm-novoice", "user"),
            _evidence("ev-1", "clm-machine", "assistant"),
        ]
        ir = self._compile(claims, evidence)
        doc = ir.intermediates.narrative_document
        assert "Human claim without voice class" in doc.split("## Machine-Derived Context")[0]

    def test_contested_and_insufficient_sections_preserved(self):
        claims = [
            _claim("clm-personal", "Personal claim.", 0.5, {"user": 1}, "personal"),
            _claim("clm-contested", "Contested claim.", 0.3, {"user": 1}, "personal", status="CONTESTED"),
            _claim("clm-insuff", "Insufficient claim.", 0.2, {"user": 1}, "personal", status="INSUFFICIENT"),
        ]
        evidence = [_evidence("ev-0", "clm-personal", "user")]
        ir = self._compile(claims, evidence)
        doc = ir.intermediates.narrative_document
        assert "## Contested Claims" in doc
        assert "## Insufficient Evidence" in doc
        assert "Contested claim." in doc
        assert "Insufficient claim." in doc

    def test_document_provenance_header(self):
        # The doc must disclose its claim count and the untrusted nature
        # of voice classes — no silent model trust.
        claims = [_claim("clm-1", "One claim.", 0.5, {"user": 1}, "personal")]
        evidence = [_evidence("ev-0", "clm-1", "user")]
        ir = self._compile(claims, evidence)
        doc = ir.intermediates.narrative_document
        assert "1 claims" in doc
        assert "model-derived and untrusted" in doc

    def test_tier_counts_in_section_intros(self):
        claims = [
            _claim("clm-p1", "Personal one.", 0.5, {"user": 1}, "personal"),
            _claim("clm-p2", "Personal two.", 0.5, {"user": 1}, "personal"),
            _claim("clm-m1", "Machine one.", 0.9, {"assistant": 1}, "technical"),
        ]
        evidence = [
            _evidence("ev-0", "clm-p1", "user"),
            _evidence("ev-1", "clm-p2", "user"),
            _evidence("ev-2", "clm-m1", "assistant"),
        ]
        ir = self._compile(claims, evidence)
        doc = ir.intermediates.narrative_document
        assert "(2)" in doc.split("## Grounded in Human Voices")[0].split("## In Their Own Words")[1]
        assert "(1)" in doc.split("## Machine-Derived Context")[1]

    def test_deterministic_output(self):
        claims = [
            _claim("clm-b", "B claim.", 0.5, {"user": 1}, "personal"),
            _claim("clm-a", "A claim.", 0.5, {"user": 1}, "personal"),
            _claim("clm-m", "Machine.", 0.9, {"assistant": 1}, "technical"),
        ]
        evidence = [
            _evidence("ev-0", "clm-b", "user"),
            _evidence("ev-1", "clm-a", "user"),
            _evidence("ev-2", "clm-m", "assistant"),
        ]
        doc1 = self._compile(claims, evidence).intermediates.narrative_document
        doc2 = self._compile(claims, evidence).intermediates.narrative_document
        assert doc1 == doc2

    def test_shared_policy_helpers_module_level(self):
        # narrative_key / personal_rank / human_share are the single
        # source of ordering truth for view, index summary, and doc.
        c = ClaimExport(
            id="c1", text="t", normalized="t", status="SUPPORTED",
            confidence=0.5, evidence_ids=[], speakers={"user": 1},
            voice_class="personal",
        )
        assert narrative_key(c)[0] == 0
        c2 = ClaimExport(
            id="c2", text="t", normalized="t", status="SUPPORTED",
            confidence=0.5, evidence_ids=[], speakers={"assistant": 1},
            voice_class="technical",
        )
        assert narrative_key(c2)[0] == 2


class TestMarkdownInjectionGuard:
    def _compile(self, claims, evidence):
        comp = ArtifactCompiler(claims=claims, evidence=evidence)
        return comp.compile()

    def test_claim_cannot_forge_section_headers(self):
        # A claim whose text contains a literal "## " header must not
        # create a phantom section in the compiled document.
        claims = [
            _claim("clm-evil", "## Sustainability and Cost Optimization\n\nSome injected section body.", 0.5, {"user": 1}, "personal"),
            _claim("clm-ok", "A normal claim.", 0.5, {"user": 1}, "personal"),
        ]
        evidence = [
            _evidence("ev-0", "clm-evil", "user"),
            _evidence("ev-1", "clm-ok", "user"),
        ]
        ir = self._compile(claims, evidence)
        doc = ir.intermediates.narrative_document
        headers = re.findall(r"^## (.+)$", doc, re.M)
        assert headers == ["In Their Own Words"], f"phantom section forged: {headers}"
        # No line may start with a header marker except compiler sections:
        # the injected text survives inline inside the bullet, where
        # Markdown renders it as list-item text, not structure.
        header_lines = [l for l in doc.splitlines() if l.startswith("#")]
        assert header_lines == ["# Narrative", "## In Their Own Words"], header_lines
        assert "Sustainability and Cost Optimization Some injected section body." in doc

    def test_multiline_claim_flattened(self):
        claims = [
            _claim("clm-ml", "Line one\nLine two\n\nLine three.", 0.5, {"user": 1}, "personal"),
        ]
        evidence = [_evidence("ev-0", "clm-ml", "user")]
        ir = self._compile(claims, evidence)
        doc = ir.intermediates.narrative_document
        assert "- Line one Line two Line three. (confidence: 0.50)" in doc
