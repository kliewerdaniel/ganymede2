"""Backfill evidence_units.speaker from source text speaker markers.

Deterministic: the speaker of an evidence unit is the last speaker header
("### 👤 User" / "### 🤖 Assistant" / ...) at or before its offset in the
canonical source text. For posts (Reddit), the speaker is the author.

Idempotent: rows already carrying a speaker are skipped unless --force.
"""
from __future__ import annotations

import argparse
import asyncio
import time
from typing import Dict, List

from sqlalchemy import select, update

from engine.database import get_session, EvidenceUnitRecord, SourceRecord
from engine.extract import speaker_at


async def main(force: bool = False, batch_size: int = 2000) -> None:
    t0 = time.time()
    # Load all source texts once (id -> (text, type)). 4.8k sources, ~200MB total text.
    sources: Dict[str, tuple] = {}
    async with get_session() as session:
        rows = (await session.execute(select(SourceRecord))).scalars().all()
        for r in rows:
            sources[r.id] = (r.text, r.type)
    print(f"loaded {len(sources)} sources in {time.time()-t0:.1f}s")

    # Walk evidence units in batches, compute speaker, write back.
    updated = 0
    skipped = 0
    no_source = 0
    t1 = time.time()
    last_id = ""
    while True:
        async with get_session() as session:
            batch = (
                await session.execute(
                    select(EvidenceUnitRecord)
                    .where(EvidenceUnitRecord.id > last_id)
                    .order_by(EvidenceUnitRecord.id)
                    .limit(batch_size)
                )
            ).scalars().all()
            if not batch:
                break
            pending: Dict[str, str] = {}
            for ev in batch:
                last_id = ev.id
                if ev.speaker and not force:
                    skipped += 1
                    continue
                src = sources.get(ev.source_id)
                if src is None:
                    no_source += 1
                    continue
                text, stype = src
                sp = speaker_at(text, ev.offset, stype)
                if sp:
                    pending[ev.id] = sp
            if pending:
                # bulk update by PK
                for ev_id, sp in pending.items():
                    await session.execute(
                        update(EvidenceUnitRecord)
                        .where(EvidenceUnitRecord.id == ev_id)
                        .values(speaker=sp)
                    )
                await session.commit()
                updated += len(pending)
        if updated and updated % 10000 < batch_size:
            print(f"  {updated} updated ({time.time()-t1:.0f}s)")
    print(f"DONE: updated={updated} skipped={skipped} no_source={no_source} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="recompute even if speaker is set")
    args = p.parse_args()
    asyncio.run(main(force=args.force))
