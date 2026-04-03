"""Security Immune System repositories for scans, findings, and policies."""

from __future__ import annotations

from sqlalchemy import func, select, update

from architect_db.models.security import SecurityFinding, SecurityPolicy, SecurityScan
from architect_db.repositories.base import BaseRepository


class SecurityScanRepository(BaseRepository[SecurityScan]):
    """Async repository for :class:`SecurityScan` entities."""

    model_class = SecurityScan

    async def list_by_target(self, target_id: str, *, limit: int = 100) -> list[SecurityScan]:
        stmt = (
            select(SecurityScan)
            .where(SecurityScan.target_id == target_id)
            .order_by(SecurityScan.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent(self, *, limit: int = 100) -> list[SecurityScan]:
        stmt = select(SecurityScan).order_by(SecurityScan.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class SecurityFindingRepository(BaseRepository[SecurityFinding]):
    """Async repository for :class:`SecurityFinding` entities."""

    model_class = SecurityFinding

    async def list_by_scan(self, scan_id: str) -> list[SecurityFinding]:
        stmt = (
            select(SecurityFinding)
            .where(SecurityFinding.scan_id == scan_id)
            .order_by(SecurityFinding.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_severity(self, severity: str, *, limit: int = 100) -> list[SecurityFinding]:
        stmt = (
            select(SecurityFinding)
            .where(SecurityFinding.severity == severity)
            .order_by(SecurityFinding.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_open(self, *, limit: int = 100) -> list[SecurityFinding]:
        stmt = (
            select(SecurityFinding)
            .where(SecurityFinding.status == "open")
            .order_by(SecurityFinding.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_severity(self) -> dict[str, int]:
        from sqlalchemy import case

        stmt = select(
            func.count().label("total"),
            func.count(case((SecurityFinding.severity == "critical", 1))).label("critical"),
            func.count(case((SecurityFinding.severity == "high", 1))).label("high"),
            func.count(case((SecurityFinding.severity == "medium", 1))).label("medium"),
            func.count(case((SecurityFinding.severity == "low", 1))).label("low"),
            func.count(case((SecurityFinding.severity == "info", 1))).label("info"),
        ).select_from(SecurityFinding)

        result = await self._session.execute(stmt)
        row = result.one()
        return {
            "total": row.total or 0,
            "critical": row.critical or 0,
            "high": row.high or 0,
            "medium": row.medium or 0,
            "low": row.low or 0,
            "info": row.info or 0,
        }

    async def update_status(self, finding_id: str, *, status: str) -> SecurityFinding | None:
        stmt = (
            update(SecurityFinding)
            .where(SecurityFinding.id == finding_id)
            .values(status=status)
            .returning(SecurityFinding)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalars().first()


class SecurityPolicyRepository(BaseRepository[SecurityPolicy]):
    """Async repository for :class:`SecurityPolicy` entities."""

    model_class = SecurityPolicy

    async def list_enabled(self) -> list[SecurityPolicy]:
        stmt = (
            select(SecurityPolicy)
            .where(SecurityPolicy.enabled.is_(True))
            .order_by(SecurityPolicy.name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> SecurityPolicy | None:
        stmt = select(SecurityPolicy).where(SecurityPolicy.name == name)
        result = await self._session.execute(stmt)
        return result.scalars().first()
