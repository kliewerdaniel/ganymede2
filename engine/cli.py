"""CLI for Ganymede 2.0."""

from __future__ import annotations

import argparse
import asyncio
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
    build_parser = artifact_subparsers.add_parser("build", help="Build artifact")
    build_parser.add_argument("--output", default="./dist", help="Output directory")
    serve_parser = artifact_subparsers.add_parser("serve", help="Serve artifact locally")
    serve_parser.add_argument("--port", type=int, default=3000, help="Port")

    # gate
    gate_parser = subparsers.add_parser("gate", help="Run quality gates")

    # explain
    explain_parser = subparsers.add_parser("explain", help="Explain a claim")
    explain_parser.add_argument("claim_id", help="Claim ID")

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
        # For incremental, we'd need to load previous sources
        # For now, just do a full compile
        report = await compiler.compile_corpus_dir(args.corpus_dir, cycle=args.cycle)
    else:
        report = await compiler.compile_corpus_dir(args.corpus_dir, cycle=args.cycle)
    print(report)


async def _cmd_artifact_build(args):
    print(f"Building artifact to {args.output}...")
    # TODO: Implement artifact compiler
    print("Artifact build not yet implemented.")


def _cmd_artifact_serve(args):
    print(f"Serving artifact on port {args.port}...")
    # TODO: Implement serve
    print("Artifact serve not yet implemented.")


async def _cmd_gate(args):
    from .gate import run_all_gates
    report = await run_all_gates()
    print(report)


async def _cmd_explain(args):
    from .store_epistemic import EpistemicGraphStore
    store = EpistemicGraphStore()
    claim = await store.get_claim(args.claim_id)
    if claim:
        import json
        print(json.dumps(claim, indent=2))
    else:
        print(f"Claim {args.claim_id} not found.")
