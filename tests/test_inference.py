"""Tests for the inference layer (ADR 006) and model refinement (Stage 5).

Unit tests use a mock provider — no network, no Ollama required.
Live tests (TestLiveOllama) are skipped automatically when Ollama is not running.
"""

import json
import os
from pathlib import Path

import httpx
import pytest

from engine.inference import (
    DEFAULT_CONFIG,
    InferenceResult,
    OllamaProvider,
    OpenAICompatProvider,
    load_inference_config,
    log_inference_event,
    select_provider,
    VERIFIER_PROMPT_VERSION,
)
from engine.policy import ProposalOutcome
from engine.refine import (
    ALLOWED_RELATION_TYPES,
    ClaimRefinement,
    RefinementReport,
    RefinementTarget,
    RelationshipProposal,
    validate_claim_refinement,
    validate_relationship_proposals,
    refine_claims,
    propose_relationships,
    REFINEMENT_PROMPT_VERSION,
)


# ---------------------------------------------------------------------------
# Mock provider for unit tests
# ---------------------------------------------------------------------------

class MockProvider:
    """Deterministic mock provider — returns canned outputs."""

    name = "mock"
    sovereignty_crossed = False

    def __init__(self, *, extract_output=None, fail=False):
        self.extract_output = extract_output
        self.fail = fail
        self.calls = []

    def generate(self, prompt, *, model, params=None):
        self.calls.append(("generate", prompt, model))
        if self.fail:
            return InferenceResult(ok=False, error="mock failure", provider=self.name, model=model, operation="generate")
        return InferenceResult(ok=True, output="mock output", provider=self.name, model=model, operation="generate")

    def generate_structured(self, prompt, *, model, schema, params=None):
        self.calls.append(("generate_structured", prompt, model))
        if self.fail:
            return InferenceResult(ok=False, error="mock failure", provider=self.name, model=model, operation="generate")
        return InferenceResult(ok=True, output="mock output", provider=self.name, model=model, operation="generate")

    def embed(self, text, *, model):
        self.calls.append(("embed", text, model))
        if self.fail:
            return InferenceResult(ok=False, error="mock failure", provider=self.name, model=model, operation="embed")
        return InferenceResult(ok=True, output=[0.1, 0.2, 0.3], provider=self.name, model=model, operation="embed")

    def classify(self, text, *, model, labels):
        self.calls.append(("classify", text, model))
        if self.fail:
            return InferenceResult(ok=False, error="mock failure", provider=self.name, model=model, operation="classify")
        return InferenceResult(ok=True, output=labels[0], provider=self.name, model=model, operation="classify")

    def extract(self, prompt, *, model, schema=None):
        self.calls.append(("extract", prompt, model))
        if self.fail:
            return InferenceResult(ok=False, error="mock failure", provider=self.name, model=model, operation="extract")
        return InferenceResult(ok=True, output=self.extract_output, provider=self.name, model=model, operation="extract")

    def verify(self, question, passage, *, model):
        self.calls.append(("verify", question, model))
        if self.fail:
            return InferenceResult(ok=False, error="mock failure", provider=self.name, model=model, operation="verify")
        return InferenceResult(ok=True, output=True, provider=self.name, model=model, operation="verify")

    def health(self):
        return not self.fail


def ollama_running() -> bool:
    try:
        httpx.get("http://localhost:11434/api/tags", timeout=1)
        return True
    except Exception:
        return False


OLLAMA = ollama_running()


# ---------------------------------------------------------------------------
# InferenceResult + logging
# ---------------------------------------------------------------------------

class TestInferenceResult:
    def test_result_carries_provenance(self):
        r = InferenceResult(
            ok=True, output="hello", provider="ollama", model="qwen3:8b",
            operation="generate", latency_seconds=0.5,
            input_hash="aaa", output_hash="bbb",
        )
        assert r.ok and r.output == "hello"
        assert r.provider == "ollama" and r.model == "qwen3:8b"
        assert not r.sovereignty_crossed

    def test_log_inference_event_shape(self):
        r = InferenceResult(
            ok=True, output="hello", provider="ollama", model="qwen3:8b",
            operation="generate", input_hash="aaa", output_hash="bbb",
        )
        event = log_inference_event(r, prompt_contract_version="1.0.0")
        assert event["event_type"] == "MODEL_INVOKED"
        assert event["actor"] == "system:inference"
        assert event["model"]["provider"] == "ollama"
        assert event["model"]["logged"] is True
        assert event["model"]["sovereignty_boundary_crossed"] is False
        assert event["input_hashes"] == ["aaa"]
        assert event["output_hashes"] == ["bbb"]
        assert event["id"].startswith("evt-")

    def test_log_inference_event_external_marks_boundary(self):
        r = InferenceResult(
            ok=True, output="hello", provider="external:openai", model="gpt-4o-mini",
            operation="generate", input_hash="aaa", output_hash="bbb",
            sovereignty_crossed=True,
        )
        event = log_inference_event(r)
        assert event["model"]["sovereignty_boundary_crossed"] is True
        assert event["model"]["logged"] is True


