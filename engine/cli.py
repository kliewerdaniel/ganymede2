"""CLI for Ganymede 2.0 — sovereign epistemic compiler."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(prog="ganymede", description="Ganymede 2.0 — sovereign epistemic compiler")
    subparsers = parser.add_subparsers(dest="command")

    # ingest
    ingest_parser = subparsers.add_parser("ingest", help="Ingest a corpus directory")
    ingest_parser.add_argument("corpus_dir", help="Path to corpus directory")
    ingest_parser.add_argument("--cycle", type=int, default=0, help="Compile cycle number")

    # compile
    compile_parser = subparsers.add_parser("compile", help="Compile corpus")
    compile_parser.add_argument("corpus_dir", help="Path to corpus directory")
    compile_parser.add_argument("--cycle", type=int, default=0, help="Compile cycle number")
    compile_parser.add_argument("--incremental", action="store_true", help="Incremental compile")

    # artifact
    artifact_parser = subparsers.add_parser("artifact", help="Manage artifacts")
    artifact_subparsers = artifact_parser.add_subparsers(dest="artifact_command")
    build_parser = artifact_subparsers.add_parser("build", help="Build artifact IR from database")
    build_parser.add_argument("--output", default="./dist", help="Output directory")
    serve_parser = artifact_subparsers.add_parser("serve", help="Serve artifact locally")
    serve_parser.add_argument("--port", type=int, default=3000, help="Port")

    # gate
    gate_parser = subparsers.add_parser("gate", help="Run quality gates")

    # investigate
    investigate_parser = subparsers.add_parser("investigate", help="Run investigation loop")
    investigate_parser.add_argument("--max-investigations", type=int, default=10, help="Max investigations to create")

    # agents
    agents_parser = subparsers.add_parser("agents", help="Run agent pipeline")
    agents_parser.add_argument("--agent", action="append", help="Specific agent to run (default: all)")

    # explain
    explain_parser = subparsers.add_parser("explain", help="Explain a claim")
    explain_parser.add_argument("claim_id", help="Claim ID")

    # status
    status_parser = subparsers.add_parser("status", help="Show corpus status")

    # refine
    refine_parser = subparsers.add_parser("refine", help="Optional model refinement (Stage 5)")
    refine_parser.add_argument("--model", default="qwen3:8b", help="Model to use")
    refine_parser.add_argument("--max-claims", type=int, default=10, help="Max claims to refine")
    refine_parser.add_argument(
        "--relationships", action="store_true",
        help="Also propose typed relationships from source texts",
    )
    voice_parser = subparsers.add_parser("classify-voices", help="Classify human claims into voices (Stage 5, model-derived)")
    voice_parser.add_argument("--model", default="qwen3:8b", help="Model to use")
    voice_parser.add_argument("--limit", type=int, default=100, help="Max claims to classify")
    voice_parser.add_argument("--voice", default="personal", help="Only classify claims for this voice run target (unused filter, kept for CLI symmetry)")
    voice_parser.add_argument("--status", default="SUPPORTED,VALIDATED", help="Comma-separated claim statuses to include")

    args = parser.parse_args()

    if args.command == "ingest":
        asyncio.run(_cmd_ingest(args))
    elif args.command == "compile":
        asyncio.run(_cmd_compile(args))
    elif args.command == "artifact":
        if args.artifact_command == "build":
            asyncio.run(_cmd_artifact_build(args))
        elif args.artifact_command == "serve":
            _cmd_artifact_serve(args)
        else:
            artifact_parser.print_help()
            sys.exit(1)
    elif args.command == "gate":
        asyncio.run(_cmd_gate(args))
    elif args.command == "explain":
        asyncio.run(_cmd_explain(args))
    elif args.command == "status":
        asyncio.run(_cmd_status(args))
    elif args.command == "refine":
        asyncio.run(_cmd_refine(args))
    elif args.command == "classify-voices":
        asyncio.run(_cmd_classify_voices(args))
    elif args.command == "investigate":
        asyncio.run(_cmd_investigate(args))
    elif args.command == "agents":
        asyncio.run(_cmd_agents(args))
    else:
        parser.print_help()
        sys.exit(1)


async def _cmd_ingest(args):
    from .compiler import Compiler
    from .database import create_tables

    print(f"Creating tables...")
    await create_tables()

    print(f"Ingesting corpus from {args.corpus_dir}...")
    compiler = Compiler()
    report = await compiler.compile_corpus_dir(args.corpus_dir, cycle=args.cycle)
    print(report)


async def _cmd_compile(args):
    from .compiler import Compiler
    from .database import create_tables

    print(f"Creating tables...")
    await create_tables()

    print(f"Compiling corpus from {args.corpus_dir}...")
    compiler = Compiler()
    if args.incremental:
        report = await compiler.compile_corpus_dir(args.corpus_dir, cycle=args.cycle)
    else:
        report = await compiler.compile_corpus_dir(args.corpus_dir, cycle=args.cycle)
    print(report)


async def _cmd_artifact_build(args):
    """Build Artifact IR from the database."""
    from .database import create_tables, get_session
    from .artifact_compiler import ArtifactCompiler
    from sqlalchemy import select
    from .database import ClaimRecord, EvidenceUnitRecord, SourceRecord, ContradictionRecord, InvestigationRecord
    import shutil

    await create_tables()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load all data from database
    async with get_session() as session:
        claims = [_row_to_dict(r) for r in (await session.execute(select(ClaimRecord))).scalars().all()]
        evidence = [_row_to_dict(r) for r in (await session.execute(select(EvidenceUnitRecord))).scalars().all()]
        sources = [_row_to_dict(r) for r in (await session.execute(select(SourceRecord))).scalars().all()]
        contradictions = [_row_to_dict(r) for r in (await session.execute(select(ContradictionRecord))).scalars().all()]
        investigations = [_row_to_dict(r) for r in (await session.execute(select(InvestigationRecord))).scalars().all()]

    # Entities live in the Evidence Graph store
    from .store_evidence import EvidenceGraphStore
    evidence_store = EvidenceGraphStore()
    entities = await evidence_store.get_entities(limit=5000)

    # Build artifact IR
    compiler = ArtifactCompiler(
        claims=claims,
        evidence=evidence,
        entities=entities,
        sources=sources,
        contradictions=contradictions,
        investigations=investigations,
    )

    # Scale-safe sharded artifact: small index + data/ shards
    summary = compiler.write_sharded_artifact(output_dir)
    print(json.dumps(summary, indent=2, default=str))
    print(f"\nSharded artifact written to {output_dir}")
    print(f"Fingerprint: {summary['fingerprint']}")

    # Also copy to Next.js public directory
    nextjs_public = Path(args.output).resolve().parent / "artifact" / "nextjs" / "public"
    if nextjs_public.exists():
        import shutil
        shutil.copytree(output_dir, nextjs_public, dirs_exist_ok=True)
        print(f"Copied to {nextjs_public}")
    else:
        print(f"Note: {nextjs_public} not found. Run from project root.")


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy row to a dict keyed by SQL column name.

    The class attribute name can differ from the SQL column name (e.g. the
    SQL column ``metadata`` is mapped to the attribute ``metadata_json``).
    ``Column.key`` defaults to the SQL name, so ``getattr(row, col.key)``
    resolves ``metadata`` to SQLAlchemy's class-level ``MetaData`` object —
    which json.dumps rejects as a circular reference. Walk
    ``mapper.column_attrs`` instead: each entry carries the true attribute
    key alongside its column.
    """
    from sqlalchemy import inspect as sa_inspect

    mapper = sa_inspect(row.__class__)
    result = {}
    for attr in mapper.column_attrs:
        col = attr.columns[0]
        result[col.name] = getattr(row, attr.key)
    return result


