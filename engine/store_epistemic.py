"""Epistemic Graph store — versioned, history-retained.

Stores claims, investigations, and ledger events.
Status is a pure function of evidence, recompiled each compile.
Uses session.add(Model(**data)) to avoid SQLAlchemy 2.0 bulk insert path.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update

from .database import (
    ClaimRecord,
    ContradictionRecord,
    InvestigationRecord,
    LedgerEventRecord,
    get_session,
)


def _compute_content_hash(record: Dict[str, Any]) -> str:
    """Compute a deterministic content hash over a record."""
    exclude = {"_meta", "created_at", "updated_at", "content_hash"}
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


def _claim_record_from_dict(record: Dict[str, Any]) -> ClaimRecord:
    return ClaimRecord(
        id=record["id"],
        text=record["text"],
        normalized=record["normalized"],
        status=record["status"],
        confidence=record["confidence"],
        confidence_terms=record.get("confidence_terms", {}),
        evidence_ids=record.get("evidence_ids", []),
        source_ids=record.get("source_ids", []),
        entity_ids=record.get("entity_ids", []),
        contradiction_ids=record.get("contradiction_ids", []),
        derived_from=record.get("derived_from", []),
        compiler_version=record["compiler_version"],
        policy_version=record["policy_version"],
        history=record.get("history", []),
        created_at=record.get("created_at", time.time()),
        updated_at=record.get("updated_at", time.time()),
        content_hash=record["content_hash"],
    )


def _investigation_record_from_dict(record: Dict[str, Any]) -> InvestigationRecord:
    return InvestigationRecord(
        id=record["id"],
        question=record["question"],
        status=record.get("status", "open"),
        claim_id=record.get("claim_id"),
        claim_ids=record.get("claim_ids", []),
        evidence_ids=record.get("evidence_ids", []),
        rationale=record.get("rationale"),
        created_at=record.get("created_at", time.time()),
        completed_at=record.get("completed_at"),
    )


def _ledger_event_record_from_dict(record: Dict[str, Any]) -> LedgerEventRecord:
    return LedgerEventRecord(
        id=record["id"],
        event_type=record["event_type"],
        actor=record["actor"],
        operation=record["operation"],
        inputs=record.get("inputs", {}),
        outputs=record.get("outputs", {}),
        input_hashes=record.get("input_hashes", []),
        output_hashes=record.get("output_hashes", []),
        model=record.get("model"),
        policy_version=record["policy_version"],
        parent_event_id=record.get("parent_event_id"),
        timestamp=record.get("timestamp", time.time()),
        metadata_json=record.get("metadata", {}),
    )


class EpistemicGraphStore:
    """Versioned store for the Epistemic Graph."""

    # ------------------------------------------------------------------
    # Claims
    # ------------------------------------------------------------------

    async def put_claim(self, claim: Dict[str, Any]) -> Optional[str]:
        """Insert or update a claim. Returns claim_id if new/changed, None if unchanged."""
        now = time.time()
        record = {
            "id": claim["id"],
            "text": claim["text"],
            "normalized": claim["normalized"],
            "status": claim["status"],
            "confidence": claim["confidence"],
            "confidence_terms": claim.get("confidence_terms", {}),
            "evidence_ids": claim.get("evidence_ids", []),
            "source_ids": claim.get("source_ids", []),
            "entity_ids": claim.get("entity_ids", []),
            "contradiction_ids": claim.get("contradiction_ids", []),
            "derived_from": claim.get("derived_from", []),
            "compiler_version": claim["compiler_version"],
            "policy_version": claim["policy_version"],
            "history": claim.get("history", []),
            "created_at": now,
            "updated_at": now,
        }
        record["content_hash"] = _compute_content_hash(record)

        async with get_session() as session:
            existing = await session.execute(
                select(ClaimRecord).where(ClaimRecord.id == record["id"])
            )
            existing_claim = existing.scalar()

            if existing_claim:
                if existing_claim.content_hash == record["content_hash"]:
                    return None  # unchanged
                # Update but retain history
                old_status = existing_claim.status
                new_status = record["status"]
                if old_status != new_status:
                    history_entry = {
                        "from_status": old_status,
                        "to_status": new_status,
                        "at": now,
                        "reason": claim.get("status_reason", "evidence change"),
                    }
                    record["history"] = existing_claim.history + [history_entry]
                # Preserve created_at
                record["created_at"] = existing_claim.created_at
                record["updated_at"] = now

                # Use update
                await session.execute(
                    update(ClaimRecord)
                    .where(ClaimRecord.id == record["id"])
                    .values(**record)
                )
            else:
                obj = _claim_record_from_dict(record)
                session.add(obj)

            return record["id"]

    async def get_claim(self, claim_id: str) -> Optional[Dict]:
        async with get_session() as session:
            result = await session.execute(
                select(ClaimRecord).where(ClaimRecord.id == claim_id)
            )
            record = result.scalar()
            return self._claim_to_dict(record) if record else None

    async def get_claims_by_status(self, status: str) -> List[Dict]:
        async with get_session() as session:
            result = await session.execute(
                select(ClaimRecord).where(ClaimRecord.status == status)
            )
            return [self._claim_to_dict(r) for r in result.scalars()]

    async def get_all_claims(self) -> List[Dict]:
        async with get_session() as session:
            result = await session.execute(select(ClaimRecord))
            return [self._claim_to_dict(r) for r in result.scalars()]

    async def get_claims_by_source(self, source_id: str) -> List[Dict]:
        async with get_session() as session:
            result = await session.execute(
                select(ClaimRecord).where(
                    ClaimRecord.source_ids.contains([source_id])
                )
            )
            return [self._claim_to_dict(r) for r in result.scalars()]

    # ------------------------------------------------------------------
    # Investigations
    # ------------------------------------------------------------------

    async def put_investigation(self, investigation: Dict[str, Any]) -> Optional[str]:
        now = time.time()
        record = {
            "id": investigation["id"],
            "question": investigation["question"],
            "status": investigation.get("status", "open"),
            "claim_id": investigation.get("claim_id"),
            "claim_ids": investigation.get("claim_ids", []),
            "evidence_ids": investigation.get("evidence_ids", []),
            "rationale": investigation.get("rationale"),
            "created_at": now,
            "completed_at": None,
        }

        async with get_session() as session:
            obj = _investigation_record_from_dict(record)
            session.add(obj)
            return record["id"]

    # ------------------------------------------------------------------
    # Ledger Events
    # ------------------------------------------------------------------

    async def put_ledger_event(self, event: Dict[str, Any]) -> Optional[str]:
        now = time.time()
        record = {
            "id": event["id"],
            "event_type": event["event_type"],
            "actor": event["actor"],
            "operation": event["operation"],
            "inputs": event.get("inputs", {}),
            "outputs": event.get("outputs", {}),
            "input_hashes": event.get("input_hashes", []),
            "output_hashes": event.get("output_hashes", []),
            "model": event.get("model"),
            "policy_version": event["policy_version"],
            "parent_event_id": event.get("parent_event_id"),
            "timestamp": now,
            "metadata": event.get("metadata", {}),
        }

        async with get_session() as session:
            obj = _ledger_event_record_from_dict(record)
            session.add(obj)
            return record["id"]

    async def get_ledger_events(self, claim_id: str = None, event_type: str = None,
                                 actor: str = None, since: float = None) -> List[Dict]:
        async with get_session() as session:
            query = select(LedgerEventRecord)
            if claim_id:
                query = query.where(
                    LedgerEventRecord.inputs.contains({"claim_id": claim_id})
                )
            if event_type:
                query = query.where(LedgerEventRecord.event_type == event_type)
            if actor:
                query = query.where(LedgerEventRecord.actor == actor)
            if since:
                query = query.where(LedgerEventRecord.timestamp >= since)
            result = await session.execute(query.order_by(LedgerEventRecord.timestamp))
            return [self._ledger_to_dict(r) for r in result.scalars()]

    # ------------------------------------------------------------------
    # Contradictions
    # ------------------------------------------------------------------

    async def get_contradiction(self, contradiction_id: str) -> Optional[Dict]:
        async with get_session() as session:
            result = await session.execute(
                select(ContradictionRecord).where(ContradictionRecord.id == contradiction_id)
            )
            record = result.scalar()
            return self._contradiction_to_dict(record) if record else None

    async def get_all_contradictions(self) -> List[Dict]:
        async with get_session() as session:
            result = await session.execute(select(ContradictionRecord))
            return [self._contradiction_to_dict(r) for r in result.scalars()]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _claim_to_dict(self, record: ClaimRecord) -> Dict:
        return {
            "id": record.id,
            "text": record.text,
            "normalized": record.normalized,
            "status": record.status,
            "confidence": record.confidence,
            "confidence_terms": record.confidence_terms,
            "evidence_ids": record.evidence_ids,
            "source_ids": record.source_ids,
            "entity_ids": record.entity_ids,
            "contradiction_ids": record.contradiction_ids,
            "derived_from": record.derived_from,
            "compiler_version": record.compiler_version,
            "policy_version": record.policy_version,
            "history": record.history,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    def _ledger_to_dict(self, record: LedgerEventRecord) -> Dict:
        return {
            "id": record.id,
            "event_type": record.event_type,
            "actor": record.actor,
            "operation": record.operation,
            "inputs": record.inputs,
            "outputs": record.outputs,
            "input_hashes": record.input_hashes,
            "output_hashes": record.output_hashes,
            "model": record.model,
            "policy_version": record.policy_version,
            "parent_event_id": record.parent_event_id,
            "timestamp": record.timestamp,
            "metadata": record.metadata_json,
        }

    def _contradiction_to_dict(self, record: ContradictionRecord) -> Dict:
        return {
            "id": record.id,
            "anchor_words": record.anchor_words,
            "entity_id": record.entity_id,
            "claim_a_id": record.claim_a_id,
            "claim_b_id": record.claim_b_id,
            "text_a": record.text_a,
            "text_b": record.text_b,
            "overlap": record.overlap,
            "sources_a": record.sources_a,
            "sources_b": record.sources_b,
            "status": record.status,
            "resolution": record.resolution,
            "resolved_by": record.resolved_by,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
