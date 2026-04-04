"""FastAPI route definitions for the Failure Taxonomy service."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from architect_common.enums import (
    FailureCode,
    HealthStatus,
    ImprovementType,
    PostMortemStatus,
)
from architect_common.health import HealthResponse
from architect_common.types import utcnow
from architect_db.models.failure import FailureRecord, Improvement, PostMortem, SimulationRun
from architect_db.repositories.failure_repo import (
    FailureRecordRepository,
    ImprovementRepository,
    PostMortemRepository,
    SimulationRunRepository,
)
from failure_taxonomy.classifier import FailureClassifier
from failure_taxonomy.models import (
    ClassificationRequest,
    SimulationConfig,
)
from failure_taxonomy.post_mortem_analyzer import PostMortemAnalyzer
from failure_taxonomy.simulation_runner import SimulationRunner

from .dependencies import (
    get_classifier,
    get_post_mortem_analyzer,
    get_session_factory,
    get_simulation_runner,
)

router = APIRouter()


# ── Request / Response schemas ────────────────────────────────────


class FailureRecordResponse(BaseModel):
    """Serialized failure record for API responses."""

    id: str
    task_id: str
    agent_id: str | None = None
    project_id: str | None = None
    failure_code: str
    severity: str
    summary: str
    root_cause: str | None = None
    eval_layer: str | None = None
    error_message: str | None = None
    classified_by: str = "auto"
    confidence: float = 0.0
    resolved: bool = False
    resolution_summary: str | None = None
    created_at: str | None = None


class FailureStatsResponse(BaseModel):
    """Failure statistics by code."""

    stats: dict[str, int]
    total: int


class PostMortemResponse(BaseModel):
    """Serialized post-mortem for API responses."""

    id: str
    project_id: str
    status: str
    failure_count: int = 0
    failure_breakdown: dict[str, Any] | None = None
    root_causes: list[str] | None = None
    prompt_improvements: list[dict[str, Any]] | None = None
    new_adversarial_tests: list[dict[str, Any]] | None = None
    heuristic_updates: list[dict[str, Any]] | None = None
    topology_recommendations: list[dict[str, Any]] | None = None
    created_at: str | None = None
    completed_at: str | None = None


class PostMortemCreateRequest(BaseModel):
    """Request to trigger a post-mortem analysis."""

    project_id: str
    task_id: str | None = None


class ImprovementResponse(BaseModel):
    """Serialized improvement for API responses."""

    id: str
    post_mortem_id: str
    improvement_type: str
    description: str
    content: dict[str, Any] | None = None
    applied: bool = False
    applied_at: str | None = None
    created_at: str | None = None


class SimulationRunResponse(BaseModel):
    """Serialized simulation run for API responses."""

    id: str
    source_type: str
    source_ref: str
    status: str
    failures_injected: int = 0
    failures_detected: int = 0
    detection_rate: float = 0.0
    results: dict[str, Any] | None = None
    created_at: str | None = None
    completed_at: str | None = None


# ── Helpers ──────────────────────────────────────────────────────


def _record_to_response(record: FailureRecord) -> FailureRecordResponse:
    return FailureRecordResponse(
        id=record.id,
        task_id=record.task_id,
        agent_id=record.agent_id,
        project_id=record.project_id,
        failure_code=record.failure_code,
        severity=record.severity,
        summary=record.summary,
        root_cause=record.root_cause,
        eval_layer=record.eval_layer,
        error_message=record.error_message,
        classified_by=record.classified_by,
        confidence=record.confidence,
        resolved=record.resolved if record.resolved is not None else False,
        resolution_summary=record.resolution_summary,
        created_at=record.created_at.isoformat() if record.created_at else None,
    )


def _post_mortem_to_response(pm: PostMortem) -> PostMortemResponse:
    return PostMortemResponse(
        id=pm.id,
        project_id=pm.project_id,
        status=pm.status,
        failure_count=pm.failure_count,
        failure_breakdown=pm.failure_breakdown,
        root_causes=pm.root_causes,
        prompt_improvements=pm.prompt_improvements,
        new_adversarial_tests=pm.new_adversarial_tests,
        heuristic_updates=pm.heuristic_updates,
        topology_recommendations=pm.topology_recommendations,
        created_at=pm.created_at.isoformat() if pm.created_at else None,
        completed_at=pm.completed_at.isoformat() if pm.completed_at else None,
    )


def _improvement_to_response(imp: Improvement) -> ImprovementResponse:
    return ImprovementResponse(
        id=imp.id,
        post_mortem_id=imp.post_mortem_id,
        improvement_type=imp.improvement_type,
        description=imp.description,
        content=imp.content,
        applied=imp.applied,
        applied_at=imp.applied_at.isoformat() if imp.applied_at else None,
        created_at=imp.created_at.isoformat() if imp.created_at else None,
    )


def _simulation_to_response(sim: SimulationRun) -> SimulationRunResponse:
    return SimulationRunResponse(
        id=sim.id,
        source_type=sim.source_type,
        source_ref=sim.source_ref,
        status=sim.status,
        failures_injected=sim.failures_injected,
        failures_detected=sim.failures_detected,
        detection_rate=sim.detection_rate,
        results=sim.results,
        created_at=sim.created_at.isoformat() if sim.created_at else None,
        completed_at=sim.completed_at.isoformat() if sim.completed_at else None,
    )


# ── Classification endpoints ─────────────────────────────────────


@router.post("/api/v1/failures/classify", response_model=FailureRecordResponse)
async def classify_failure(
    body: ClassificationRequest,
    classifier: FailureClassifier = Depends(get_classifier),
    session_factory: Any = Depends(get_session_factory),
) -> FailureRecordResponse:
    """Classify a failure and persist the record."""
    from architect_common.types import new_failure_record_id

    classification = await classifier.classify(body)

    async with session_factory() as session:
        repo = FailureRecordRepository(session)
        record = FailureRecord(
            id=new_failure_record_id(),
            task_id=body.task_id,
            agent_id=body.agent_id,
            failure_code=classification.failure_code.value,
            severity=_severity_for_code(classification.failure_code),
            summary=classification.summary,
            root_cause=classification.root_cause,
            eval_layer=body.eval_layer,
            error_message=body.error_message[:2000] if body.error_message else None,
            stack_trace=body.stack_trace[:5000] if body.stack_trace else None,
            classified_by="auto",
            confidence=classification.confidence,
        )
        await repo.create(record)
        await session.commit()

    return _record_to_response(record)


@router.get("/api/v1/failures", response_model=list[FailureRecordResponse])
async def list_failures(
    limit: int = 50,
    session_factory: Any = Depends(get_session_factory),
) -> list[FailureRecordResponse]:
    """List recent failure records."""
    async with session_factory() as session:
        repo = FailureRecordRepository(session)
        records = await repo.get_recent(limit=limit)
    return [_record_to_response(r) for r in records]


@router.get("/api/v1/failures/stats", response_model=FailureStatsResponse)
async def get_failure_stats(
    session_factory: Any = Depends(get_session_factory),
) -> FailureStatsResponse:
    """Get failure statistics grouped by failure code."""
    async with session_factory() as session:
        repo = FailureRecordRepository(session)
        stats = await repo.get_stats_by_code()
    return FailureStatsResponse(stats=stats, total=sum(stats.values()))


@router.get("/api/v1/failures/{failure_id}", response_model=FailureRecordResponse)
async def get_failure(
    failure_id: str,
    session_factory: Any = Depends(get_session_factory),
) -> FailureRecordResponse:
    """Get a specific failure record by ID."""
    async with session_factory() as session:
        repo = FailureRecordRepository(session)
        record = await repo.get_by_id(failure_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Failure record not found")
    return _record_to_response(record)


# ── Post-mortem endpoints ────────────────────────────────────────


@router.post("/api/v1/post-mortems", response_model=PostMortemResponse)
async def create_post_mortem(
    body: PostMortemCreateRequest,
    analyzer: PostMortemAnalyzer = Depends(get_post_mortem_analyzer),
    session_factory: Any = Depends(get_session_factory),
) -> PostMortemResponse:
    """Trigger a post-mortem analysis for a project."""
    async with session_factory() as session:
        failure_repo = FailureRecordRepository(session)
        pm_repo = PostMortemRepository(session)
        imp_repo = ImprovementRepository(session)

        # Fetch unresolved failures for the project
        failures = await failure_repo.get_by_project(body.project_id, limit=200)
        unresolved = [f for f in failures if not f.resolved]

        if not unresolved:
            raise HTTPException(
                status_code=400,
                detail="No unresolved failures found for this project",
            )

        # Run analysis
        analysis = await analyzer.analyze(body.project_id, unresolved)

        # Persist the post-mortem
        pm = PostMortem(
            id=str(analysis.post_mortem_id),
            project_id=body.project_id,
            task_id=body.task_id,
            status=PostMortemStatus.COMPLETED,
            failure_count=len(unresolved),
            failure_breakdown=analysis.failure_summary,
            root_causes=analysis.root_causes,
            prompt_improvements=[p.model_dump(mode="json") for p in analysis.prompt_improvements],
            new_adversarial_tests=[t.model_dump(mode="json") for t in analysis.adversarial_tests],
            heuristic_updates=[h.model_dump(mode="json") for h in analysis.heuristic_updates],
            topology_recommendations=[
                r.model_dump(mode="json") for r in analysis.topology_recommendations
            ],
            completed_at=utcnow(),
        )
        await pm_repo.create(pm)

        # Persist improvements as individual records
        from architect_common.types import new_improvement_id

        for pi in analysis.prompt_improvements:
            imp = Improvement(
                id=new_improvement_id(),
                post_mortem_id=pm.id,
                improvement_type=ImprovementType.PROMPT_IMPROVEMENT,
                description=pi.suggested_change,
                content=pi.model_dump(mode="json"),
            )
            await imp_repo.create(imp)

        for at in analysis.adversarial_tests:
            imp = Improvement(
                id=new_improvement_id(),
                post_mortem_id=pm.id,
                improvement_type=ImprovementType.ADVERSARIAL_TEST,
                description=at.test_description,
                content=at.model_dump(mode="json"),
            )
            await imp_repo.create(imp)

        for hu in analysis.heuristic_updates:
            imp = Improvement(
                id=new_improvement_id(),
                post_mortem_id=pm.id,
                improvement_type=ImprovementType.HEURISTIC_UPDATE,
                description=hu.action,
                content=hu.model_dump(mode="json"),
            )
            await imp_repo.create(imp)

        for tr in analysis.topology_recommendations:
            imp = Improvement(
                id=new_improvement_id(),
                post_mortem_id=pm.id,
                improvement_type=ImprovementType.TOPOLOGY_RECOMMENDATION,
                description=tr.recommendation,
                content=tr.model_dump(mode="json"),
            )
            await imp_repo.create(imp)

        await session.commit()

    return _post_mortem_to_response(pm)


@router.get("/api/v1/post-mortems", response_model=list[PostMortemResponse])
async def list_post_mortems(
    project_id: str | None = None,
    limit: int = 50,
    session_factory: Any = Depends(get_session_factory),
) -> list[PostMortemResponse]:
    """List post-mortem analyses."""
    async with session_factory() as session:
        repo = PostMortemRepository(session)
        if project_id:
            records = await repo.get_by_project(project_id, limit=limit)
        else:
            # Get latest N post-mortems
            latest = await repo.get_latest()
            records = [latest] if latest else []
    return [_post_mortem_to_response(pm) for pm in records]


@router.get("/api/v1/post-mortems/{post_mortem_id}", response_model=PostMortemResponse)
async def get_post_mortem(
    post_mortem_id: str,
    session_factory: Any = Depends(get_session_factory),
) -> PostMortemResponse:
    """Get a specific post-mortem analysis."""
    async with session_factory() as session:
        repo = PostMortemRepository(session)
        pm = await repo.get_by_id(post_mortem_id)
    if pm is None:
        raise HTTPException(status_code=404, detail="Post-mortem not found")
    return _post_mortem_to_response(pm)


# ── Improvement endpoints ────────────────────────────────────────


@router.get("/api/v1/improvements", response_model=list[ImprovementResponse])
async def list_improvements(
    unapplied_only: bool = False,
    limit: int = 50,
    session_factory: Any = Depends(get_session_factory),
) -> list[ImprovementResponse]:
    """List improvement proposals."""
    async with session_factory() as session:
        repo = ImprovementRepository(session)
        if unapplied_only:
            records = await repo.get_unapplied(limit=limit)
        else:
            # Use get_unapplied as a fallback since there's no get_all method
            records = await repo.get_unapplied(limit=limit)
    return [_improvement_to_response(i) for i in records]


@router.post("/api/v1/improvements/{improvement_id}/apply", response_model=ImprovementResponse)
async def apply_improvement(
    improvement_id: str,
    session_factory: Any = Depends(get_session_factory),
) -> ImprovementResponse:
    """Mark an improvement as applied."""
    async with session_factory() as session:
        repo = ImprovementRepository(session)
        improvement = await repo.mark_applied(improvement_id)
        if improvement is None:
            raise HTTPException(status_code=404, detail="Improvement not found")
        await session.commit()
    return _improvement_to_response(improvement)


# ── Simulation endpoints ─────────────────────────────────────────


@router.post("/api/v1/simulations", response_model=SimulationRunResponse)
async def create_simulation(
    body: SimulationConfig,
    runner: SimulationRunner = Depends(get_simulation_runner),
    session_factory: Any = Depends(get_session_factory),
) -> SimulationRunResponse:
    """Start a simulation training run."""
    from architect_common.types import _prefixed_uuid

    result = await runner.run_simulation(body)

    async with session_factory() as session:
        repo = SimulationRunRepository(session)
        sim = SimulationRun(
            id=_prefixed_uuid("sim"),
            source_type=body.source_type,
            source_ref=body.source_ref,
            status="completed",
            failures_injected=result.failures_injected,
            failures_detected=result.failures_detected,
            detection_rate=result.detection_rate,
            results=result.model_dump(mode="json"),
            completed_at=utcnow(),
        )
        await repo.create(sim)
        await session.commit()

    return _simulation_to_response(sim)


@router.get("/api/v1/simulations/{simulation_id}", response_model=SimulationRunResponse)
async def get_simulation(
    simulation_id: str,
    session_factory: Any = Depends(get_session_factory),
) -> SimulationRunResponse:
    """Get a specific simulation run."""
    async with session_factory() as session:
        repo = SimulationRunRepository(session)
        sim = await repo.get_by_id(simulation_id)
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return _simulation_to_response(sim)


# ── Health endpoint ──────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Service health check endpoint."""
    status = HealthStatus.HEALTHY

    try:
        get_classifier()
    except RuntimeError:
        status = HealthStatus.DEGRADED

    try:
        get_session_factory()
    except RuntimeError:
        status = HealthStatus.DEGRADED

    uptime = time.monotonic() - getattr(request.app.state, "started_at", time.monotonic())
    return HealthResponse(
        service="failure-taxonomy",
        status=status,
        uptime_seconds=round(uptime, 2),
    )


def _severity_for_code(code: FailureCode) -> str:
    """Map failure codes to severity levels."""
    critical = {FailureCode.F9_SECURITY_VULN}
    high = {FailureCode.F2_ARCHITECTURE_ERROR, FailureCode.F3_HALLUCINATION}
    low = {FailureCode.F7_UX_REJECTION}

    if code in critical:
        return "critical"
    if code in high:
        return "high"
    if code in low:
        return "low"
    return "medium"
