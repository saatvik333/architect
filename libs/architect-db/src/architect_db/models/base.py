"""SQLAlchemy declarative base and shared mixins."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ARCHITECT ORM models."""


class TimestampMixin:
    """Mixin that adds ``created_at`` and ``updated_at`` columns with server defaults."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """Mixin that provides a TEXT primary key ``id`` column (prefixed UUIDs)."""

    id: Mapped[str] = mapped_column(Text, primary_key=True)