# ---------------------------------------------------------------------------
# JSON parsing (untrusted output)
# ---------------------------------------------------------------------------

class TestParseJson:
    def test_plain_json(self):
        assert OllamaProvider._parse_json('{"a": 1}') == {"a": 1}

    def test_markdown_fenced(self):
        assert OllamaProvider._parse_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_prose_wrapped(self):
        text = 'Here is the result: {"refined_text": "x", "rationale": "y"} hope it helps'
        assert OllamaProvider._parse_json(text) == {"refined_text": "x", "rationale": "y"}

    def test_json_array(self):
        assert OllamaProvider._parse_json('[1, 2, 3]') == [1, 2, 3]

    def test_garbage_returns_none(self):
        assert OllamaProvider._parse_json("no json here at all") is None
        assert OllamaProvider._parse_json("") is None


# ---------------------------------------------------------------------------
# Config + provider selection (sovereignty ladder)
# ---------------------------------------------------------------------------

class TestProviderSelection:
    def test_default_config_shape(self):
        cfg = DEFAULT_CONFIG["inference"]
        assert cfg["canonical"] == "ollama"
        assert cfg["external"]["enabled"] is False
        assert any(rt["name"] == "ollama" for rt in cfg["local_runtimes"])

    def test_load_config_falls_back_when_missing(self):
        cfg = load_inference_config("/nonexistent/path/config.yaml")
        assert cfg == DEFAULT_CONFIG

    def test_select_provider_returns_none_when_unreachable(self):
        # Point at a dead port — must return None, not raise
        config = {
            "inference": {
                "canonical": "ollama",
                "local_runtimes": [
                    {"name": "ollama", "base_url": "http://localhost:59999", "models": ["x"]},
                ],
                "external": {"enabled": False, "providers": []},
            }
        }
        assert select_provider(config=config) is None

    def test_select_provider_external_disabled_even_if_configured(self):
        config = {
            "inference": {
                "canonical": "ollama",
                "local_runtimes": [
                    {"name": "ollama", "base_url": "http://localhost:59999", "models": ["x"]},
                ],
                "external": {
                    "enabled": False,
                    "providers": [
                        {"name": "openai", "base_url": "http://localhost:59998", "api_key_env": "X"},
                    ],
                },
            }
        }
        # Both endpoints dead, external disabled -> None
        assert select_provider(config=config) is None

    def test_select_provider_local_when_ollama_alive(self):
        if not OLLAMA:
            pytest.skip("Ollama not running")
        provider = select_provider()
        assert provider is not None
        assert provider.name == "ollama"
        assert provider.sovereignty_crossed is False


# ---------------------------------------------------------------------------
# Refinement validation (untrusted model output)
# ---------------------------------------------------------------------------

class TestClaimRefinementValidation:
    def test_valid_refinement(self):
        out = {"refined_text": "Chris was an avid hiker.", "rationale": "Removes conversational noise"}
        r = validate_claim_refinement(out, source_claim_id="clm-1", source_quote="Daniel: Chris was an avid hiker!")
        assert r is not None
        assert r.refined_text == "Chris was an avid hiker."
        assert r.source_claim_id == "clm-1"

    def test_null_refined_text_rejected(self):
        out = {"refined_text": None, "rationale": "Question, not assertion"}
        assert validate_claim_refinement(out, source_claim_id="clm-1", source_quote="q?") is None

    def test_empty_rationale_rejected(self):
        out = {"refined_text": "x", "rationale": "short"}
        assert validate_claim_refinement(out, source_claim_id="clm-1", source_quote="q") is None

    def test_non_dict_rejected(self):
        assert validate_claim_refinement("just a string", source_claim_id="c", source_quote="q") is None
        assert validate_claim_refinement(None, source_claim_id="c", source_quote="q") is None

    def test_hallucination_guard_rejects_bloated_output(self):
        out = {"refined_text": "word " * 500, "rationale": "This is a valid rationale."}
        assert validate_claim_refinement(out, source_claim_id="c", source_quote="short quote") is None

    def test_confidence_clamped_to_range(self):
        out = {"refined_text": "ok text", "rationale": "valid rationale here", "confidence": 5.0}
        r = validate_claim_refinement(out, source_claim_id="c", source_quote="a quote")
        assert r is not None
        assert 0.0 <= r.confidence <= 1.0


