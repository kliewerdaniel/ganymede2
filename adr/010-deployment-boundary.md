# ADR 010: Deployment boundary — Next.js static export over local engine

**Status:** Accepted
**Date:** September 2026
**Deciders:** Conrad (Daniel Kliewer)
**Review trigger:** Before Phase 8 implementation begins, or when the deployment model changes.

---

## Context

Ganymede 2.0 has two distinct components: the epistemic engine (local, private, contains all corpus data and inference) and the artifact (static, viewable, potentially hosted). The question is how these components are deployed, how they communicate, and what the trust boundary is between them.

Ganymede 1.x uses Docker Compose (API + PostgreSQL + pgvector + Ollama) with a web SPA served from the API. The prompt calls for a Next.js static export to Vercel, with the engine remaining local.

---

## Decision

Use a **two-tier deployment model**: local engine (private, never exposed) and static artifact (optionally hosted).

### Local engine

```
┌──────────────────────────────────────────────────────────┐
│  Local machine / private server                          │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Ganymede Engine (Python)                          │  │
│  │  ─ Ingestion compiler                              │  │
│  │  ─ Evidence Graph store (PostgreSQL + pgvector)    │  │
│  │  ─ Epistemic Graph store (PostgreSQL)              │  │
│  │  ─ Lifecycle state machine                         │  │
│  │  ─ Confidence scoring                              │  │
│  │  ─ Contradiction detection                         │  │
│  │  ─ Epistemic ledger                                │  │
│  │  ─ Inference layer (Ollama, llama.cpp, etc.)       │  │
│  │  ─ Agent policy layer                              │  │
│  │  ─ Artifact compiler                               │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  PostgreSQL + pgvector                             │  │
│  │  ─ Evidence Graph tables                           │  │
│  │  ─ Epistemic Graph tables                          │  │
│  │  ─ Ledger events table                             │  │
│  │  ─ Embeddings (pgvector)                           │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Inference providers                               │  │
│  │  ─ Ollama (canonical)                              │  │
│  │  ─ llama.cpp, vllm (optional)                      │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

- The engine is **never exposed to the internet**.
- All corpus data, embeddings, claims, and ledger events stay local.
- The engine exposes a local API (e.g., `http://localhost:8000`) for the CLI and for artifact compilation.

### Static artifact

```
┌──────────────────────────────────────────────────────────┐
│  Vercel (or any static host)                            │
│                                                          │
│  ─ Next.js static export                                │
│  ─ Multi-view UI (Narrative, Evidence, Claim, etc.)     │
│  ─ Bidirectional traversal                              │
│  ─ Simpler intermediates (knowledge graphs, narratives) │
│  ─ No query-time inference                              │
│  ─ No corpus data (only compiled claims/evidence refs)  │
└──────────────────────────────────────────────────────────┘
```

- The artifact is a **compiled snapshot** of the Epistemic Graph at a point in time.
- It contains claim text, status, confidence, and evidence references (quotes, source names, offsets).
- It does **not** contain raw source text (only the quotes that support claims).
- It does **not** contain embeddings or model weights.
- It is **read-only** — no query-time inference, no user input, no mutation.

### Deployment pipeline

```
1. User runs: ganymede compile
   → Engine compiles corpus → Epistemic Graph → Artifact IR

2. User runs: ganymede artifact build
   → Artifact IR → Next.js project → Static export

3. User runs: ganymede artifact deploy
   → Static export → Vercel (or copy to any static host)
   → OR: ganymede artifact serve (local preview)
```

### Trust boundary

| Component | Contains raw corpus? | Contains inference? | Exposed to internet? |
|-----------|---------------------|--------------------|--------------------|
| Local engine | Yes | Yes (local only) | No |
| Static artifact | No (only quotes + claim text) | No | Yes (if deployed) |

- The static artifact is **not** a security boundary — it contains only what the user has chosen to compile and deploy.
- The local engine is the **only** place where raw corpus data and inference coexist.

### Configuration

```yaml
# config.yaml
deployment:
  engine:
    host: "localhost"
    port: 8000
    database_url: "postgresql://ganymede:ganymede@localhost:5432/ganymede"
    ollama_url: "http://localhost:11434"

  artifact:
    output_dir: "./dist"
    deploy_target: "vercel" | "local" | "s3"
    vercel:
      project_id: "..."
      team_id: "..."
      token_env: "VERCEL_TOKEN"
    local:
      serve_port: 3000
```

---

## Consequences

**Enables:**
- **Privacy**: raw corpus data never leaves the local machine
- **Performance**: static artifact is fast, cacheable, CDN-friendly
- **Reliability**: artifact is viewable even when the engine is offline
- **Multiple deployments**: the same engine can compile artifacts for different audiences (different views, different claim subsets)

**Costs:**
- Two deployment targets to maintain
- Deployment pipeline adds steps (compile → build → deploy)
- Static artifact is a snapshot, not live (must be recompiled to reflect new corpus data)

**Hardens:**
- The "Vercel is a distribution target, never the home" principle
- The "everything exportable and locally reconstructable" principle
- The "private by architecture" trust constraint (from Ganymede 1.x)

---

## Alternatives considered

### Docker Compose (Ganymede 1.x model)
Rejected for the artifact. Docker Compose is appropriate for the engine (local deployment), but the artifact should be a static export that can be hosted anywhere, not a containerized web app.

### Server-rendered Next.js (no static export)
Rejected. Server-rendered Next.js requires a running server, which means the engine must be exposed or duplicated. Static export is simpler, faster, and more secure.

### IPFS / decentralized storage
Rejected for MVP. Static export to Vercel or any static host is sufficient. IPFS adds complexity without a clear benefit at this stage.

---

## References

- Ganymede 2.0 SPEC.md §10 (Deployment boundary)
- Ganymede 1.x `docker-compose.yml` (Docker deployment — what we're evolving from)
- Vercel documentation: https://vercel.com/docs