def _cmd_artifact_serve(args):
    import http.server
    import socketserver
    import os

    dist_dir = "./dist"
    if not os.path.exists(dist_dir):
        print(f"No artifact found. Run 'ganymede artifact build' first.")
        sys.exit(1)

    os.chdir(dist_dir)
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", args.port), handler) as httpd:
        print(f"Serving artifact at http://localhost:{args.port}")
        httpd.serve_forever()


async def _cmd_gate(args):
    from .gate import run_all_gates
    report = await run_all_gates()
    print(report)


async def _cmd_explain(args):
    from .store_epistemic import EpistemicGraphStore
    store = EpistemicGraphStore()
    claim = await store.get_claim(args.claim_id)
    if claim:
        print(json.dumps(claim, indent=2))
    else:
        print(f"Claim {args.claim_id} not found.")


async def _cmd_status(args):
    """Show corpus status summary."""
    from .database import create_tables, get_session
    from sqlalchemy import select, func
    from .database import ClaimRecord, SourceRecord, EvidenceUnitRecord, ContradictionRecord

    await create_tables()

    async with get_session() as session:
        source_count = (await session.execute(select(func.count(SourceRecord.id)))).scalar() or 0
        claim_count = (await session.execute(select(func.count(ClaimRecord.id)))).scalar() or 0
        evidence_count = (await session.execute(select(func.count(EvidenceUnitRecord.id)))).scalar() or 0
        contradiction_count = (await session.execute(select(func.count(ContradictionRecord.id)))).scalar() or 0

        status_counts = {}
        for status in ["UNEXAMINED", "SUPPORTED", "VALIDATED", "CONTESTED", "INSUFFICIENT", "UNRESOLVED", "RETRACTED", "SUPERSEDED"]:
            count = (await session.execute(
                select(func.count(ClaimRecord.id)).where(ClaimRecord.status == status)
            )).scalar()
            if count > 0:
                status_counts[status] = count

    print(f"\n{'='*50}")
    print(f"  Ganymede 2.0 — Corpus Status")
    print(f"{'='*50}")
    print(f"  Sources:       {source_count}")
    print(f"  Evidence:      {evidence_count}")
    print(f"  Claims:        {claim_count}")
    print(f"  Contradictions: {contradiction_count}")
    print(f"{'─'*50}")
    print(f"  Claims by status:")
    for status, count in status_counts.items():
        print(f"    {status:15s} {count}")
    print(f"{'='*50}\n")


