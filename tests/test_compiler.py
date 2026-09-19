"""Tests for the ingestion compiler."""

import pytest
import pytest_asyncio
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.canonicalize import read_source_file, structural_parse, normalize_text, _make_envelope
from engine.extract import extract_source, is_claim, stance_of, normalise_entity, claim_id, entity_id
from engine.confidence import score_claim, EvidenceRef
from engine.contradictions import mine_contradictions, overlap, contradiction_id
from engine.lifecycle import ClaimStatus, initial_status, is_legal_transition


class TestCanonicalize:
    def test_make_envelope(self):
        envelope = _make_envelope(
            text="Hello world",
            source_type="document",
            origin="test.txt",
            metadata={},
        )
        assert envelope["type"] == "document"
        assert envelope["text"] == "Hello world"
        assert envelope["checksum"] is not None
        assert envelope["id"].startswith("src-")

    def test_normalize_text(self):
        assert normalize_text("Hello World") == "hello world"
        assert normalize_text("  Hello   World  ") == "hello world"

    def test_structural_parse_document(self):
        source = _make_envelope(
            text="First paragraph.\n\nSecond paragraph.",
            source_type="document",
            origin="test.txt",
            metadata={},
        )
        units = structural_parse(source)
        assert len(units) == 2
        assert units[0]["type"] == "paragraph"
        assert units[0]["offset"] == 0


class TestExtract:
    def test_is_claim(self):
        assert is_claim("The quick brown fox is a well-known pangram used for testing fonts.")
        assert not is_claim("Hello world.")
        assert not is_claim("This is a test.")

    def test_stance_of(self):
        assert stance_of("The sky is blue.") == "support"
        assert stance_of("The sky is not blue.") == "contradict"

    def test_normalise_entity(self):
        assert normalise_entity("Hello World") == "hello world"
        assert normalise_entity("Hello-World") == "hello world"

    def test_claim_id_deterministic(self):
        id1 = claim_id("The sky is blue.", "src-123")
        id2 = claim_id("The sky is blue.", "src-123")
        assert id1 == id2

    def test_entity_id_deterministic(self):
        id1 = entity_id("Hello World")
        id2 = entity_id("Hello World")
        assert id1 == id2

    def test_extract_source(self):
        source = _make_envelope(
            text="The quick brown fox jumps over the lazy dog. " * 10,
            source_type="document",
            origin="test.txt",
            metadata={},
        )
        extraction = extract_source(source)
        assert isinstance(extraction.entities, list)
        assert isinstance(extraction.claims, list)
        assert isinstance(extraction.evidence, list)


class TestConfidence:
    def test_score_claim_no_evidence(self):
        result = score_claim([])
        assert result.score == 0.0

    def test_score_claim_single_evidence(self):
        refs = [EvidenceRef(evidence_id="ev-1", source_id="src-1", quote="test")]
        result = score_claim(refs)
        assert 0.0 <= result.score <= 1.0

    def test_score_claim_contradiction(self):
        refs = [
            EvidenceRef(evidence_id="ev-1", source_id="src-1", stance="support"),
            EvidenceRef(evidence_id="ev-2", source_id="src-2", stance="contradict"),
        ]
        result = score_claim(refs)
        assert result.contested
        assert result.score < 0.5


class TestContradictions:
    def test_overlap(self):
        assert overlap("The sky is blue", "The sky is not blue") > 0.5
        assert overlap("The sky is blue", "Cats are mammals") < 0.3

    def test_mine_contradictions(self):
        claims = [
            {"id": "clm-1", "text": "The sky is blue.", "source_ids": ["src-1"]},
            {"id": "clm-2", "text": "The sky is not blue.", "source_ids": ["src-2"]},
        ]
        contradictions = mine_contradictions(claims)
        assert len(contradictions) >= 1

    def test_contradiction_id_deterministic(self):
        id1 = contradiction_id("clm-1", "clm-2")
        id2 = contradiction_id("clm-2", "clm-1")
        assert id1 == id2


class TestLifecycle:
    def test_initial_status_no_evidence(self):
        assert initial_status([], 0.0) == ClaimStatus.UNRESOLVED

    def test_initial_status_low_confidence(self):
        refs = [EvidenceRef(evidence_id="ev-1", source_id="src-1")]
        assert initial_status(refs, 0.1) == ClaimStatus.INSUFFICIENT

    def test_initial_status_supported(self):
        refs = [EvidenceRef(evidence_id="ev-1", source_id="src-1")]
        assert initial_status(refs, 0.8) == ClaimStatus.SUPPORTED

    def test_legal_transition(self):
        assert is_legal_transition(ClaimStatus.UNEXAMINED, ClaimStatus.SUPPORTED)
        assert is_legal_transition(ClaimStatus.SUPPORTED, ClaimStatus.VALIDATED)
        assert not is_legal_transition(ClaimStatus.UNEXAMINED, ClaimStatus.VALIDATED)

    def test_illegal_skip(self):
        assert not is_legal_transition(ClaimStatus.RETRACTED, ClaimStatus.SUPPORTED)