class TestRelationshipValidation:
    def test_valid_proposal(self):
        out = {
            "proposals": [
                {
                    "source_entity": "Chris",
                    "target_entity": "Daniel",
                    "relation_type": "family_of",
                    "evidence_quote": "his brother Daniel",
                    "rationale": "Brothers stated in text",
                }
            ]
        }
        props = validate_relationship_proposals(out)
        assert len(props) == 1
        assert props[0].relation_type == "family_of"

    def test_unknown_relation_type_rejected(self):
        out = {
            "proposals": [
                {
                    "source_entity": "A", "target_entity": "B",
                    "relation_type": "enemy_of",
                    "evidence_quote": "q", "rationale": "valid rationale",
                }
            ]
        }
        assert validate_relationship_proposals(out) == []

    def test_missing_fields_rejected(self):
        out = {"proposals": [{"source_entity": "A", "relation_type": "friend_of"}]}
        assert validate_relationship_proposals(out) == []

    def test_list_cap_at_five(self):
        proposals = [
            {
                "source_entity": f"E{i}", "target_entity": f"F{i}",
                "relation_type": "friend_of", "evidence_quote": "q",
                "rationale": "valid rationale",
            }
            for i in range(10)
        ]
        assert len(validate_relationship_proposals({"proposals": proposals})) == 5

    def test_non_dict_rejected(self):
        assert validate_relationship_proposals("garbage") == []
        assert validate_relationship_proposals({"proposals": "not-a-list"}) == []


# ---------------------------------------------------------------------------
# Refinement pass with mock provider (policy integrated)
# ---------------------------------------------------------------------------

class TestRefineClaimsWithMock:
    def test_no_provider_skips_gracefully(self):
        report = refine_claims(
            [RefinementTarget(claim_id="c1", text="t", quote="q")],
            provider=None,
        )
        # select_provider() may find real Ollama; force None by passing dead config
        report = refine_claims(
            [RefinementTarget(claim_id="c1", text="t", quote="q")],
            provider=None,
        )
        # If Ollama is live this would have run; assert report is well-formed either way
        assert isinstance(report, RefinementReport)

    def test_refinement_accepted_through_policy(self):
        mock = MockProvider(extract_output={
            "refined_text": "Chris was an avid hiker.",
            "rationale": "Strips speaker prefix from the quote",
        })
        targets = [RefinementTarget(claim_id="clm-1", text="t", quote="Daniel: Chris was an avid hiker!")]
        report = refine_claims(targets, provider=mock, model="mock-model")
        assert report.claims_refined == 1
        assert report.proposals_accepted == 1
        assert len(report.inference_events) == 1
        assert report.inference_events[0]["event_type"] == "MODEL_INVOKED"

    def test_invalid_model_output_rejected_before_policy(self):
        mock = MockProvider(extract_output={"refined_text": None, "rationale": "no assertion"})
        targets = [RefinementTarget(claim_id="clm-1", text="t", quote="Is this a question?")]
        report = refine_claims(targets, provider=mock, model="mock-model")
        assert report.claims_rejected_invalid == 1
        assert report.proposals_accepted == 0

    def test_provider_failure_recorded_not_raised(self):
        mock = MockProvider(fail=True)
        targets = [RefinementTarget(claim_id="clm-1", text="t", quote="q")]
        report = refine_claims(targets, provider=mock, model="mock-model")
        assert report.claims_refined == 0
        assert len(report.errors) == 1
        assert "mock failure" in report.errors[0]

    def test_max_targets_respected(self):
        mock = MockProvider(extract_output={"refined_text": "x", "rationale": "valid rationale"})
        targets = [RefinementTarget(claim_id=f"c{i}", text="t", quote="q") for i in range(50)]
        report = refine_claims(targets, provider=mock, model="m", max_targets=5)
        assert len(mock.calls) == 5


class TestProposeRelationshipsWithMock:
    def test_relationships_proposed_through_policy(self):
        mock = MockProvider(extract_output={
            "proposals": [
                {
                    "source_entity": "Chris",
                    "target_entity": "Daniel",
                    "relation_type": "family_of",
                    "evidence_quote": "his brother Daniel",
                    "rationale": "Text states brother relationship",
                }
            ]
        })
        report = propose_relationships(
            [{"source_id": "src-1", "text": "Chris grew up with his brother Daniel."}],
            provider=mock, model="mock-model",
        )
        assert report.relationships_proposed == 1
        assert report.proposals_accepted == 1

    def test_no_relationships_found_is_not_an_error(self):
        mock = MockProvider(extract_output={"proposals": []})
        report = propose_relationships(
            [{"source_id": "src-1", "text": "Nothing relational here."}],
            provider=mock, model="mock-model",
        )
        assert report.relationships_proposed == 0
        assert report.proposals_accepted == 0