async def _cmd_refine(args):
    """Optional model refinement pass (Stage 5) — gated on provider availability."""
    from .database import create_tables, get_session
    from .inference import select_provider, log_inference_event
    from .refine import RefinementTarget, refine_claims, propose_relationships
    from .store_epistemic import EpistemicGraphStore
    from sqlalchemy import select
    from .database import ClaimRecord, SourceRecord

    await create_tables()

    provider = select_provider()
    if provider is None:
        print("No inference provider available — deterministic layer stands alone.")
        print("(Start Ollama or configure a provider in config.yaml to enable refinement.)")
        return

    print(f"Provider: {provider.name} (sovereignty crossed: {provider.sovereignty_crossed})")
    print(f"Model:    {args.model}")

    store = EpistemicGraphStore()

    # Load claims + sources
    async with get_session() as session:
        claims = (await session.execute(select(ClaimRecord))).scalars().all()
        sources = (await session.execute(select(SourceRecord))).scalars().all()

    existing_claim_ids = [c.id for c in claims]

    # Claim refinement
    targets = [
        RefinementTarget(claim_id=c.id, text=c.text, quote=(c.text or "")[:400])
        for c in claims[: args.max_claims]
    ]
    print(f"\nRefining {len(targets)} claims...")
    report = refine_claims(
        targets, provider=provider, model=args.model,
        existing_claim_ids=existing_claim_ids,
    )
    print(f"  refined: {report.claims_refined}")
    print(f"  invalid model output rejected: {report.claims_rejected_invalid}")
    print(f"  accepted: {report.proposals_accepted} | needs_review: {report.proposals_needs_review} | rejected: {report.proposals_rejected}")
    if report.errors:
        print(f"  errors: {len(report.errors)}")
        for e in report.errors[:3]:
            print(f"    - {e[:120]}")

    # Persist MODEL_INVOKED ledger events
    for event in report.inference_events:
        await store.put_ledger_event(event)
    print(f"  ledger events: {len(report.inference_events)}")

    # Relationship proposals
    if args.relationships:
        texts = [{"source_id": s.id, "text": s.text[:2000]} for s in sources[:10]]
        print(f"\nProposing relationships from {len(texts)} sources...")
        rel_report = propose_relationships(texts, provider=provider, model=args.model)
        print(f"  proposed: {rel_report.relationships_proposed}")
        print(f"  invalid rejected: {rel_report.relationships_rejected_invalid}")
        print(f"  accepted: {rel_report.proposals_accepted} | needs_review: {rel_report.proposals_needs_review} | rejected: {rel_report.proposals_rejected}")
        for event in rel_report.inference_events:
            await store.put_ledger_event(event)
        print(f"  ledger events: {len(rel_report.inference_events)}")
        if rel_report.errors:
            print(f"  errors: {len(rel_report.errors)}")


