# ADR 003: Ingestion compiler — deterministic stages with optional model refinement

**Status:** Accepted
**Date:** September 2026
**Deciders:** Conrad (Daniel Kliewer)
**Review trigger:** Before Phase 2 implementation begins, or when a new source format requires a parser that doesn't fit the canonicalization model.

---

## Context

Ganymede 2.0's ingestion pipeline must handle a wide variety of source formats (ChatGPT exports, Reddit exports, PDFs, DOCX, images with OCR, code repos, notes, multimedia transcripts) and produce a uniform, provenance-bearing representation that feeds the Evidence Graph. The question is how to structure this pipeline: as a single monolithic ingest step, as a job queue with independent workers, or as a staged compiler.

Atlas uses a two-layer extraction model: deterministic (sentence splitting, assertion-cue detection) with optional model refinement. Ganymede 1.x uses a synchronous in-process pipeline. Both are partial models. Ganymede 2.0 needs to generalize both into a single ingestion compiler that handles many formats and produces both Evidence Graph records and the raw material for the Epistemic Graph.

---

## Decision

Use a **6-stage ingestion compiler** that is deterministic by default, with optional model refinement at two stages. The compiler runs at compile time, not query time. The output is a set of Evidence Graph records (sources, extractions, evidence units, contradictions) and a set of Epistemic Graph inputs (proposed claims, confidence scores).

### Stage 1: ACQUISITION
- Fetch source from file, URL, API, or export
- Record: `source_id`, `origin`, `fetched_at`, `raw_checksum`
- Validate: file size, MIME type, encoding
- On failure: mark source as `failed` with visible error (never silently create an empty searchable source — carried from Ganymede ADR 003)

### Stage 2: CANONICALIZATION
- Convert every format into a common document envelope:
  ```python
  {
      "id": source_id,
      "type": "conversation" | "post" | "document" | "code_repo" | "image" | "note" | "transcript",
      "text": "full plain text",
      "url": "...",
      "domain": "...",
      "author": "...",
      "fetched_at": timestamp,
      "checksum": sha256,
      "parser_version": "1.0.0",
      "normalization_version": "1.0.0",
      "metadata": {...}  # format-specific extras
  }
  ```
- Format handlers:
  - ChatGPT exports → JSON extraction of turns
  - Reddit exports → JSON extraction of post/comment trees
  - PDF → PyMuPDF page-aware extraction
  - DOCX → python-docx paragraph extraction
  - Images → Tesseract OCR (with OCR confidence metadata)
  - Code repos → file/commit extraction (via git)
  - Notes → plain text with metadata
  - Multimedia transcripts → Whisper transcription (if needed)
- Every handler produces the same envelope. The `type` field tells the structural parser what to expect.

### Stage 3: STRUCTURAL PARSING
- Format-specific decomposition of the canonical envelope:
  - `conversation` → turns (speaker, text, timestamp)
  - `post` → post body + comment tree
  - `document` → pages/sections/passages
  - `code_repo` → files + commits
  - `image` → OCR text + bounding boxes
  - `notes` → paragraphs
  - `transcript` → speaker segments
- Output: structural units with provenance (`source_id`, `offset`, `span`, `structural_unit_id`)
- Each structural unit carries a `structural_unit_id` that is stable across compiles (derived from source_id + offset)

### Stage 4: EVIDENCE UNIT CREATION
- The smallest provenance-bearing object. Created from structural units.
- Fields:
  ```python
  {
      "evidence_id": "ev-" + hash,
      "source_id": "...",
      "claim_id": None,  # filled in Stage 6
      "structural_unit_id": "...",
      "domain": "...",
      "author": "...",
      "stance": "support" | "contradict",
      "quote": "...",  # the actual text span
      "offset": int,
      "timestamp": float,
      "reliability": float,  # 0-1, source-specific prior
      "source_checksum": "...",  # for staleness detection
      "parser_version": "...",
  }
  ```
- Evidence units are the bridge between the Evidence Graph and the Epistemic Graph. They are immutable once written.

