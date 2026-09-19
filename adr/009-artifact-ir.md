# ADR 009: Artifact IR — compilation pipeline and view schema

**Status:** Accepted
**Date:** September 2026
**Deciders:** Conrad (Daniel Kliewer)
**Review trigger:** Before Phase 7 implementation begins, or when a new view or intermediate is proposed.

---

## Context

Ganymede 2.0's artifact compiler must transform the Epistemic Graph into inspectable artifacts: a Next.js static export (Vercel) with multiple views, simpler intermediates (knowledge graphs, narratives, dossiers), and bidirectional traversal. The question is how to structure the compilation pipeline and what the intermediate representation (IR) looks like.

Atlas compiles to a JSON store + `atlas explain` CLI output. Ganymede 1.x serves a web SPA from the API. The prompt calls for a layered approach: Epistemic Graph → Artifact IR → Next.js project → Static export, with simpler intermediates building into the artifact.

---

## Decision

Use a **two-phase artifact compiler** that first produces a JSON-based Artifact IR, then compiles that IR into a Next.js project that can be statically exported to Vercel.

### Phase 1: Epistemic Graph → Artifact IR

```python
@dataclass
class ArtifactIR:
    version: str                     # semantic version of the IR schema
    compiled_at: float
    compiler_version: str
    policy_version: str
    corpus_fingerprint: str          # fingerprint of the Evidence Graph state

    claims: list[ClaimExport]        # all claims with status, confidence, evidence refs
    evidence_index: list[EvidenceExport]  # evidence units referenced by claims
    entity_index: list[EntityExport] # entities mentioned in claims
    contradictions: list[ContradictionExport]
    investigations: list[InvestigationExport]
    provenance_index: list[SourceExport]  # sources referenced by evidence

    views: ViewIndex                 # pre-computed view data
    intermediates: IntermediateIndex  # pre-computed intermediate artifacts
```

### Phase 2: Artifact IR → Next.js project

```
Artifact IR → pages/ → components/ → public/ → Next.js build → Static export
```

### View schema

Each view is a pre-computed slice of the Artifact IR, optimized for rendering:

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

- **Claim → Evidence**: Each claim card links to its evidence units. Each evidence unit shows the source, offset, quote, and parser version.
- **Evidence → Downstream Claims**: Each evidence unit shows which claims depend on it. Removing this evidence would retract/supercede these claims.

### Simpler intermediates

These are pre-compiled and included in the artifact:

| Intermediate | Format | Purpose |
|-------------|--------|---------|
| Knowledge graph | JSON (d3.js compatible) | Entity co-occurrence + claim relationships |
| Narrative document | Markdown | Full prose narrative, ready for export |
| Character dossier | Markdown + JSON | Per-entity summary: claims, evidence, contradictions |
| Established facts | JSON | High-confidence claims, queryable |
| Timeline | JSON (chronology.js compatible) | Chronological event sequence |
| Contradiction report | Markdown | Unresolved tensions, both sides |
| Source inventory | JSON | Corpus coverage map, source metadata |

### Artifact determinism

- The Artifact IR is a pure function of the Epistemic Graph state.
- Identical Epistemic Graph → identical Artifact IR (byte-identical).
- The `corpus_fingerprint` field enables quick comparison between artifact versions.

### Deployment

```
┌──────────────────────────────────────────┐
│  Vercel (static export)                  │
│  ─ Next.js artifact                      │
│  ─ Multi-view UI                         │
│  ─ Bidirectional traversal               │
│  ─ Simpler intermediates                 │
└──────────────────────────────────────────┘
              │
              │ deploy (push/export)
              │
┌──────────────────────────────────────────┐
│  Local Ganymede Engine                   │
│  ─ PostgreSQL + pgvector                 │
│  ─ Evidence Graph store                  │
│  ─ Epistemic Graph store                 │
│  ─ Inference providers                   │
│  ─ Artifact compiler                     │
└──────────────────────────────────────────┘
```

---

## Consequences

**Enables:**
- **Multiple interfaces**: the same Epistemic Graph can be viewed as narrative, evidence browser, claim graph, chronology, etc.
- **Static export**: Vercel-hosted artifact is fast, cacheable, and doesn't expose the engine
- **Deterministic artifacts**: identical inputs produce identical outputs
- **Extensibility**: new views and intermediates can be added without changing the engine

**Costs:**
- Two-phase compilation adds complexity
- Next.js project template must be maintained
- Static export means the artifact is read-only (no query-time inference)

**Hardens:**
- The "artifact compiler produces a versioned manifest" principle
- The "Vercel is a distribution target, never the home" principle
- The "epistemic reproducibility" principle (artifacts are deterministic)

---

## Alternatives considered

### Query-time rendering (Ganymede 1.x model)
Rejected. Ganymede 1.x renders the SPA at query time from the API. This adds latency and requires the engine to be running for the artifact to be viewable. Static export is faster and more reliable.

### Single-page artifact (no views)
Rejected. The prompt explicitly calls for multiple simultaneous views. A single page would force the user to choose one perspective.

### Direct Next.js generation (no IR)
Rejected. The IR layer enables: (a) deterministic comparison between artifacts, (b) multiple output formats (Next.js, Markdown, JSON), (c) caching and reuse of intermediate results.

---

## References

- Ganymede 2.0 SPEC.md §9 (Artifact compiler)
- Ganymede 1.x `web/index.html` (SPA pattern — what we're evolving from)
- Atlas `explain.py` (claim export — what we're extending to a full artifact IR)