async def _cmd_investigate(args):
    """Run the investigation loop — detect open questions, create investigation plans."""
    from .database import create_tables, get_session
    from .investigation import InvestigationEngine
    from sqlalchemy import select
    from .database import ClaimRecord, EvidenceUnitRecord, ContradictionRecord, InvestigationRecord

    await create_tables()

    async with get_session() as session:
        claims = [_row_to_dict(r) for r in (await session.execute(select(ClaimRecord))).scalars().all()]
        evidence = [_row_to_dict(r) for r in (await session.execute(select(EvidenceUnitRecord))).scalars().all()]
        contradictions = [_row_to_dict(r) for r in (await session.execute(select(ContradictionRecord))).scalars().all()]
        existing_investigations = [_row_to_dict(r) for r in (await session.execute(select(InvestigationRecord))).scalars().all()]

    engine = InvestigationEngine(
        claims=claims,
        evidence=evidence,
        contradictions=contradictions,
        existing_investigations=existing_investigations,
    )

    plans = engine.detect_open_questions()[: args.max_investigations]

    print(f"\nInvestigation Queue — {len(plans)} open question(s)")
    print("=" * 60)

    for i, plan in enumerate(plans):
        print(f"\n[{i+1}] {plan.investigation_id}")
        print(f"  Q: {plan.question}")
        print(f"  Status: {plan.status} | Priority: {plan.priority}")
        print(f"  Claims: {', '.join(claim_id[:12] for claim_id in plan.claim_ids)}")
        print(f"  Targets:")
        for t in plan.evidence_targets:
            print(f"    - [{t.target_type}] {t.description[:80]}... (p={t.priority})")
        print(f"  Rationale: {plan.rationale[:100]}")

    if not plans:
        print("\nNo open questions detected. Epistemic Graph is clean.")

    print(f"\n{'=' * 60}")
    print(f"Total: {len(plans)} investigation(s) proposed")
    print(f"Run 'ganymede investigate --max-investigations N' to adjust queue size")


async def _cmd_agents(args):
    """Run agent pipeline — agents propose, policy evaluates."""
    from agents import AgentRunner
    from .database import create_tables, get_session
    from sqlalchemy import select
    from .database import ClaimRecord, EvidenceUnitRecord, SourceRecord, ContradictionRecord, InvestigationRecord

    await create_tables()

    async with get_session() as session:
        claims = [_row_to_dict(r) for r in (await session.execute(select(ClaimRecord))).scalars().all()]
        evidence = [_row_to_dict(r) for r in (await session.execute(select(EvidenceUnitRecord))).scalars().all()]
        sources = [_row_to_dict(r) for r in (await session.execute(select(SourceRecord))).scalars().all()]
        contradictions = [_row_to_dict(r) for r in (await session.execute(select(ContradictionRecord))).scalars().all()]
        investigations = [_row_to_dict(r) for r in (await session.execute(select(InvestigationRecord))).scalars().all()]

    runner = AgentRunner()

    agent_ids = args.agent or None

    result = await runner.run_pipeline(
        claims=claims,
        evidence=evidence,
        sources=sources,
        contradictions=contradictions,
        investigations=investigations,
        context={"corpus_dir": "corpus/sources"},
        agent_ids=agent_ids,
    )

    print(f"\nAgent Pipeline — {result['agents_run']} agent(s) ran")
    print("=" * 60)
    print(f"  Total proposals: {result['total_proposals']}")
    print(f"  Accepted:        {result['accepted']}")
    print(f"  Rejected:        {result['rejected']}")
    print(f"  Needs review:    {result['needs_review']}")

    if result["by_agent"]:
        print(f"\n  By agent:")
        for agent_id, summary in result["by_agent"].items():
            print(f"    {agent_id:25s} P={summary['proposals']} A={summary['accepted']} R={summary['rejected']} N={summary['needs_review']}")

    # Print proposals that need review
    needs_review = [r for r in runner.results if r["decision"].outcome == "needs_review"]
    if needs_review:
        print(f"\n  Proposals needing review:")
        for nr in needs_review:
            p = nr["proposal"]
            d = nr["decision"]
            print(f"    [{p.agent_id}] {p.operation}: {d.reason[:80]}")

    print(f"\n{'=' * 60}")