### Stage 5: SEMANTIC EXTRACTION (deterministic + optional model)
Two layers:
1. **DETERMINISTIC** (always runs, no model required):
   - Sentence splitting (provenance-preserving, char offsets)
   - Assertion-cue detection (from Atlas's `extract.py`)
   - Entity extraction (proper nouns, acronyms, code tokens)
   - Co-mention relationships (the backbone of the entity graph)
   - Stance classification (support/contradict based on negation cues)

2. **MODEL** (optional, `--local` or configured):
   - Claim text refinement (improve phrasing, resolve ambiguity)
   - Relationship proposal (n-gram misses that a model catches)
   - Confidence adjustment (model-based reliability scoring)
   - Gated: absent model → deterministic layer stands alone, reported as `model: skipped`

Everything emitted here carries provenance back to a `source_id` + `char offset`.

### Stage 6: CLAIM GRAPH CONSTRUCTION
- Merge extractions across sources (accumulate `source_ids`, `mentions`, `co_counts`)
- Build entity co-occurrence graph (from Atlas's `graph.py`)
- Detect contradictions: polarity + topical overlap (from Atlas's `contradictions.py`)
- Compute confidence scores: independence 0.40 + reliability 0.25 + recency 0.15 + corroboration 0.20, multiplicative contradiction penalty (from Atlas's `confidence.py`)
- Assign initial lifecycle status: UNEXAMINED → SUPPORTED/INSUFFICIENT/UNRESOLVED (from ADR 002)
- Write to Evidence Graph store
- Write proposed claims to Epistemic Graph store (for policy evaluation)

### Change detection
- Each stage's output is content-hash gated. Identical input + identical parser = no write.
- The changelog stays silent on unchanged records (the determinism gate).
- Staleness: if a source's checksum changes after extraction, the affected evidence units are flagged `needs_revalidation=True` with `stale_evidence` count > 0.

---

## Consequences

**Enables:**
- **Epistemic reproducibility:** "this claim was SUPPORTED under corpus version A, parser version B, inference provider C, epistemic policy D"
- **Incremental compilation:** unchanged sources are not re-extracted; the changelog proves it
- **Format extensibility:** adding a new format means adding a canonicalizer + structural parser; the rest of the pipeline is unchanged
- **Model sovereignty:** the pipeline runs without a model; model refinement is an enhancement, not a requirement
- **Provenance integrity:** every evidence unit traces to a source + offset + parser version

**Costs:**
- 6 stages to implement and test
- Canonicalization layer adds complexity for each new format
- Model refinement layer adds a dependency boundary that must be carefully managed

**Hardens:**
- The "corpus is immutable infrastructure" principle: raw objects stay recoverable; derived representations regenerate
- The "LLM reasoning only enters after deterministic stages" principle
- The "agent must never be both investigator and judge" principle: agents can propose new sources, but the compiler is the deterministic substrate
- The "negative knowledge is first-class" principle: evidence units with `stance=contradict` are first-class records

---

## Alternatives considered

### Single monolithic ingest step (Ganymede 1.x model)
Rejected. Ganymede 1.x's `ingest_document()` handles PDF/DOCX/plain text but doesn't scale to conversations, code repos, Reddit exports, etc. The 6-stage model generalizes.

### Async job queue (Celery/RQ)
Rejected for MVP. The deterministic stages are fast enough for the initial corpus. The model refinement stage is the only potentially slow part, and it's optional. Revisit when the corpus grows to hundreds of documents.

### Pure LLM extraction (no deterministic layer)
Rejected. Atlas proved that deterministic extraction with 0.667 precision / 1.000 recall is sufficient for the backbone. LLM-only extraction would be slower, less reproducible, and more expensive. The two-layer model is the right tradeoff.

---

## References

- Ganymede 2.0 SPEC.md §5 (Ingestion compiler)
- Ganymede ADR 003 (synchronous in-process ingestion — what we're generalizing)
- Atlas `extract.py` (deterministic + optional model extraction — what we're adopting)
- Atlas `compiler.py` (compile-time model — what we're extending)
