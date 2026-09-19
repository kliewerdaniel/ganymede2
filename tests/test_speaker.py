"""Tests for speaker provenance: derivation, persistence, and narrative ordering."""
import pytest

from engine.extract import speaker_at, extract_source
from engine.artifact_compiler import ArtifactCompiler
from engine.artifact_ir import ClaimExport


CONV_TEXT = """# Conversation: test

## Metadata

- **Conversation ID**: `test`

## Messages

### 👤 User
**Timestamp**: 2023-03-12 11:36:03

He was a software engineer and a musician.

---

### 🤖 Assistant
**Timestamp**: 2023-03-12 11:36:21

All the files uploaded by the user have been fully loaded. The user is asking about music.

---

### ⚙️ System
**Timestamp**: 2023-03-12 11:36:22

You are ChatGPT.
"""


class TestSpeakerAt:
    def test_user_turn(self):
        off = CONV_TEXT.find("He was a software engineer")
        assert speaker_at(CONV_TEXT, off, "conversation") == "user"

    def test_assistant_turn(self):
        off = CONV_TEXT.find("All the files uploaded")
        assert speaker_at(CONV_TEXT, off, "conversation") == "assistant"

    def test_system_turn(self):
        off = CONV_TEXT.find("You are ChatGPT.")
        assert speaker_at(CONV_TEXT, off, "conversation") == "system"

    def test_before_first_marker_is_none(self):
        off = CONV_TEXT.find("# Conversation")
        assert speaker_at(CONV_TEXT, off, "conversation") is None

    def test_post_is_author(self):
        assert speaker_at("any text", 0, "post") == "author"

    def test_document_is_none(self):
        assert speaker_at("any text", 0, "document") is None

    def test_last_marker_wins(self):
        # offset inside the assistant turn but after a user marker earlier
        text = "### 👤 User\nhello\n\n### 🤖 Assistant\nworld\n"
        off = text.find("world")
        assert speaker_at(text, off, "conversation") == "assistant"


class TestSpeakerInExtraction:
    def test_extract_source_tags_speakers(self):
        source = {
            "id": "src-test",
            "type": "conversation",
            "text": CONV_TEXT,
            "checksum": "abc",
            "fetched_at": 1710000000.0,
        }
        ex = extract_source(source)
        assert ex.evidence, "extraction produced no evidence"
        speakers = {e["speaker"] for e in ex.evidence}
        assert "user" in speakers or "assistant" in speakers
        for e in ex.evidence:
            assert e["speaker"] in ("user", "assistant", "system", None)


class TestNarrativeOrdering:
    def _claim(self, cid, conf, speakers):
        return {
            "id": cid, "text": f"claim {cid}", "normalized": cid,
            "status": "SUPPORTED", "confidence": conf,
            "evidence_ids": [f"ev-{i}" for i in range(2)],
            "speakers": speakers,
        }

    def test_human_grounding_outranks_confidence(self):
        # Machine claim has HIGHER confidence but no human evidence.
        claims = [
            self._claim("clm-machine", 0.9, {"assistant": 3}),
            self._claim("clm-human", 0.5, {"user": 2}),
        ]
        evidence = [
            {"id": "ev-0", "source_id": "s", "claim_id": "clm-machine",
             "speaker": "assistant", "quote": "q", "offset": 0,
             "source_checksum": "c", "parser_version": "1"},
            {"id": "ev-1", "source_id": "s", "claim_id": "clm-human",
             "speaker": "user", "quote": "q", "offset": 0,
             "source_checksum": "c", "parser_version": "1"},
        ]
        comp = ArtifactCompiler(claims=claims, evidence=evidence)
        tallies = comp._speaker_tallies()
        assert tallies == {"clm-machine": {"assistant": 1}, "clm-human": {"user": 1}}
        exports = [comp._build_claim(c, tallies) for c in claims]
        by_id = {e.id: e for e in exports}
        assert by_id["clm-machine"].speakers == {"assistant": 1}
        assert by_id["clm-human"].speakers == {"user": 1}

        # The narrative ordering key must rank human share first.
        def human_share(c: ClaimExport) -> float:
            if not c.speakers:
                return 0.0
            human = c.speakers.get("user", 0) + c.speakers.get("author", 0)
            return human / sum(c.speakers.values())

        ranked = sorted(exports, key=lambda c: (-human_share(c), -c.confidence, c.id))
        assert ranked[0].id == "clm-human"

    def test_deterministic_tiebreak(self):
        # Equal human share + confidence -> ID breaks the tie.
        claims = [
            self._claim("clm-b", 0.5, {"user": 1}),
            self._claim("clm-a", 0.5, {"user": 1}),
        ]
        comp = ArtifactCompiler(claims=claims, evidence=[])
        exports = [comp._build_claim(c, {}) for c in claims]
        def human_share(c):
            if not c.speakers:
                return 0.0
            return (c.speakers.get("user", 0) + c.speakers.get("author", 0)) / sum(c.speakers.values())
        ranked = sorted(exports, key=lambda c: (-human_share(c), -c.confidence, c.id))
        assert [c.id for c in ranked] == ["clm-a", "clm-b"]
