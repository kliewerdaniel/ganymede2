"""Evidence Graph store — immutable, append-only.

Stores sources, structural units, evidence units, and contradictions.
Content-hash gated: identical input produces no write.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .database import (
    EvidenceUnitRecord,
    SourceRecord,
    StructuralUnitRecord,
    ContradictionRecord,
    get_session,
)


def _compute_content_hash(record: Dict[str, Any], exclude: set = None) -> str:
    """Compute a deterministic content hash over a record."""
    exclude = exclude or {"_meta", "created_at", "updated_at", "content_hash"}
    canonical = {}
    for k, v in sorted(record.items()):
        if k in exclude:
            continue
        if isinstance(v, dict):
            canonical[k] = json.dumps(v, sort_keys=True)
        elif isinstance(v, list):
            canonical[k] = json.dumps(v, sort_keys=True)
        else:
            canonical[k] = str(v)
    payload = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


import json


class EvidenceGraphStore:
    """Append-only store for the Evidence Graph."""

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------

    async def put_source(self, source: Dict[str, Any]) -> Optional[str]:
        """Insert a source. Returns source_id if new, None if unchanged."""
        now = time.time()
        record = {
            "id": source["id"],
            "type": source["type"],
            "origin": source["origin"],
            "text": source["text"],
            "url": source.get("url"),
            "domain": source.get("domain"),
            "author": source.get("author"),
            "fetched_at": source["fetched_at"],
            "checksum": source["checksum"],
            "parser_version": source["parser_version"],
            "normalization_version": source["normalization_version"],
            "status": "active",
            "metadata": source.get("metadata", {}),
            "created_at": now,
            "updated_at": now,
        }
        record["content_hash"] = _compute_content_hash(record)

        async with get_session() as session:
            existing = await session.execute(
                select(SourceRecord.content_hash).where(SourceRecord.id == record["id"])
            )
            if existing.scalar() == record["content_hash"]:
                return None  # unchanged

            await session.execute(
                pg_insert(SourceRecord)
                .values(**record)
                .on_conflict_do_nothing(index_elements=["content_hash"])
            )
            return record["id"]

    async def get_source(self, source_id: str) -> Optional[Dict]:
        async with get_session() as session:
            result = await session.execute(
                select(SourceRecord).where(SourceRecord.id == source_id)
            )
            record = result.scalar()
            return self._source_to_dict(record) if record else None

    async def get_active_sources(self) -> List[Dict]:
        async with get_session() as session:
            result = await session.execute(
                select(SourceRecord).where(SourceRecord.status == "active")
            )
            return [self._source_to_dict(r) for r in result.scalars()]

    async def mark_source_removed(self, source_id: str) -> bool:
        async with get_session() as session:
            result = await session.execute(
                select(SourceRecord).where(SourceRecord.id == source_id)
            )
            record = result.scalar()
            if not record:
                return False
            record.status = "removed"
            record.updated_at = time.time()
            return True

    # ------------------------------------------------------------------
    # Structural Units
    # ------------------------------------------------------------------

    async def put_structural_unit(self, unit: Dict[str, Any]) -> Optional[str]:
        record = {
            "id": unit["id"],
            "source_id": unit["source_id"],
            "type": unit["type"],
            "text": unit["text"],
            "offset": unit["offset"],
            "span_start": unit["span_start"],
            "span_end": unit["span_end"],
            "parent_id": unit.get("parent_id"),
            "metadata": unit.get("metadata", {}),
            "created_at": time.time(),
        }
        record["content_hash"] = _compute_content_hash(record)

        async with get_session() as session:
            existing = await session.execute(
                select(StructuralUnitRecord.content_hash).where(StructuralUnitRecord.id == record["id"])
            )
            if existing.scalar() == record["content_hash"]:
                return None

            await session.execute(
                pg_insert(StructuralUnitRecord)
                .values(**record)
                .on_conflict_do_nothing(index_elements=["content_hash"])
            )
            return record["id"]

    # ------------------------------------------------------------------
    # Evidence Units
    # ------------------------------------------------------------------

    async def put_evidence_unit(self, evidence: Dict[str, Any]) -> Optional[str]:
        record = {
            "id": evidence["id"],
            "source_id": evidence["source_id"],
            "structural_unit_id": evidence.get("structural_unit_id"),
            "claim_id": evidence.get("claim_id"),
            "domain": evidence.get("domain"),
            "author": evidence.get("author"),
            "stance": evidence.get("stance", "support"),
            "quote": evidence["quote"],
            "offset": evidence["offset"],
            "timestamp": evidence.get("timestamp"),
            "reliability": evidence.get("reliability"),
            "source_checksum": evidence["source_checksum"],
            "parser_version": evidence["parser_version"],
            "needs_revalidation": False,
            "stale_evidence": 0,
            "created_at": time.time(),
        }
        record["content_hash"] = _compute_content_hash(record)

        async with get_session() as session:
            existing = await session.execute(
                select(EvidenceUnitRecord.content_hash).where(EvidenceUnitRecord.id == record["id"])
            )
            if existing.scalar() == record["content_hash"]:
                return None

            await session.execute(
                pg_insert(EvidenceUnitRecord)
                .values(**record)
                .on_conflict_do_nothing(index_elements=["content_hash"])
            )
            return record["id"]

    async def get_evidence_for_claim(self, claim_id: str) -> List[Dict]:
        async with get_session() as session:
            result = await session.execute(
                select(EvidenceUnitRecord).where(EvidenceUnitRecord.claim_id == claim_id)
            )
            return [self._evidence_to_dict(r) for r in result.scalars()]

    async def get_evidence_for_source(self, source_id: str) -> List[Dict]:
        async with get_session() as session:
            result = await session.execute(
                select(EvidenceUnitRecord).where(EvidenceUnitRecord.source_id == source_id)
            )
            return [self._evidence_to_dict(r) for r in result.scalars()]

    async def claim_id_for_evidence(self, evidence_id: str) -> Optional[str]:
        async with get_session() as session:
            result = await session.execute(
                select(EvidenceUnitRecord.claim_id).where(EvidenceUnitRecord.id == evidence_id)
            )
            return result.scalar()

    # ------------------------------------------------------------------
    # Contradictions
    # ------------------------------------------------------------------

    async def put_contradiction(self, contradiction: Dict[str, Any]) -> Optional[str]:
        now = time.time()
        record = {
            "id": contradiction["id"],
            "anchor_words": contradiction["anchor_words"],
            "entity_id": contradiction.get("entity_id"),
            "claim_a_id": contradiction["claim_a_id"],
            "claim_b_id": contradiction["claim_b_id"],
            "text_a": contradiction["text_a"],
            "text_b": contradiction["text_b"],
            "overlap": contradiction["overlap"],
            "sources_a": contradiction["sources_a"],
            "sources_b": contradiction["sources_b"],
            "status": "open",
            "resolution": None,
            "resolved_by": None,
            "created_at": now,
            "updated_at": now,
        }
        record["content_hash"] = _compute_content_hash(record)

        async with get_session() as session:
            existing = await session.execute(
                select(ContradictionRecord.content_hash).where(ContradictionRecord.id == record["id"])
            )
            if existing.scalar() == record["content_hash"]:
                return None

            await session.execute(
                pg_insert(ContradictionRecord)
                .values(**record)
                .on_conflict_do_nothing(index_elements=["content_hash"])
            )
            return record["id"]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _source_to_dict(self, record: SourceRecord) -> Dict:
        return {
            "id": record.id,
            "type": record.type,
            "origin": record.origin,
            "text": record.text,
            "url": record.url,
            "domain": record.domain,
            "author": record.author,
            "fetched_at": record.fetched_at,
            "checksum": record.checksum,
            "parser_version": record.parser_version,
            "normalization_version": record.normalization_version,
            "status": record.status,
            "metadata": record.metadata_json,
        }

    def _evidence_to_dict(self, record: EvidenceUnitRecord) -> Dict:
        return {
            "id": record.id,
            "source_id": record.source_id,
            "structural_unit_id": record.structural_unit_id,
            "claim_id": record.claim_id,
            "domain": record.domain,
            "author": record.author,
            "stance": record.stance,
            "quote": record.quote,
            "offset": record.offset,
            "timestamp": record.timestamp,
            "reliability": record.reliability,
            "source_checksum": record.source_checksum,
            "parser_version": record.parser_version,
            "needs_revalidation": record.needs_revalidation,
            "stale_evidence": record.stale_evidence,
        }