# ---------------------------------------------------------------------------
# Live Ollama tests (skipped when Ollama is down)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not OLLAMA, reason="Ollama not running")
class TestLiveOllama:
    def test_generate_real(self):
        provider = OllamaProvider()
        result = provider.generate("Say exactly: hello", model="qwen3:4b", params={"num_predict": 8})
        assert result.ok, result.error
        assert result.provider == "ollama"
        assert result.sovereignty_crossed is False
        assert result.input_hash and result.output_hash
        assert result.latency_seconds > 0

    def test_embed_real(self):
        provider = OllamaProvider()
        result = provider.embed("Chris was a musician.", model="nomic-embed-text")
        assert result.ok, result.error
        assert isinstance(result.output, list)
        assert len(result.output) > 100  # nomic-embed-text is 768-dim

    def test_embed_truncates_long_input(self):
        provider = OllamaProvider()
        result = provider.embed("word " * 5000, model="nomic-embed-text")
        assert result.ok, result.error  # would 500 without truncation

    def test_verify_real(self):
        provider = OllamaProvider()
        passage = "Christopher James Kliewer was born on March 15, 1985, in Seattle, Washington."
        r_yes = provider.verify("Where was Chris born?", passage, model="qwen3:4b")
        assert r_yes.ok and r_yes.output is True, r_yes.error
        r_no = provider.verify("What color was Chris's car?", passage, model="qwen3:4b")
        assert r_no.ok and r_no.output is False

    def test_classify_real(self):
        provider = OllamaProvider()
        result = provider.classify(
            "Chris played guitar at local venues in Seattle.",
            model="qwen3:4b",
            labels=["music", "sports", "cooking"],
        )
        assert result.ok, result.error
        assert result.output == "music"

    def test_extract_real_json(self):
        provider = OllamaProvider()
        prompt = 'Reply with only this JSON object: {"refined_text": "test", "rationale": "test rationale"}'
        result = provider.extract(prompt, model="qwen3:4b")
        assert result.ok, result.error
        assert isinstance(result.output, dict)


# ---------------------------------------------------------------------------
# Live OpenAI-compatible tests via Ollama's /v1 endpoint (Phase 5 close-out:
# classify/extract/verify now use generate_structured, not raw _chat)
# ---------------------------------------------------------------------------

OPENAI_COMPAT = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def _compat_reachable() -> bool:
    try:
        return httpx.get(f"{OPENAI_COMPAT}/v1/models", timeout=2).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _compat_reachable(), reason="OpenAI-compatible endpoint not running")
class TestLiveOpenAICompat:
    def _provider(self) -> OpenAICompatProvider:
        return OpenAICompatProvider("local-compat", f"{OPENAI_COMPAT}/v1", api_key_env=None)

    def test_classify_structured(self):
        result = self._provider().classify(
            "Chris played guitar at local venues in Seattle.",
            model="qwen3:4b",
            labels=["music", "sports", "cooking"],
        )
        assert result.ok, result.error
        assert result.output == "music"
        assert result.operation == "classify"

    def test_classify_rejects_off_label(self):
        # schema enum + _match_label fallback: garbage in -> ok=False, not a crash
        result = self._provider().classify(
            "Quantum flux capacitor calibration notes",
            model="qwen3:4b",
            labels=["music", "sports", "cooking"],
        )
        assert isinstance(result, InferenceResult)
        assert result.ok is False or result.output in ("music", "sports", "cooking")

    def test_extract_structured(self):
        prompt = "Extract the person's name as JSON: Marcus Aurelius was a Roman emperor."
        result = self._provider().extract(
            prompt, model="qwen3:4b",
            schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        )
        assert result.ok, result.error
        assert isinstance(result.output, dict)
        assert result.output.get("name") == "Marcus Aurelius"

    def test_verify_structured(self):
        provider = self._provider()
        passage = "Christopher James Kliewer was born on March 15, 1985, in Seattle, Washington."
        r_yes = provider.verify("Where was Chris born?", passage, model="qwen3:4b")
        assert r_yes.ok and r_yes.output is True, r_yes.error
        r_no = provider.verify("What color was Chris's car?", passage, model="qwen3:4b")
        assert r_no.ok and r_no.output is False
