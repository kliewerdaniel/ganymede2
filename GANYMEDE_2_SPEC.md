# Ganymede 2.0 — Specification

**Version:** 0.1 (draft)
**Date:** September 2026
**Status:** Draft — pending Conrad review and approval

---

## 1. System identity

- **Name:** `ganymede2`
- **Category:** Sovereign epistemic compiler — local-first, incrementally-compiled, falsifiable knowledge system
- **North star:** Ingest a corpus, produce a deterministic claim graph, and generate inspectable artifacts showing what the system knows, what it thinks it can establish, what it can't, and where every proposition traces back to.
- **Domain:** General-purpose epistemic compiler; litigation is one function among many (research, biography, investigative journalism, knowledge management)
- **First corpus:** A realistic portrayal of Chris (the user's late brother) — reconstruction as a MODEL, never canonical Chris, never fabrication of real life
- **Success criteria:** Not "produce a narrative" but "ingest a real corpus, produce a deterministic corpus manifest, extract a first claim graph, and generate an inspectable artifact showing what the system knows, what it thinks it can establish, what it can't, and where every proposition traces back to"

---

## 2. Architectural principles

1. **Epistemic engine vs. agent system are strictly separated.** Ganymede itself is not an autonomous agent — it's the deterministic/semi-deterministic substrate. Agents propose typed operations; Ganymede's policy layer records and evaluates them. The agent must never be both investigator and judge of its own claims.

2. **The fundamental object is a Claim, not a document or chunk.** Status is a pure function of evidence. Status is never boolean — use a state machine with 8 states.

3. **Corpus is immutable infrastructure.** Every source gets content hash, source ID, ingestion timestamp, parser version, origin metadata, normalization version. Raw objects stay recoverable; derived representations regenerate.

4. **LLM reasoning only enters after deterministic stages.** The system runs without a model. Model refinement is an optional enhancement, not a requirement.

5. **Retrieval is an access mechanism, not the epistemic mechanism.** Retrieve claims, evidence chains, entities, events, contradictions, source clusters, temporal neighborhoods, prior investigations — not just top-k chunks.

6. **Evidence Graph vs. Epistemic Graph, kept distinct.** Evidence Graph = what exists in the corpus (historical, immutable). Epistemic Graph = what the system currently believes can be inferred from it (interpretation, versioned, revisable).

7. **Negative knowledge is first-class.** Distinguish "no evidence found" vs. "evidence searched, found insufficient" vs. "sources directly contradict this" vs. "supporting evidence removed."

8. **Append-only Epistemic Ledger.** Every operation affecting epistemic state is recorded. History is a DAG, never overwritten.

9. **Agent-agnostic with skill files.** The agent system is integrated from the beginning, with skill files to aid agents. Designed to be agent-agnostic.

10. **Epistemic reproducibility.** "This claim was SUPPORTED under corpus version A, parser version B, inference provider C, epistemic policy D."

---

## 3. Architecture overview

```
┌─────────────────────────────────────────────────────────────┐
│                    EXPOSED LAYER                              │
│  Next.js static export (Vercel)                              │
│  Multi-view: Narrative / Evidence / Claim / Chronology /     │
│              Contradiction / Provenance / Investigation      │
│  Simpler intermediates: knowledge graphs, narratives,        │
│              dossiers, timelines, contradiction reports      │
└──────────────────────────┬──────────────────────────────────┘
                           │ compiled artifact (JSON IR)
┌──────────────────────────▼──────────────────────────────────┐
│                  EPISTEMIC ENGINE (local)                    │
│  ┌─────────────────────┐  ┌──────────────────────────────┐  │
│  │  EVIDENCE GRAPH      │  │  EPISTEMIC GRAPH             │  │
│  │  (immutable store)   │◄─┤  (versioned store)           │  │
│  │  sources, extractions│  │  claims, confidence, status, │  │
│  │  evidence spans,     │  │  derived_from, investigations│  │
│  │  contradictions      │  │  ledger events               │  │
│  └─────────────────────┘  └──────────────────────────────┘  │
│            ▲                        ▲                       │
│            │                        │                       │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  INGESTION COMPILER (deterministic, compile-time)      │  │
│  │  acquisition → canonicalization → structural parsing   │  │
│  │  → evidence unit creation → semantic extraction        │  │
│  │  → claim graph construction                            │  │
│  └────────────────────────────────────────────────────────┘  │
│            ▲                        ▲                       │
│            │                        │                       │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  INFERENCE LAYER (optional refinement)                 │  │
│  │  LLM verifier / claim refinement / narrative synthesis │  │
│  │  (sovereignty-ranked: local → external)                │  │
│  └────────────────────────────────────────────────────────┘  │
│            ▲                        ▲                       │
│            │                        │                       │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  AGENT POLICY LAYER (proposal-only)                    │  │
│  │  agents propose typed operations; policy evaluates     │  │
│  │  against schema + epistemic policy before commit       │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Two-store separation

| Aspect | Evidence Graph | Epistemic Graph |
|--------|---------------|-----------------|
| **Nature** | Historical, immutable | Interpretation, versioned, revisable |
| **Contents** | sources, extractions, evidence spans, source checksums, contradiction records | claims, confidence scores, status, derived_from links, investigation history, ledger events |
| **Mutability** | Append-only. Raw objects never deleted (sources may be marked `removed` but record persists). Extractions are immutable once written. | Status is a pure function of evidence, recomputed each compile. History is appended, never overwritten. Claims are never deleted — only transitioned to RETRACTED/SUPERSEDED. |
| **Provenance model** | Source ID + char offset + parser version + content hash + normalization version | Claim ID + evidence refs + compiler version + policy version + parent event IDs |
| **Change detection** | Content-hash gated. Identical source + identical parser + identical checksum = no write. | Evidence-change gated. Claims whose evidence fingerprint is unchanged keep their status. Claims with new/removed evidence are re-evaluated. |
| **Storage** | PostgreSQL (JSONB) | PostgreSQL (JSONB) |
| **Question it answers** | "What did the corpus contain?" | "What can we legitimately establish from it?" |

**Communication:** One direction only — Evidence Graph → Epistemic Graph. The Epistemic Graph holds references (evidence IDs, source IDs) into the Evidence Graph, never the reverse.

---

## 5. Claim lifecycle

### States

| State | Meaning | Evidence condition |
|-------|---------|-------------------|
| `UNEXAMINED` | Claim extracted, not yet evaluated | No evaluation run against this claim |
| `SUPPORTED` | Evidence supports this claim | Supporting evidence above confidence threshold |
| `VALIDATED` | Multiple independent sources corroborate | ≥2 independent sources, high confidence, no strong contradiction |
| `CONTESTED` | Both supporting and contradicting evidence exist | Mixed evidence with both sides above noise floor |
| `CONTRADICTED` | Evidence directly contradicts this claim | Contradicting evidence dominates supporting evidence |
| `INSUFFICIENT` | Some evidence exists but below support threshold | Weak, sparse, or low-reliability evidence |
| `UNRESOLVED` | No supporting evidence found after deliberate search | Search was conducted; no evidence located |
| `RETRACTED` | Was SUPPORTED/VALIDATED; supporting evidence was removed or invalidated | DELETE-driven: the evidence that supported this claim is gone |
| `SUPERSEDED` | Replaced by a more precise claim | Newer claim subsumes this one |

### Invariants

1. **No-op stability** — A no-op recompile (no evidence changed) does not move any claim's state.
2. **No illegal skips** — Every written state is the one evidence dictates. The state machine is a pure function of evidence, not of prior state.
3. **Invalidations are justified** — A claim becomes `RETRACTED` ONLY when its supporting evidence is removed or directly contradicted. The claim record and its history are retained, never silently dropped.
4. **Contradictions are preserved** — A contradicted claim pair survives delta recompiles without being dropped.
5. **UNRESOLVED is distinct** — A claim that was searched for but not found is `UNRESOLVED`, not `INSUFFICIENT`. Searching is a deliberate act, recorded in the ledger.
6. **History is never dropped** — Every state transition is appended to the claim's `history[]` list.

---

## 6. Ingestion compiler

### Stages

```
Stage 1: ACQUISITION
  → Fetch source (file, URL, API, export)
  → Record: source_id, origin, fetched_at, raw_checksum
  → Validate: file size, MIME type, encoding
  → On failure: mark source as `failed` with visible error

Stage 2: CANONICALIZATION
  → Common envelope across formats:
    { id, type, text, url, domain, author, fetched_at,
      checksum, parser_version, normalization_version, metadata }
  → Formats: ChatGPT exports, Reddit exports, documents (PDF/DOCX),
    images (OCR), code repos, notes, multimedia transcripts

Stage 3: STRUCTURAL PARSING
  → Format-specific decomposition:
    conversations → turns
    posts → post/comment
    repos → files/commits
    docs → pages/passages
  → Output: structural units with provenance (source_id, offset, span)

Stage 4: EVIDENCE UNIT CREATION
  → Smallest provenance-bearing object
  → Fields: evidence_id, source_id, claim_id, structural_unit_id,
    domain, author, stance, quote, offset, timestamp, reliability,
    source_checksum, parser_version, needs_revalidation, stale_evidence

Stage 5: SEMANTIC EXTRACTION (deterministic + optional model)
  → Deterministic: sentence splitting, assertion-cue detection,
    entity extraction, co-mention relationships
  → Optional model: claim refinement, relationship proposal
  → Gated: absent model → deterministic layer stands alone

Stage 6: CLAIM GRAPH CONSTRUCTION
  → Merge extractions across sources
  → Build entity co-occurrence graph
  → Detect contradictions (polarity + topical overlap)
  → Compute confidence scores (independence, reliability, recency, corroboration)
  → Assign initial lifecycle status
  → Write to Evidence Graph store
  → Write proposed claims to Epistemic Graph store
```

### Change detection

- Each stage's output is content-hash gated. Identical input + identical parser = no write.
- The changelog stays silent on unchanged records.
- Staleness: if a source's checksum changes after extraction, the affected evidence units are flagged `needs_revalidation=True`.

---

## 7. Inference sovereignty ladder

| Priority | Provider category | Examples | Sovereignty boundary |
|----------|------------------|----------|---------------------|
| 1 (canonical) | Local Ollama | qwen3:8b, qwen3:4b, nomic-embed-text | None (local) |
| 2 | Other local runtimes | llama.cpp, vllm, MLX | None (local) |
| 3 | Explicitly-marked external | OpenAI API, Anthropic API, etc. | Crossed (logged) |

Every inference event logs: provider, model, version, params, prompt-contract version, input/output hashes, latency, sovereignty boundary crossed (Y/N).

---

## 8. Agent system

### Principle

Agents propose typed operations; Ganymede's policy layer records and evaluates them. The agent is never both investigator and judge of its own claims.

### Agent roles (proposal-only)

| Agent | Proposes | Never does |
|-------|----------|------------|
| `CorpusCartographer` | New sources, corpus structure, gap identification | Directly ingest sources |
| `Extractor` | Evidence units, claims, relationships | Directly write to Evidence Graph |
| `Researcher` | External lookups (scoped, logged) | Directly add external evidence |
| `EvidenceAnalyst` | Evidence evaluations, reliability scores | Directly change evidence records |
| `TemporalAnalyst` | Temporal orderings, event sequences | Directly modify claims |
| `ContradictionAnalyst` | Contradiction detections, resolutions | Directly resolve contradictions |
| `SynthesisAgent` | Claim merges, narrative structures | Directly create artifacts |
| `ArtifactCompiler` | Artifact views, narrative orderings | Directly deploy artifacts |

### Policy layer evaluation

1. **Schema validity** — Does the proposal conform to the schema?
2. **Epistemic policy compliance** — Does the proposal violate any epistemic invariants?
3. **Sovereignty boundary** — Was external inference used? Is it logged?
4. **Conflict detection** — Does the proposal conflict with existing claims?
5. **Authority scope** — Is the agent authorized for this operation?

### Evaluation outcomes

| Outcome | Meaning | Action |
|---------|---------|--------|
| `accepted` | Proposal is valid and policy-compliant | Commit to Epistemic Graph, record in ledger |
| `rejected` | Proposal violates policy | Record rejection in ledger, return to agent with reason |
| `needs_review` | Proposal is valid but conflicts with existing claims | Queue for human review, record in ledger |
| `deferred` | Proposal requires information not yet available | Queue for re-evaluation when information arrives |

---

## 9. Epistemic ledger

### Event types

| Category | Event types |
|----------|-------------|
| Corpus | `SOURCE_INGESTED`, `SOURCE_REMOVED`, `SOURCE_RESTORED` |
| Extraction | `EVIDENCE_EXTRACTED`, `EVIDENCE_INVALIDATED`, `EVIDENCE_STALE` |
| Claims | `CLAIM_PROPOSED`, `CLAIM_SUPPORTED`, `CLAIM_CONTESTED`, `CLAIM_CONTRADICTED`, `CLAIM_RETRACTED`, `CLAIM_SUPERSEDED`, `CLAIM_VALIDATED`, `CLAIM_REOPENED` |
| Contradictions | `CONTRADICTION_DETECTED`, `CONTRADICTION_RESOLVED`, `CONTRADICTION_ACCEPTED` |
| Investigations | `INVESTIGATION_STARTED`, `INVESTIGATION_COMPLETED`, `INVESTIGATION_ABANDONED` |
| Inference | `MODEL_INVOKED`, `MODEL_SKIPPED`, `PROVIDER_SELECTED` |
| Artifacts | `ARTIFACT_COMPILED`, `ARTIFACT_DEPLOYED`, `ARTIFACT_RETRACTED` |
| System | `COMPILE_STARTED`, `COMPILE_COMPLETED`, `GATE_PASSED`, `GATE_FAILED` |

### Properties

- Append-only. Never overwritten, never deleted.
- Event IDs are content-hash derived (deterministic).
- Forms a DAG (parent_event_id links).
- Every state change, every agent proposal, every inference event is recorded.

---

## 10. Artifact compiler

### Pipeline

```
Epistemic Graph → Artifact IR (JSON) → Next.js project → Static export
```

### Views

| View | Content | Primary query |
|------|---------|---------------|
| **Narrative** | Prose synthesis of SUPPORTED/VALIDATED claims, ordered by confidence | "What does Ganymede establish?" |
| **Evidence** | Evidence units grouped by source, with claim back-links | "What evidence supports this?" |
| **Claim** | All claims, filterable by status, confidence, entity | "What claims exist and what's their status?" |
| **Chronology** | Temporal ordering of events/claims by timestamp | "What happened when?" |
| **Contradiction** | Contradiction pairs, both sides visible, resolution status | "What tensions exist?" |
| **Provenance** | Source-to-claim graph, full traceability | "Where does this come from?" |
| **Investigation** | Investigation history, open questions, abandoned inquiries | "What was asked and what was found?" |

### Bidirectional traversal

- **Claim → Evidence**: Each claim card links to its evidence units.
- **Evidence → Downstream Claims**: Each evidence unit shows which claims depend on it.

### Simpler intermediates

| Intermediate | Format | Purpose |
|-------------|--------|---------|
| Knowledge graph | JSON (d3.js compatible) | Entity co-occurrence + claim relationships |
| Narrative document | Markdown | Full prose narrative, ready for export |
| Character dossier | Markdown + JSON | Per-entity summary: claims, evidence, contradictions |
| Established facts | JSON | High-confidence claims, queryable |
| Timeline | JSON (chronology.js compatible) | Chronological event sequence |
| Contradiction report | Markdown | Unresolved tensions, both sides |
| Source inventory | JSON | Corpus coverage map, source metadata |

---

## 11. Negative knowledge

| State | Meaning | Distinct from |
|-------|---------|---------------|
| `UNRESOLVED` | Search was conducted; no evidence found | "No answer" — searching is a deliberate act |
| `INSUFFICIENT` | Evidence found but below support threshold | "Weak answer" — there's something, but not enough |
| `CONTRADICTED` | Evidence directly contradicts this claim | "Opposite answer" — the corpus says the opposite |
| `RETRACTED` | Evidence was removed or invalidated | "Used to know this" — the supporting evidence is gone |

---

## 12. Quality gates

| Gate | Target | How measured |
|------|--------|-------------|
| Source recall | ≥80% | Gold set of answerable questions |
| Answer-absent precision | 100% | Gold set of unanswerable questions |
| Negative knowledge precision | 100% | Correct distinction between UNRESOLVED/INSUFFICIENT/CONTRADICTED |
| Matter isolation | 100% | Cross-matter test suite |
| Claim extraction precision | ≥0.667 | Hand-annotated gold set |
| Claim extraction recall | ≥1.000 | Hand-annotated gold set |
| Provenance completeness | 1.000 | Every claim's evidence resolves to real source + span |
| Contradiction preservation | 1.000 | Contradicted claims survive delta recompiles |
| Lifecycle correctness | 1.000 | Status matches evidence-derived gold |
| Determinism | Full-compile identity + delta isolation | `ganymede gate` |
| Epistemic regression | 0 silent changes | Previously-supported claims don't silently lose support |

---

## 13. Repo structure

```
ganymede2/
├── README.md
├── SKILL.md                    # Hermes agent operating instructions
├── GANYMEDE_2_SPEC.md          # This spec
├── adr/                        # Architecture Decision Records
│   ├── 000-template.md
│   ├── 001-two-store-separation.md
│   ├── 002-claim-lifecycle.md
│   ├── 003-ingestion-compiler.md
│   ├── 004-evidence-graph.md
│   ├── 005-epistemic-graph.md
│   ├── 006-inference-sovereignty.md
│   ├── 007-agent-authority.md
│   ├── 008-epistemic-ledger.md
│   ├── 009-artifact-ir.md
│   ├── 010-deployment-boundary.md
│   └── 011-negative-knowledge.md
├── engine/                     # Epistemic engine (Python)
│   ├── __init__.py
│   ├── compiler.py             # Ingestion compiler (deterministic stages)
│   ├── store_evidence.py       # Evidence Graph store (immutable)
│   ├── store_epistemic.py      # Epistemic Graph store (versioned)
│   ├── lifecycle.py            # Claim lifecycle state machine
│   ├── confidence.py           # Confidence scoring
│   ├── contradictions.py       # Contradiction detection
│   ├── ledger.py               # Epistemic ledger (append-only DAG)
│   ├── explain.py              # Bidirectional claim traversal
│   ├── extract.py              # Deterministic + optional model extraction
│   ├── graph.py                # Entity co-occurrence graph
│   ├── gate.py                 # Determinism + lifecycle gates
│   ├── inference.py            # Provider-agnostic inference layer
│   └── agent_policy.py         # Agent proposal evaluation
├── artifact/                   # Artifact compiler
│   ├── __init__.py
│   ├── compiler.py             # Epistemic Graph → Next.js IR
│   ├── views/                  # View generators
│   │   ├── narrative.py
│   │   ├── evidence.py
│   │   ├── claim.py
│   │   ├── chronology.py
│   │   ├── contradiction.py
│   │   ├── provenance.py
│   │   └── investigation.py
│   └── nextjs/                 # Next.js project template
│       ├── pages/
│       ├── components/
│       └── public/
├── agents/                     # Agent definitions (agent-agnostic)
│   ├── __init__.py
│   ├── proposals.py            # AgentProposal schema
│   ├── corpus_cartographer.py
│   ├── extractor.py
│   ├── researcher.py
│   ├── evidence_analyst.py
│   ├── temporal_analyst.py
│   ├── contradiction_analyst.py
│   ├── synthesis_agent.py
│   └── artifact_compiler.py
├── skills/                     # Agent skill files
│   ├── corpus-cartographer.md
│   ├── extractor.md
│   ├── researcher.md
│   ├── evidence-analyst.md
│   ├── temporal-analyst.md
│   ├── contradiction-analyst.md
│   ├── synthesis-agent.md
│   └── artifact-compiler.md
├── tests/
│   ├── test_compiler.py
│   ├── test_lifecycle.py
│   ├── test_confidence.py
│   ├── test_contradictions.py
│   ├── test_ledger.py
│   ├── test_explain.py
│   ├── test_gate.py
│   ├── test_agent_policy.py
│   ├── test_artifact_compiler.py
│   └── gold/                   # Gold sets
│       ├── answerable.json
│       ├── unanswerable.json
│       ├── isolation.json
│       └── claims.json
├── corpus/                     # Corpus storage (gitignored)
│   ├── sources/                # Raw source files
│   ├── evidence_graph/         # Evidence Graph store files
│   └── epistemic_graph/        # Epistemic Graph store files
├── docs/
│   ├── specification/
│   │   └── product-contract.md
│   ├── architecture/
│   │   ├── trust-boundaries.md
│   │   └── data-flow.md
│   └── adr/                    # Mirror of adr/ for GitHub rendering
├── plans/
│   └── weekly-scorecard.md
├── decisions/
├── docker-compose.yml          # Engine + PostgreSQL + pgvector + Ollama
├── pyproject.toml
└── .gitignore
```

---

## 14. Phasing

| Phase | Focus | Done when |
|-------|-------|-----------|
| 1 | Archaeology + spec freeze | Ganymede 1.x audited, Atlas reconciled, spec approved |
| 2 | Canonical corpus + Evidence Graph | First corpus ingested, evidence units extracted, provenance complete |
| 3 | Claim + Epistemic Graph | Claims extracted, lifecycle assigned, confidence scored |
| 4 | Epistemic ledger + state machine | Ledger events recorded, lifecycle gates pass |
| 5 | Inference layer | Provider abstraction, sovereignty logging, optional refinement |
| 6 | Agent policy layer | Agents propose, policy evaluates, no silent mutation |
| 7 | Artifact IR | Epistemic Graph → JSON IR, multi-view compilation |
| 8 | First Next.js artifact | Static export, multiple views, bidirectional traversal |
| 9 | Narrative intermediates | Knowledge graphs, dossiers, timelines, contradiction reports |
| 10 | Autonomous investigation loop | Agents can propose and execute scoped investigations |

---

## 15. Trust constraints (non-negotiable)

1. **Export:** Every external artifact requires a deliberate human action and carries an AI-draft label.
2. **Evidence:** Answers preserve document hash, page, offsets, retrieval scores, and model/version metadata.
3. **Egress:** No telemetry or inference traffic leaves the deployment unless the customer enables it.
4. **Tenant:** No shared application database or vector index between customers.
5. **Matter:** Authorization filters retrieval before any prompt is assembled.
6. **Model:** Model output is untrusted data; it cannot grant itself tools or permissions.
7. **Agent:** Agents are proposal-only; they cannot directly mutate epistemic state.
8. **Ledger:** Every operation affecting epistemic state is recorded in the append-only ledger.

---

## 16. Prior art and reconciliation

### Ganymede 1.x

| Component | Status in Ganymede 2.0 |
|-----------|------------------------|
| Hybrid retrieval (FTS + vector, RRF) | Adopted as the retrieval mechanism |
| Verifier (LLM-as-judge) | Adopted as optional refinement layer |
| Matter isolation model | Adopted as the trust boundary |
| Sync/async endpoint split | Adopted as the compile-time/query-time split |
| Gold set discipline | Extended to claim-level metrics |
| Trust constraints | Carried forward verbatim |
| Docker Compose deployment | Adopted for the engine |

### Hermes Atlas

| Component | Status in Ganymede 2.0 |
|-----------|------------------------|
| Claim lifecycle (6-state) | Extended to 8-state superset |
| Evidence ledger | Adopted as the Evidence Graph model |
| Contradictions as first-class nodes | Adopted as-is |
| Determinism gate | Adopted as-is |
| Confidence scoring | Adopted as-is |
| Compile-time extraction | Adopted as Stage 5 of the ingestion compiler |
| Delta recompilation | Adopted as the change detection mechanism |
| `atlas explain` | Adopted as the bidirectional traversal UI |
| Popper falsifiability canary | Adopted as the quality gate |
| Single-store architecture | Diverged from (two-store separation) |
| Model-free by default | Adopted (inference is optional) |

### Compile-time AI pattern

The recurring pattern across Conrad's compile-time AI work (k8s-docs-compiler, sovereign-knowledge-compiler, scientific-question-compiler, Popper) is: reasoning happens once at build time into a static deterministic artifact, queried at runtime with no further LLM calls, deployed as a Next.js static export to Vercel while the corpus/compute stays local. Ganymede 2.0 follows this pattern: the ingestion compiler runs at compile time, the artifact is a static export, and the engine stays local.

---

## 17. Open questions (resolved)

| Question | Resolution |
|----------|------------|
| Repo name | `ganymede2` |
| Domain | General compiler, litigation one function |
| First corpus | Chris (reconstruction as model) |
| Database | PostgreSQL + pgvector |
| Claim lifecycle | 8-state superset |
| Store separation | Two real stores (Evidence + Epistemic) |
| Verifier | Optional refinement layer |
| Inference timing | Compile-time only |
| Artifact | Simpler intermediates → Next.js artifact |
| Deployment | Next.js static export over local engine |
| Agent system | Integrated from start, agent-agnostic |

---

## 18. ADRs

1. **ADR 001** — Two-store separation (Evidence Graph vs Epistemic Graph)
2. **ADR 002** — Claim lifecycle (8-state superset, invariants)
3. **ADR 003** — Ingestion compiler (deterministic stages, canonicalization)
4. **ADR 004** — Evidence Graph model (immutable, provenance-bearing)
5. **ADR 005** — Epistemic Graph model (versioned, revisable)
6. **ADR 006** — Inference sovereignty ladder (provider ranking, logging)
7. **ADR 007** — Agent authority model (proposal-only, policy evaluation)
8. **ADR 008** — Epistemic ledger (append-only DAG, event types)
9. **ADR 009** — Artifact IR (compilation pipeline, view schema)
10. **ADR 010** — Deployment boundary (Next.js static export, local engine)
11. **ADR 011** — Negative knowledge (first-class epistemic states)

---

**This specification is a draft.** It will be updated as the system is implemented and new constraints are discovered. All changes will be recorded in the epistemic ledger.
