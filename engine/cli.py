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
    elif args.command == "investigate":
        asyncio.run(_cmd_investigate(args))
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

    # Build artifact IR
    compiler = ArtifactCompiler(
        claims=claims,
        evidence=evidence,
        sources=sources,
        contradictions=contradictions,
        investigations=investigations,
    )
    ir = compiler.compile()

    # Write JSON
    ir_path = output_dir / "artifact.json"
    ir_path.write_text(ir.to_json())
    print(f"Artifact IR written to {ir_path}")

    # Write intermediates
    inter = ir.intermediates

    kg_path = output_dir / "knowledge_graph.json"
    kg_path.write_text(json.dumps(inter.knowledge_graph, indent=2, default=str))
    print(f"Knowledge graph written to {kg_path}")

    narrative_path = output_dir / "narrative.md"
    narrative_path.write_text(inter.narrative_document)
    print(f"Narrative document written to {narrative_path}")

    facts_path = output_dir / "established_facts.json"
    facts_path.write_text(json.dumps(inter.established_facts, indent=2, default=str))
    print(f"Established facts written to {facts_path}")

    timeline_path = output_dir / "timeline.json"
    timeline_path.write_text(json.dumps(inter.timeline, indent=2, default=str))
    print(f"Timeline written to {timeline_path}")

    cr_path = output_dir / "contradiction_report.md"
    cr_path.write_text(inter.contradiction_report)
    print(f"Contradiction report written to {cr_path}")

    si_path = output_dir / "source_inventory.json"
    si_path.write_text(json.dumps(inter.source_inventory, indent=2, default=str))
    print(f"Source inventory written to {si_path}")

    # Character dossiers
    for entity_id, dossier in inter.character_dossiers.items():
        dossier_path = output_dir / f"dossier_{entity_id}.json"
        dossier_path.write_text(json.dumps(dossier, indent=2, default=str))

    print(f"\nArtifact build complete. Fingerprint: {ir.corpus_fingerprint}")

    # Also copy to Next.js public directory
    nextjs_public = Path(args.output).resolve().parent / "artifact" / "nextjs" / "public"
    if nextjs_public.exists():
        shutil.copy2(ir_path, nextjs_public / "artifact.json")
        # Copy intermediates
        for name in ["knowledge_graph.json", "narrative.md", "established_facts.json",
                     "timeline.json", "contradiction_report.md", "source_inventory.json"]:
            src = output_dir / name
            if src.exists():
                shutil.copy2(src, nextjs_public / name)
        print(f"Copied to {nextjs_public}")
    else:
        print(f"Note: {nextjs_public} not found. Run from project root.")


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy row to a dict."""
    result = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        result[col.name] = val
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


if __name__ == "__main__":
    main()
