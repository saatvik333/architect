"""Security Immune System ORM models for scans, findings, and policies."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from architect_common.enums import (
    FindingSeverity,
    FindingStatus,
    PolicyAction,
    ScanType,
    ScanVerdict,
)
from architect_db.models.base import Base, UUIDPrimaryKeyMixin


class SecurityScan(UUIDPrimaryKeyMixin, Base):
    """Result of a security scan operation.

    Maps to the ``security_scans`` table.
    """

    __tablename__ = "security_scans"

    scan_type: Mapped[str] = mapped_column(
        sa.Enum(ScanType, native_enum=False, length=64), nullable=False, index=True
    )
    target_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    verdict: Mapped[str] = mapped_column(
        sa.Enum(ScanVerdict, native_enum=False, length=64), nullable=False
    )
    findings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<SecurityScan id={self.id!r} type={self.scan_type!r} verdict={self.verdict!r}>"


class SecurityFinding(UUIDPrimaryKeyMixin, Base):
    """A single issue found during a security scan.

    Maps to the ``security_findings`` table.
    """

    __tablename__ = "security_findings"

    scan_id: Mapped[str] = mapped_column(
        Text,
        sa.ForeignKey("security_scans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(
        sa.Enum(FindingSeverity, native_enum=False, length=64), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(FindingStatus, native_enum=False, length=64),
        nullable=False,
        default="open",
        index=True,
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    cwe_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<SecurityFinding id={self.id!r} severity={self.severity!r} status={self.status!r}>"


class SecurityPolicy(UUIDPrimaryKeyMixin, Base):
    """A configurable security policy rule.

    Maps to the ``security_policies`` table.
    """

    __tablename__ = "security_policies"

    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    scan_type: Mapped[str] = mapped_column(
        sa.Enum(ScanType, native_enum=False, length=64), nullable=False, index=True
    )
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    action: Mapped[str] = mapped_column(
        sa.Enum(PolicyAction, native_enum=False, length=64), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<SecurityPolicy id={self.id!r} name={self.name!r} action={self.action!r}>"
