"""Full-corpus ingestion driver for the Chris corpus.

Reads the real corpus (~/Projects/Chris: ChatGPT conversations + Reddit
comments/submissions), compiles it through the Ganymede 2.0 pipeline in
batches, and reports progress. Deterministic: same input → same output.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.compiler import Compiler
from engine.database import create_tables


async def main() -> None:
    corpus_root = Path("/Users/danielkliewer/Projects/Chris")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0  # 0 = everything

    conv_dir = corpus_root / "openai" / "conversations_markdown"
    reddit_dirs = [
        corpus_root / "reddit" / "comments",
        corpus_root / "reddit" / "submissions",
    ]

    from engine import canonicalize as canon

    sources = []

    def collect(files, label):
        n = 0
        for f in sorted(files):
            try:
                env = canon.read_source_file(f)
                if env:
                    sources.append(env)
                    n += 1
            except Exception as e:
                print(f"WARN: {f}: {e}")
        print(f"acquired {n} from {label}")

    conv_files = sorted(conv_dir.rglob("*.md"))
    reddit_files = []
    for d in reddit_dirs:
        reddit_files.extend(sorted(d.glob("*.md")))

    if limit:
        step = max(1, len(conv_files) // (limit // 2 or 1))
        conv_files = conv_files[::step][: limit // 2]
        step = max(1, len(reddit_files) // (limit - len(conv_files) or 1))
        reddit_files = reddit_files[::step][: limit - len(conv_files)]

    collect(conv_files, "openai/conversations_markdown")
    collect(reddit_files, "reddit (comments+submissions)")
    print(f"TOTAL SOURCES: {len(sources)}")

    await create_tables()
    compiler = Compiler()

    BATCH = 100
    t0 = time.time()
    total = len(sources)
    for i in range(0, total, BATCH):
        batch = sources[i : i + BATCH]
        report = await compiler.compile_sources(batch, cycle=1)
        done = min(i + BATCH, total)
        rate = done / max(time.time() - t0, 0.001)
        print(
            f"[{done}/{total}] "
            f"claims_new={report.claims_new} updated={report.claims_updated} "
            f"ev={report.evidence_units} su={report.structural_units} "
            f"contra={report.contradictions_detected} "
            f"({rate:.1f} src/s, {time.time() - t0:.0f}s elapsed)",
            flush=True,
        )
        if report.errors:
            for e in report.errors[:3]:
                print(f"  ERR: {e}")
    print(f"DONE in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
