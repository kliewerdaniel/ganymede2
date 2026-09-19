# Ganymede 2.0

A sovereign epistemic compiler — local-first, incrementally-compiled, falsifiable knowledge system.

Ingest a corpus, produce a deterministic claim graph, and generate inspectable artifacts showing what the system knows, what it thinks it can establish, what it can't, and where every proposition traces back to.

## What this is

Ganymede 2.0 reframes document-Q&A RAG into a **sovereign epistemic compiler**. Instead of asking "what answer does the corpus contain?", it asks "what can this corpus legitimately establish, what remains unresolved, how did the system arrive there, and can another observer reconstruct that path?"

## Key ideas

- **Two-store separation**: Evidence Graph (immutable, historical) and Epistemic Graph (versioned, interpretive) are physically distinct.
- **Claim-centric**: The fundamental object is a Claim with an 8-state lifecycle, not a document or chunk.
- **Compile-time AI**: Extraction and reasoning happen once at compile time. The system runs without a model; model refinement is optional.
- **Negative knowledge is first-class**: Distinguish "no evidence found" from "evidence insufficient" from "evidence contradicts" from "evidence removed."
- **Agent-agnostic**: Agents propose typed operations; the policy layer evaluates and commits. No agent is both investigator and judge.
- **Deterministic artifacts**: The same corpus always produces the same claim graph and the same compiled artifact.
- **Epistemic reproducibility**: "This claim was SUPPORTED under corpus version A, parser version B, inference provider C, epistemic policy D."

## Status

Week 0 — Specification and ADRs complete. Phase 1 (archaeology) complete. Awaiting Phase 2 implementation.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Next.js static export (Vercel)                              │
│  Multi-view: Narrative / Evidence / Claim / Chronology /     │
│              Contradiction / Provenance / Investigation      │
└──────────────────────────┬──────────────────────────────────┘
                           │ compiled artifact (JSON IR)
┌──────────────────────────▼──────────────────────────────────┐
│  EPISTEMIC ENGINE (local)                                   │
│  ┌─────────────────────┐  ┌──────────────────────────────┐  │
│  │  EVIDENCE GRAPH      │  │  EPISTEMIC GRAPH             │  │
│  │  (immutable store)   │◄─┤  (versioned store)           │  │
│  └─────────────────────┘  └──────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  INGESTION COMPILER │ INFERENCE LAYER │ AGENT POLICY   │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## Quick start

```bash
# Install
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Start infrastructure
docker compose up -d

# Ingest corpus
ganymede ingest ./corpus/sources

# Compile
ganymede compile

# Build artifact
ganymede artifact build

# Serve artifact locally
ganymede artifact serve
```

## Documentation

- `GANYMEDE_2_SPEC.md` — Full specification
- `SKILL.md` — Hermes agent operating instructions
- `adr/` — Architecture Decision Records
- `skills/` — Agent skill files

## Trust constraints

1. Export requires deliberate human action
2. Evidence preserves document hash, page, offsets, retrieval scores, model/version metadata
3. No outbound inference traffic by default
4. No shared database between tenants
5. Authorization filters retrieval before prompt assembly
6. Model output is untrusted data
7. Agents are proposal-only
8. Every operation is recorded in the append-only ledger

## Prior art

- [Ganymede 1.x](https://github.com/kliewerdaniel/ganymede) — Hybrid retrieval, verifier architecture, matter isolation
- [Hermes Atlas](https://github.com/kliewerdaniel/hermes-atlas) — Claim lifecycle, evidence ledger, contradictions, determinism gate, confidence scoring, compile-time extraction
- [Compile-time AI pattern](https://github.com/kliewerdaniel) — Reasoning once at build time into static deterministic artifacts

## License

TBD — pending Conrad's decision on open-source license.
