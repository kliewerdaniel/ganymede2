# ADR 004: Evidence Graph model — immutable, provenance-bearing

**Status:** Accepted
**Date:** September 2026
**Deciders:** Conrad (Daniel Kliewer)
**Review trigger:** Before Phase 2 implementation begins, or when a new evidence type doesn't fit the model.

---

## Context

The Evidence Graph is the historical record of what was in the corpus. It must be immutable (once written, records are never deleted), provenance-bearing (every record traces to a source + offset + parser version), and content-hash gated (identical input produces no write). The question is what the Evidence Graph actually contains and how it's stored.

---

## Decision

The Evidence Graph contains **four record types**, all append-only, all content-hash gated:

### 1. Sources
```python
{
    "id": "src-" + sha256(origin + fetched_at),
    "type": "conversation" | "post" | "document" | "code_repo" | "image" | "note" | "transcript",
    "origin": "file:///..." | "https://..." | "chatgpt-export" | "reddit-export",
    "text": "full plain text",
    "url": "...",
    "domain": "...",
    "author": "...",
    "fetched_at": timestamp,
    "checksum": sha256(text),
    "parser_version": "1.0.0",
    "normalization_version": "1.0.0",
    "status": "active" | "removed",
    "metadata": {...},
    "_meta": {
        "content_hash": sha256(all other fields),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
}
```

- `status="removed"` is a tombstone, not a deletion. The record persists.
- `checksum` is the content hash of the source text. If the same text is ingested again, the existing record is returned (idempotency).

### 2. Structural Units
```python
{
    "id": "su-" + sha256(source_id + structural_type + offset),
    "source_id": "src-...",
    "type": "turn" | "page" | "paragraph" | "file" | "commit" | "ocr_block" | "speaker_segment",
    "text": "the structural unit's text",
    "offset": int,  # char offset in source text
    "span": [start, end],
    "parent_id": "su-..." | None,  # for nested structures (e.g., comment under post)
    "metadata": {...},  # format-specific (page number, speaker, timestamp, etc.)
    "_meta": {...},
}
```

- Stable across compiles: same source_id + same offset = same structural_unit_id.
- Enables evidence units to reference a stable structural location.

### 3. Evidence Units
```python
{
    "id": "ev-" + sha256(source_id + offset + quote),
    "source_id": "src-...",
    "structural_unit_id": "su-...",
    "claim_id": "clm-..." | None,  # filled in Stage 6
    "domain": "...",
    "author": "...",
    "stance": "support" | "contradict",
    "quote": "the actual text span",
    "offset": int,
    "timestamp": float,
    "reliability": float,
    "source_checksum": "...",  # for staleness detection
    "parser_version": "...",
    "needs_revalidation": bool,
    "stale_evidence": int,  # count of stale source checksums
    "_meta": {...},
}
```

- The bridge between Evidence Graph and Epistemic Graph.
- Immutable once written. Staleness is flagged, not silently corrected.

### 4. Contradictions
```python
{
    "id": "con-" + sha256(sorted([claim_a_id, claim_b_id])),
    "anchor_words": ["word1", "word2"],
    "entity_id": "ent-...",
    "claim_a": "clm-...",
    "claim_b": "clm-...",
    "text_a": "...",
    "text_b": "...",
    "overlap": float,
    "sources_a": ["src-..."],
    "sources_b": ["src-..."],
    "status": "open" | "resolved" | "accepted_tension",
    "resolution": str | None,
    "resolved_by": str | None,
    "_meta": {...},
}
```

- Both sides retain their own claim record and confidence score.
- Resolution is an explicit, logged act — never a side effect of the newest source winning.

### Storage
- PostgreSQL with JSONB columns for flexible metadata.
- Content-hash gating: before writing, compute `content_hash` over all fields except `_meta.updated_at`. If a record with the same `content_hash` already exists, the write is a no-op (changelog stays silent).
- Indexes on `source_id`, `claim_id`, `stance`, `status`.

---

## Consequences

**Enables:**
- Full provenance: every evidence unit traces to a source + offset + parser version
- Staleness detection: if a source's checksum changes, affected evidence units are flagged
- Contradiction preservation: contradicted claims survive delta recompiles
- Determinism: identical inputs produce identical Evidence Graph state

**Costs:**
- PostgreSQL dependency (vs. Atlas's stdlib flat files)
- JSONB storage is less queryable than normalized columns (mitigated by indexes on common fields)

**Hardens:**
- The "corpus is immutable infrastructure" principle
- The "raw objects stay recoverable" principle

---

## Alternatives considered

### Stdlib flat files (Atlas model)
Rejected. Atlas's flat-file store works for a research tool with a small corpus. Ganymede 2.0's corpus is larger, the litigation domain has regulatory implications for evidence handling, and PostgreSQL + pgvector is already proven in Ganymede 1.x.

### Normalized relational schema
Rejected for MVP. The metadata fields vary by source type (conversations have speakers, documents have pages, code repos have commits). JSONB handles this flexibility. Normalize later if query patterns demand it.

---

## References

- Ganymede 2.0 SPEC.md §3 (Two-store separation)
- Ganymede 2.0 SPEC.md §5 (Ingestion compiler)
- Atlas `store.py` (single-store pattern — what we're diverging from)
