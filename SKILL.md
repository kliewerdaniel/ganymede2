# Hermes Agent Operating Instructions — Ganymede 2.0

This document tells an AI agent (Hermes) how to work in this repository. It is part of the repo's documentation, not a general prompt.

## Project identity

- **Project name:** Ganymede 2.0
- **Working category:** Sovereign epistemic compiler — local-first, incrementally-compiled, falsifiable knowledge system
- **North-star sentence:** Ingest a corpus, produce a deterministic claim graph, and generate inspectable artifacts showing what the system knows, what it thinks it can establish, what it can't, and where every proposition traces back to.
- **Repo slug:** `ganymede2`

## Build philosophy

- **Documentation first.** No implementation code is written until the relevant specification, ADR, and benchmark design exist. The documentation phase produces the substance; code implements it.
- **One corpus, many views.** The product wins through a reliable, reviewable path from corpus to claim graph to inspectable artifact.
- **Test coverage is the primary done metric.** A successful milestone is not "we added another 100 tests" — it is "we discovered and characterized a previously implicit semantic boundary."
- **Counterexamples are first-class research artifacts.** When something fails, preserve the failure case.

## Repository conventions

- ADRs live in `adr/`. Every material technical decision gets an ADR before implementation. Use `adr/000-template.md` as the template.
- The specification lives in `GANYMEDE_2_SPEC.md`. Version it. The benchmark, corpus rules, and non-goals are part of the spec.
- Agent skill files live in `skills/`. Each agent role has a skill file describing its responsibilities, inputs, outputs, and constraints.
- Decisions that are not architectural go in `decisions/`.
- Weekly scorecards live in `plans/`.

## Trust constraints (non-negotiable)

1. **Export:** Every external artifact requires a deliberate human action and carries an AI-draft label.
2. **Evidence:** Answers preserve document hash, page, offsets, retrieval scores, and model/version metadata.
3. **Egress:** No telemetry or inference traffic leaves the deployment unless the customer enables it.
4. **Tenant:** No shared application database or vector index between customers.
5. **Matter:** Authorization filters retrieval before any prompt is assembled.
6. **Model:** Model output is untrusted data; it cannot grant itself tools or permissions.
7. **Agent:** Agents are proposal-only; they cannot directly mutate epistemic state.
8. **Ledger:** Every operation affecting epistemic state is recorded in the append-only ledger.

Violating any of these without an ADR is a defect.

## Epistemic principles

- **Epistemic engine vs. agent system are strictly separated.** Ganymede is not an autonomous agent. Agents propose typed operations; Ganymede's policy layer evaluates them.
- **The fundamental object is a Claim, not a document or chunk.** Status is a pure function of evidence.
- **Corpus is immutable infrastructure.** Raw objects stay recoverable; derived representations regenerate.
- **LLM reasoning only enters after deterministic stages.** The system runs without a model.
- **Negative knowledge is first-class.** Distinguish UNRESOLVED, INSUFFICIENT, CONTRADICTED, RETRACTED — these are different epistemic states, not variations of "no answer."

## Quality gates

| Gate | Minimum target | How measured |
|------|---------------|-------------|
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

## Two-store separation

The **Evidence Graph** (immutable, append-only) and the **Epistemic Graph** (versioned, revisable) are physically distinct stores. The Epistemic Graph references the Evidence Graph but never mutates it. See ADR 001.

## Claim lifecycle

8-state superset: `UNEXAMINED` → `SUPPORTED` → `VALIDATED` → `CONTESTED` → `CONTRADICTED` → `INSUFFICIENT` → `UNRESOLVED` → `RETRACTED` → `SUPERSEDED`. Status is a pure function of evidence. History is never dropped. See ADR 002.

## Inference sovereignty

Local Ollama is canonical. Other local runtimes are acceptable. External providers are dev accelerators only, never invisible. Every inference event is logged. See ADR 006.

## Agent authority

Agents propose typed operations; the policy layer evaluates and commits. No agent can directly mutate the Evidence Graph or Epistemic Graph. See ADR 007.

## Epistemic ledger

Every operation affecting epistemic state is recorded in an append-only DAG. Events are never overwritten or deleted. See ADR 008.

## Artifact compiler

Epistemic Graph → Artifact IR (JSON) → Next.js project → Static export. Multiple simultaneous views. Bidirectional traversal. See ADR 009.

## Deployment boundary

Local engine (private, never exposed) + static artifact (optionally hosted on Vercel). See ADR 010.

## Prior art

- **Ganymede 1.x** (kliewerdaniel/ganymede): Hybrid retrieval, verifier architecture, matter isolation, trust constraints — all adopted.
- **Hermes Atlas** (kliewerdaniel/hermes-atlas): Claim lifecycle, evidence ledger, contradictions as first-class nodes, determinism gate, confidence scoring, compile-time extraction, delta recompilation, explain command, Popper falsifiability canary — all adopted and extended.
- **Compile-time AI pattern** (k8s-docs-compiler, sovereign-knowledge-compiler, scientific-question-compiler, Popper): Reasoning happens once at build time into a static deterministic artifact, queried at runtime with no further LLM calls, deployed as a Next.js static export to Vercel while the corpus/compute stays local — followed.

## What to read first

1. `GANYMEDE_2_SPEC.md` — the full specification
2. `adr/001-two-store-separation.md` — the foundational architectural decision
3. `adr/002-claim-lifecycle.md` — the state machine at the heart of the system
4. `adr/003-ingestion-compiler.md` — how sources become claims
5. `adr/006-inference-sovereignty.md` — how inference is used safely
6. `adr/007-agent-authority.md` — how agents interact with the system
7. `skills/` — agent skill files for implementation guidance
