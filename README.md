# Ganymede 2.0

**A sovereign epistemic compiler — local-first, incrementally-compiled, falsifiable knowledge system.**

Ingest a corpus. Compile it into a deterministic claim graph. Inspect what the system knows, what it can establish, what it can't, and where every proposition traces back to — down to character offsets in the original sources.

[![Deploy with Vercel](https://img.shields.io/badge/deploy-Vercel-black)](https://ganymede-artifact.vercel.app)

---

## What this is

Ganymede 2.0 reframes document-QA RAG into a **sovereign epistemic compiler**. Instead of asking *"what answer does the corpus contain?"*, it asks:

> What can this corpus legitimately establish, what remains unresolved, how did the system arrive there, and can another observer reconstruct that path?

The output is not a chatbot. It's a **compiled static artifact** — a website you can host anywhere, generated entirely at compile time, with no inference server in the loop at view time.

```
┌─────────────────────────────────────────────────────────────┐
│  EXPOSED: Next.js static export (Vercel)                    │
│  11 views · 32 static pages · 82 kB first-load JS           │
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
└─────────────────────────────────────────────────────────────┘
```

## Screenshots

**Narrative view** — established claims, ordered by confidence, each traceable to evidence:

![Narrative view](docs/screenshots/narrative-view.png)

**Claims table** — the full Epistemic Graph, filterable and searchable, every claim linked to its provenance:

![Claims view](docs/screenshots/claims-view.png)

**Claim detail** — confidence decomposition, linked evidence units, full provenance metadata:

![Claim detail](docs/screenshots/claim-detail.png)

**Evidence view** — evidence units grouped by source, with character offsets into the original documents:

![Evidence view](docs/screenshots/evidence-view.png)

**Source inventory** — what was ingested, when, by which parser version:

![Source inventory](docs/screenshots/source-inventory.png)

## Key ideas

- **Two-store separation** — Evidence Graph (immutable, content-hash gated) and Epistemic Graph (versioned, interpretive) are physically distinct. What was said can never be rewritten; what we conclude about it can be revised, with history retained.
- **Claim-centric** — the fundamental object is a Claim with an 8-state lifecycle, not a document or chunk.
- **Compile-time AI** — extraction and reasoning happen once at compile time. The artifact runs without a model; model refinement is optional and untrusted.
- **Negative knowledge is first-class** — "no evidence found" ≠ "evidence insufficient" ≠ "evidence contradicts" ≠ "evidence removed".
- **Agents propose, policy decides** — agents are proposal-only. A PolicyEvaluator enforces authorization, schema, confidence bounds, and sovereignty boundaries. No agent is both investigator and judge.
- **Deterministic artifacts** — the same corpus always produces the same claim graph and the same compiled artifact. `identical input → identical output` is a test-enforced gate.
- **Epistemic reproducibility** — every claim records: "SUPPORTED under corpus version A, parser version B, inference provider C, epistemic policy D."

## The 8-state claim lifecycle

```
UNEXAMINED → SUPPORTED → VALIDATED
                ↓            ↓
             CONTESTED    INSUFFICIENT
                ↓            ↓
            UNRESOLVED   RETRACTED
                             ↓
                         SUPERSEDED
```

Every transition is recorded in an append-only ledger.

## Quick start

```bash
# Install
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Start infrastructure (PostgreSQL 16 + pgvector, Ollama)
docker compose up -d

export DATABASE_URL=postgresql+asyncpg://ganymede:ganymede@localhost:5432/ganymede

# Ingest a corpus → 6-stage compiler → claim graph
ganymede ingest ./corpus/sources

# Build the artifact IR (JSON) + intermediates
ganymede artifact build --output ./dist

# Build the static site
cd artifact/nextjs && npm install && npm run build
# → artifact/nextjs/out/  (deploy anywhere; no server needed)

# Serve locally to inspect
python3 -m http.server 4173 -d artifact/nextjs/out
```

## CLI

| Command | What it does |
|---------|--------------|
| `ganymede ingest <dir>` | Ingest corpus → canonicalize → parse → extract → claim graph |
| `ganymede compile <dir>` | Compile corpus (same pipeline, explicit cycle control) |
| `ganymede artifact build` | Build artifact IR + intermediates (narrative, knowledge graph, timeline, dossiers) |
| `ganymede artifact serve` | Serve the artifact locally on a port |
| `ganymede agents` | Run the 8-agent proposal pipeline against the database |
| `ganymede agents --agent researcher` | Run a single agent |
| `ganymede investigate` | Propose investigations from unresolved claims |
| `ganymede refine --model qwen3:8b` | Optional model refinement (local Ollama, Level 1 sovereignty) |
| `ganymede gate` | Run quality gates (determinism, schema, provenance) |
| `ganymede explain <claim_id>` | Explain a claim — full provenance chain |
| `ganymede status` | Corpus status summary |

## The agent system

Eight agents, all proposal-only, each authorized for specific operations (ADR 007):

| Agent | Role | Can propose |
|-------|------|-------------|
| `corpus-cartographer` | Maps corpus structure, ingestion priorities | INGEST, EXTRACT |
| `extractor` | Proposes claims from evidence | CLAIM_PROPOSE |
| `researcher` | Cross-source connections, external lookup flags | EXTRACT, CLAIM_PROPOSE |
| `evidence-analyst` | Evidence quality, reliability concerns | EVALUATE_EVIDENCE |
| `temporal-analyst` | Temporal ordering of events | TEMPORAL_ORDER |
| `contradiction-analyst` | Detects and proposes resolutions for contradictions | CONTRADICT_DETECT, CONTRADICT_RESOLVE |
| `synthesis-agent` | Proposes investigations from unresolved claims | INVESTIGATION_PROPOSE |
| `artifact-compiler` | Proposes artifact compilation | ARTIFACT_COMPILE |

Every proposal is evaluated by `PolicyEvaluator`: schema → authorization → confidence bounds → sovereignty logging → **ACCEPTED / REJECTED / NEEDS_REVIEW / DEFERRED**. Accepted proposals commit to the Epistemic Graph with full provenance.

## Confidence model

```
confidence = 0.40·independence + 0.25·reliability + 0.15·recency + 0.20·corroboration
```

- Independence by provenance domain/author
- Reliability defaults to 0.5, source-adjustable
- Recency half-life: 540 days (~18 months)
- Contradictions apply multiplicatively

Every claim's confidence terms are visible in the artifact (claim detail page).

## Trust constraints

1. Export requires deliberate human action
2. Evidence preserves document hash, page, offsets, retrieval scores, model/version metadata
3. No outbound inference traffic by default
4. Model output is untrusted data — it can only propose, never commit
5. Agents are proposal-only
6. Every operation is recorded in the append-only ledger
7. Determinism gate: identical input → identical output, test-enforced
8. Content-hash gating on the Evidence Graph — no silent rewrites of what was said

## Inference sovereignty ladder (ADR 006)

| Level | Runtime | Behavior |
|-------|---------|----------|
| 1 | Local Ollama | Canonical. Default for all inference |
| 2 | Other local runtimes | Allowed, flagged |
| 3 | External APIs | Opt-in only. `sovereignty_crossed=True` logged in the ledger |

## Corpus privacy

The first corpus is personal (a memorial reconstruction). `corpus/sources/` is gitignored; the deployed artifact contains only compiled claims and evidence quotes — no full source documents.

## Project layout

```
engine/          Core engine — compiler, stores, policy, inference, CLI
agents/          8 proposal-only agents + AgentRunner
artifact/        Artifact IR schema + Next.js static frontend
adr/             11 Architecture Decision Records
corpus/          Corpus sources (gitignored)
dist/            Built artifact IR (gitignored)
docs/            Documentation + screenshots
skills/          Agent skill files
tests/           108 tests
```

## Tests

```bash
DATABASE_URL=postgresql+asyncpg://ganymede:ganymede@localhost:5432/ganymede \
  python -m pytest tests/ -v
```

**108/108 passing** — stores, lifecycle, policy, agents, inference, artifact compiler, investigations, confidence, contradictions, gates.

## Documentation

- `GANYMEDE_2_SPEC.md` — full specification
- `adr/` — 11 Architecture Decision Records
- `SKILL.md` — Hermes agent operating instructions

## Prior art

- [Ganymede 1.x](https://github.com/kliewerdaniel/ganymede) — hybrid retrieval, verifier architecture, matter isolation
- [Hermes Atlas](https://github.com/kliewerdaniel/hermes-atlas) — claim lifecycle, evidence ledger, contradictions, determinism gate, confidence scoring

## Status

Phases 1–11 complete. All 11 ADRs implemented. 108/108 tests passing. Static artifact builds and deploys to Vercel.

## License

TBD.
