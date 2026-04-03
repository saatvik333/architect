"""Knowledge & Memory ORM models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Float, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from architect_common.enums import ContentType, MemoryLayer, ObservationType
from architect_db.models.base import Base, UUIDPrimaryKeyMixin


class KnowledgeEntry(UUIDPrimaryKeyMixin, Base):
    """Persistent knowledge item (L1-L4 layers).

    Maps to the ``knowledge_entries`` table.
    """

    __tablename__ = "knowledge_entries"

    layer: Mapped[str] = mapped_column(
        sa.Enum(MemoryLayer, native_enum=False, length=64), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(
        sa.Enum(ContentType, native_enum=False, length=64), nullable=False
    )

    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_tag: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    tags: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    # pgvector embedding stored as raw JSONB (vector type added via migration raw SQL)
    embedding: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)

    parent_id: Mapped[str | None] = mapped_column(
        Text, sa.ForeignKey("knowledge_entries.id"), nullable=True
    )
    superseded_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<KnowledgeEntry id={self.id!r} topic={self.topic!r} layer={self.layer!r}>"


class KnowledgeObservation(UUIDPrimaryKeyMixin, Base):
    """Raw observation before compression into a pattern.

    Maps to the ``knowledge_observations`` table.
    """

    __tablename__ = "knowledge_observations"

    task_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    observation_type: Mapped[str] = mapped_column(
        sa.Enum(ObservationType, native_enum=False, length=64), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)

    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)

    compressed_into: Mapped[str | None] = mapped_column(
        Text, sa.ForeignKey("knowledge_entries.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<KnowledgeObservation id={self.id!r} type={self.observation_type!r}>"


class HeuristicRule(UUIDPrimaryKeyMixin, Base):
    """L3 heuristic rule: 'When X happens, do Y'.

    Maps to the ``heuristic_rules`` table.
    """

    __tablename__ = "heuristic_rules"

    condition: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    condition_structured: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    action_structured: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    domain: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    source_patterns: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<HeuristicRule id={self.id!r} domain={self.domain!r}>"


class MetaStrategy(UUIDPrimaryKeyMixin, Base):
    """L4 meta-strategy record.

    Maps to the ``meta_strategies`` table.
    """

    __tablename__ = "meta_strategies"

    strategy_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    config_patch: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="proposed")
    effectiveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<MetaStrategy id={self.id!r} type={self.strategy_type!r}>"