async def _cmd_classify_voices(args):
    """Classify human-grounded claims into voices (Stage 5 model refinement).

    Model output is untrusted annotation: it NEVER changes claim status or
    confidence, is stored alongside the model+prompt version that produced
    it, and is excluded from the corpus fingerprint.
    """
    from sqlalchemy import select, update
    from .database import create_tables, get_session, ClaimRecord, EvidenceUnitRecord
    from .inference import select_provider, log_inference_event
    from .refine import classify_voices, VOICE_LABELS
    from .store_epistemic import EpistemicGraphStore

    await create_tables()

    provider = select_provider()
    if provider is None:
        print("No inference provider available — deterministic layer stands alone.")
        return
    print(f"Provider: {provider.name} (sovereignty crossed: {provider.sovereignty_crossed})")
    print(f"Model:    {args.model}")

    statuses = [s.strip().upper() for s in args.status.split(",") if s.strip()]

    # Human-grounded claims: any evidence from user turn or post author,
    # matching status, not yet classified by this prompt version.
    async with get_session() as session:
        rows = (
            await session.execute(
                select(ClaimRecord.id, ClaimRecord.text, ClaimRecord.confidence)
                .join(EvidenceUnitRecord, EvidenceUnitRecord.claim_id == ClaimRecord.id)
                .where(
                    EvidenceUnitRecord.speaker.in_(["user", "author"]),
                    ClaimRecord.status.in_(statuses),
                    (ClaimRecord.voice_class.is_(None))
                    | (ClaimRecord.voice_prompt_version != "1.0.0"),
                )
                .distinct()
                .order_by(ClaimRecord.confidence.desc())
                .limit(args.limit)
            )
        ).all()

    if not rows:
        print("No unclassified human-grounded claims found.")
        return

    targets = [{"claim_id": r.id, "text": r.text} for r in rows]
    print(f"Classifying {len(targets)} human-grounded claims...")

    report = classify_voices(targets, provider=provider, model=args.model, max_targets=args.limit)
    classifications = report.classifications
    print(f"  classified: {len(classifications)} / {len(targets)}")

    if not classifications:
        print("  no valid classifications — nothing written")
        return

    # Tally + write back
    tally: dict = {}
    async with get_session() as session:
        for vc in classifications:
            await session.execute(
                update(ClaimRecord)
                .where(ClaimRecord.id == vc.claim_id)
                .values(
                    voice_class=vc.voice,
                    voice_model=vc.model,
                    voice_prompt_version=vc.prompt_contract_version,
                )
            )
            tally[vc.voice] = tally.get(vc.voice, 0) + 1
        await session.commit()

    for voice, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {voice}: {n}")

    # Persist MODEL_INVOKED ledger events
    store = EpistemicGraphStore()
    for event in report.inference_events:
        await store.put_ledger_event(event)
    print(f"DONE: {len(classifications)} claims annotated (model-derived, untrusted)")
    print(f"  ledger events: {len(report.inference_events)}")


if __name__ == "__main__":
    main()
