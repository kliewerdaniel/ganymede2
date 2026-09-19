"""Database schema and connection for Ganymede 2.0.

Two-store separation:
- Evidence Graph (immutable): sources, structural_units, evidence_units, contradictions
- Epistemic Graph (versioned): claims, investigations, ledger_events
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def get_database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://ganymede:ganymede@localhost:5432/ganymede",
    )


def get_sync_database_url() -> str:
    return os.environ.get(
        "SYNC_DATABASE_URL",
        "postgresql://ganymede:ganymede@localhost:5432/ganymede",
    )


# ---------------------------------------------------------------------------
# Engine and session
# ---------------------------------------------------------------------------

_async_engine = None
_async_session_factory = None

_sync_engine = None


def get_async_engine():
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            get_database_url(),
            echo=False,
            pool_size=5,
            max_overflow=10,
        )
    return _async_engine


def get_async_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            get_async_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


def get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(
            get_sync_database_url(),
            echo=False,
        )
    return _sync_engine


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_async_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Evidence Graph (immutable store)
# ---------------------------------------------------------------------------

class SourceRecord(Base):
    """A raw source document. Append-only, never deleted."""
    __tablename__ = "sources"

    id = Column(String(64), primary_key=True)  # src-<sha256>
    type = Column(String(32), nullable=False)  # conversation, post, document, code_repo, image, note, transcript
    origin = Column(Text, nullable=False)
    text = Column(Text, nullable=False)
    url = Column(Text, nullable=True)
    domain = Column(String(256), nullable=True)
    author = Column(String(256), nullable=True)
    fetched_at = Column(Float, nullable=False)
    checksum = Column(String(64), nullable=False)  # sha256 of text
    parser_version = Column(String(16), nullable=False)
    normalization_version = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="active")  # active, removed
    metadata_json = Column("metadata", JSONB, nullable=False, default=dict)
    content_hash = Column(String(64), nullable=False, unique=True)  # for change detection
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)

    # Relationships
    structural_units = relationship("StructuralUnitRecord", back_populates="source")
    evidence_units = relationship("EvidenceUnitRecord", back_populates="source")

    __table_args__ = (
        Index("idx_sources_type", "type"),
        Index("idx_sources_status", "status"),
        Index("idx_sources_checksum", "checksum"),
    )


class StructuralUnitRecord(Base):
    """A structural unit within a source (turn, page, paragraph, file, etc.)."""
    __tablename__ = "structural_units"

    id = Column(String(64), primary_key=True)  # su-<sha256>
    source_id = Column(String(64), ForeignKey("sources.id"), nullable=False)
    type = Column(String(32), nullable=False)  # turn, page, paragraph, file, commit, ocr_block, speaker_segment
    text = Column(Text, nullable=False)
    offset = Column(Integer, nullable=False)  # char offset in source text
    span_start = Column(Integer, nullable=False)
    span_end = Column(Integer, nullable=False)
    parent_id = Column(String(64), ForeignKey("structural_units.id"), nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=False, default=dict)
    content_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(Float, nullable=False)

    # Relationships
    source = relationship("SourceRecord", back_populates="structural_units")
    evidence_units = relationship("EvidenceUnitRecord", back_populates="structural_unit")

    __table_args__ = (
        Index("idx_structural_units_source", "source_id"),
        Index("idx_structural_units_type", "type"),
    )


class EvidenceUnitRecord(Base):
    """The smallest provenance-bearing object. Bridge between Evidence and Epistemic graphs."""
    __tablename__ = "evidence_units"

    id = Column(String(64), primary_key=True)  # ev-<sha256>
    source_id = Column(String(64), ForeignKey("sources.id"), nullable=False)
    structural_unit_id = Column(String(64), ForeignKey("structural_units.id"), nullable=True)
    claim_id = Column(String(64), ForeignKey("claims.id"), nullable=True)  # filled in Stage 6
    domain = Column(String(256), nullable=True)
    author = Column(String(256), nullable=True)
    stance = Column(String(16), nullable=False, default="support")  # support, contradict
    quote = Column(Text, nullable=False)
    offset = Column(Integer, nullable=False)
    timestamp = Column(Float, nullable=True)
    reliability = Column(Float, nullable=True)
    source_checksum = Column(String(64), nullable=False)  # for staleness detection
    parser_version = Column(String(16), nullable=False)
    needs_revalidation = Column(Boolean, nullable=False, default=False)
    stale_evidence = Column(Integer, nullable=False, default=0)
    content_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(Float, nullable=False)

    # Relationships
    source = relationship("SourceRecord", back_populates="evidence_units")
    structural_unit = relationship("StructuralUnitRecord", back_populates="evidence_units")
    claim = relationship("ClaimRecord", back_populates="evidence_units")

    __table_args__ = (
        Index("idx_evidence_units_source", "source_id"),
        Index("idx_evidence_units_claim", "claim_id"),
        Index("idx_evidence_units_stance", "stance"),
    )


class ContradictionRecord(Base):
    """A contradiction between two claims. Both sides retained."""
    __tablename__ = "contradictions"

    id = Column(String(64), primary_key=True)  # con-<sha256>
    anchor_words = Column(JSONB, nullable=False, default=list)
    entity_id = Column(String(64), nullable=True)
    claim_a_id = Column(String(64), ForeignKey("claims.id"), nullable=False)
    claim_b_id = Column(String(64), ForeignKey("claims.id"), nullable=False)
    text_a = Column(Text, nullable=False)
    text_b = Column(Text, nullable=False)
    overlap = Column(Float, nullable=False)
    sources_a = Column(JSONB, nullable=False, default=list)
    sources_b = Column(JSONB, nullable=False, default=list)
    status = Column(String(16), nullable=False, default="open")  # open, resolved, accepted_tension
    resolution = Column(Text, nullable=True)
    resolved_by = Column(String(256), nullable=True)
    content_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)

    # Relationships
    claim_a = relationship("ClaimRecord", foreign_keys=[claim_a_id], back_populates="contradictions_a")
    claim_b = relationship("ClaimRecord", foreign_keys=[claim_b_id], back_populates="contradictions_b")

    __table_args__ = (
        Index("idx_contradictions_claim_a", "claim_a_id"),
        Index("idx_contradictions_claim_b", "claim_b_id"),
        Index("idx_contradictions_status", "status"),
    )


# ---------------------------------------------------------------------------
# Epistemic Graph (versioned store)
# ---------------------------------------------------------------------------

class ClaimRecord(Base):
    """A claim with lifecycle status, confidence, and full history."""
    __tablename__ = "claims"

    id = Column(String(64), primary_key=True)  # clm-<sha256>
    text = Column(Text, nullable=False)
    normalized = Column(Text, nullable=False)  # normalized form for deduplication
    status = Column(String(16), nullable=False, default="UNEXAMINED")
    confidence = Column(Float, nullable=False, default=0.0)
    confidence_terms = Column(JSONB, nullable=False, default=dict)
    evidence_ids = Column(JSONB, nullable=False, default=list)
    source_ids = Column(JSONB, nullable=False, default=list)
    entity_ids = Column(JSONB, nullable=False, default=list)
    contradiction_ids = Column(JSONB, nullable=False, default=list)
    derived_from = Column(JSONB, nullable=False, default=list)
    compiler_version = Column(String(16), nullable=False)
    policy_version = Column(String(16), nullable=False)
    history = Column(JSONB, nullable=False, default=list)
    content_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)

    # Relationships
    evidence_units = relationship("EvidenceUnitRecord", back_populates="claim")
    contradictions_a = relationship("ContradictionRecord", foreign_keys=[ContradictionRecord.claim_a_id], back_populates="claim_a")
    contradictions_b = relationship("ContradictionRecord", foreign_keys=[ContradictionRecord.claim_b_id], back_populates="claim_b")
    investigations = relationship("InvestigationRecord", back_populates="claim")

    __table_args__ = (
        Index("idx_claims_status", "status"),
        Index("idx_claims_confidence", "confidence"),
        Index("idx_claims_normalized", "normalized"),
    )


class InvestigationRecord(Base):
    """A deliberate act of inquiry. Required for UNRESOLVED claims."""
    __tablename__ = "investigations"

    id = Column(String(64), primary_key=True)  # inv-<sha256>
    question = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="open")  # open, completed, abandoned
    claim_id = Column(String(64), ForeignKey("claims.id"), nullable=True)
    claim_ids = Column(JSONB, nullable=False, default=list)
    evidence_ids = Column(JSONB, nullable=False, default=list)
    rationale = Column(Text, nullable=True)
    created_at = Column(Float, nullable=False)
    completed_at = Column(Float, nullable=True)

    # Relationships
    claim = relationship("ClaimRecord", back_populates="investigations")

    __table_args__ = (
        Index("idx_investigations_status", "status"),
        Index("idx_investigations_claim", "claim_id"),
    )


class LedgerEventRecord(Base):
    """Append-only event log. Forms a DAG."""
    __tablename__ = "ledger_events"

    id = Column(String(64), primary_key=True)  # evt-<sha256>
    event_type = Column(String(32), nullable=False)
    actor = Column(String(64), nullable=False)
    operation = Column(String(64), nullable=False)
    inputs = Column(JSONB, nullable=False, default=dict)
    outputs = Column(JSONB, nullable=False, default=dict)
    input_hashes = Column(JSONB, nullable=False, default=list)
    output_hashes = Column(JSONB, nullable=False, default=list)
    model = Column(JSONB, nullable=True)
    policy_version = Column(String(16), nullable=False)
    parent_event_id = Column(String(64), ForeignKey("ledger_events.id"), nullable=True)
    timestamp = Column(Float, nullable=False)
    metadata_json = Column("metadata", JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("idx_ledger_events_type", "event_type"),
        Index("idx_ledger_events_actor", "actor"),
        Index("idx_ledger_events_parent", "parent_event_id"),
        Index("idx_ledger_events_timestamp", "timestamp"),
    )


# ---------------------------------------------------------------------------
# Schema management
# ---------------------------------------------------------------------------

async def create_tables():
    """Create all tables."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables():
    """Drop all tables."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def create_tables_sync():
    """Create all tables (synchronous)."""
    engine = get_sync_engine()
    Base.metadata.create_all(engine)
