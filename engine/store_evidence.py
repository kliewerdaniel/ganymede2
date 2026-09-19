"""Evidence Graph store — immutable, append-only.

Stores sources, structural units, evidence units, and contradictions.
Content-hash gated: identical input produces no write.
Uses session.add(Model(**data)) to avoid SQLAlchemy 2.0 bulk insert path.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from .database import (
    ContradictionRecord,
    EntityRecord,
    EvidenceUnitRecord,
    SourceRecord,
    StructuralUnitRecord,
    get_session,
)


def _compute_content_hash(record: Dict[str, Any], exclude: set = None) -> str:
    """Compute a deterministic content hash over a record."""
    exclude = exclude or {"_meta", "created_at", "updated_at", "content_hash", "fetched_at"}
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


def _source_record_from_dict(record: Dict[str, Any]) -> SourceRecord:
    return SourceRecord(
        id=record["id"],
        type=record["type"],
        origin=record["origin"],
        text=record["text"],
        url=record.get("url"),
        domain=record.get("domain"),
        author=record.get("author"),
        fetched_at=record["fetched_at"],
        checksum=record["checksum"],
        parser_version=record["parser_version"],
        normalization_version=record["normalization_version"],
        status=record.get("status", "active"),
        metadata_json=record.get("metadata_json", record.get("metadata", {})),
        created_at=record.get("created_at", time.time()),
        updated_at=record.get("updated_at", time.time()),
        content_hash=record["content_hash"],
    )


def _structural_unit_from_dict(record: Dict[str, Any]) -> StructuralUnitRecord:
    return StructuralUnitRecord(
        id=record["id"],
        source_id=record["source_id"],
        type=record["type"],
        text=record["text"],
        offset=record["offset"],
        span_start=record["span_start"],
        span_end=record["span_end"],
        parent_id=record.get("parent_id"),
        metadata_json=record.get("metadata_json", record.get("metadata", {})),
        created_at=record.get("created_at", time.time()),
        content_hash=record["content_hash"],
    )


def _evidence_unit_from_dict(record: Dict[str, Any]) -> EvidenceUnitRecord:
    return EvidenceUnitRecord(
        id=record["id"],
        source_id=record["source_id"],
        structural_unit_id=record.get("structural_unit_id"),
        claim_id=record.get("claim_id"),
        speaker=record.get("speaker"),
        domain=record.get("domain"),
        author=record.get("author"),
        stance=record.get("stance", "support"),
        quote=record["quote"],
        offset=record["offset"],
        timestamp=record.get("timestamp"),
        reliability=record.get("reliability"),
        source_checksum=record["source_checksum"],
        parser_version=record["parser_version"],
        needs_revalidation=record.get("needs_revalidation", False),
        stale_evidence=record.get("stale_evidence", 0),
        created_at=record.get("created_at", time.time()),
        content_hash=record["content_hash"],
    )


def _contradiction_from_dict(record: Dict[str, Any]) -> ContradictionRecord:
    return ContradictionRecord(
        id=record["id"],
        anchor_words=record["anchor_words"],
        entity_id=record.get("entity_id"),
        claim_a_id=record["claim_a_id"],
        claim_b_id=record["claim_b_id"],
        text_a=record["text_a"],
        text_b=record["text_b"],
        overlap=record["overlap"],
        sources_a=record["sources_a"],
        sources_b=record["sources_b"],
        status=record.get("status", "open"),
        resolution=record.get("resolution"),
        resolved_by=record.get("resolved_by"),
        created_at=record.get("created_at", time.time()),
        updated_at=record.get("updated_at", time.time()),
        content_hash=record["content_hash"],
    )


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
            "metadata_json": source.get("metadata", {}),
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

            obj = _source_record_from_dict(record)
            session.add(obj)
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
            "metadata_json": unit.get("metadata", {}),
            "created_at": time.time(),
        }
        record["content_hash"] = _compute_content_hash(record)

        async with get_session() as session:
            existing = await session.execute(
                select(StructuralUnitRecord.content_hash).where(
                    StructuralUnitRecord.id == record["id"]
                )
            )
            if existing.scalar() == record["content_hash"]:
                return None

            obj = _structural_unit_from_dict(record)
            session.add(obj)
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
            "speaker": evidence.get("speaker"),
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
                select(EvidenceUnitRecord.content_hash).where(
                    EvidenceUnitRecord.id == record["id"]
                )
            )
            if existing.scalar() == record["content_hash"]:
                return None

            obj = _evidence_unit_from_dict(record)
            session.add(obj)
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
                select(EvidenceUnitRecord.claim_id).where(
                    EvidenceUnitRecord.id == evidence_id
                )
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
                select(ContradictionRecord.content_hash).where(
                    ContradictionRecord.id == record["id"]
                )
            )
            if existing.scalar() is not None:
                # Same contradiction id (same claim pair) already persisted —
                # idempotent no-op regardless of content_hash drift from
                # created_at/updated_at in the hash input.
                return None

            obj = _contradiction_from_dict(record)
            session.add(obj)
            return record["id"]

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------

    async def put_entity(self, entity: Dict[str, Any]) -> Optional[str]:
        """Upsert an entity: accumulate mentions and source_ids."""
        now = time.time()
        async with get_session() as session:
            result = await session.execute(
                select(EntityRecord).where(EntityRecord.id == entity["id"])
            )
            record = result.scalar()
            if record:
                record.mentions += entity.get("mentions", 0)
                existing_sources = set(record.source_ids or [])
                for sid in entity.get("sources", []):
                    existing_sources.add(sid)
                record.source_ids = sorted(existing_sources)
                record.updated_at = now
                return None
            session.add(EntityRecord(
                id=entity["id"],
                label=entity.get("label", ""),
                normalized=entity.get("label", "").lower(),
                mentions=entity.get("mentions", 0),
                source_ids=entity.get("sources", []),
                created_at=now,
                updated_at=now,
            ))
            return entity["id"]

    async def get_entities(self, *, min_mentions: int = 0, limit: int = 5000) -> List[Dict]:
        """Top entities by mention count."""
        async with get_session() as session:
            result = await session.execute(
                select(EntityRecord)
                .where(EntityRecord.mentions >= min_mentions)
                .order_by(EntityRecord.mentions.desc())
                .limit(limit)
            )
            return [
                {
                    "id": r.id,
                    "name": r.label,
                    "normalized": r.normalized,
                    "mentions": r.mentions,
                    "entity_type": "unknown",
                    "source_ids": r.source_ids or [],
                }
                for r in result.scalars()
            ]

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
            "speaker": record.speaker,
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
