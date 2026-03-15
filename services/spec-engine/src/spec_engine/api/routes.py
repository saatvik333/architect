"""FastAPI route definitions for the Spec Engine."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from architect_common.enums import HealthStatus
from architect_llm.client import LLMClient
from spec_engine.api.dependencies import get_llm_client, get_spec_parser
from spec_engine.models import SpecResult
from spec_engine.parser import SpecParser
from spec_engine.scope_governor import ScopeGovernor
from spec_engine.stakeholder_simulator import StakeholderSimulator
from spec_engine.validator import SpecValidator

router = APIRouter()

# ── Spec store — in-memory for Phase 2, to be replaced with Postgres in Phase 3 ──
_spec_store: dict[str, dict[str, Any]] = {}

_validator = SpecValidator()


# ── Request / Response schemas ────────────────────────────────────────


class CreateSpecRequest(BaseModel):
    """Request body for POST /api/v1/specs."""

    raw_text: str = Field(description="Natural-language requirement text.")


class ClarifyRequest(BaseModel):
    """Request body for POST /api/v1/specs/{spec_id}/clarify."""

    clarifications: dict[str, str] = Field(
        description="Mapping of question text to answer text.",
    )


class SpecResponse(BaseModel):
    """Response body wrapping a SpecResult."""

    result: dict[str, Any]
    validation_issues: list[str] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    """Response body for POST /api/v1/specs/{spec_id}/review."""

    stakeholder_review: dict[str, Any]
    scope_report: dict[str, Any]


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    service: str = "spec-engine"
    status: HealthStatus


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/api/v1/specs", response_model=SpecResponse)
async def create_spec(
    body: CreateSpecRequest,
    parser: SpecParser = Depends(get_spec_parser),
) -> SpecResponse:
    """Parse natural-language text into a formal specification."""
    result = await parser.parse(body.raw_text)
    validation_issues: list[str] = []

    if result.spec is not None:
        validation_issues = _validator.validate(result.spec)
        # Store the spec for later retrieval
        _spec_store[result.spec.id] = {
            "result": result.model_dump(mode="json"),
            "raw_text": body.raw_text,
        }

    return SpecResponse(
        result=result.model_dump(mode="json"),
        validation_issues=validation_issues,
    )


@router.get("/api/v1/specs/{spec_id}", response_model=SpecResponse)
async def get_spec(spec_id: str) -> SpecResponse:
    """Retrieve a previously parsed specification by ID."""
    stored = _spec_store.get(spec_id)
    if stored is None:
        raise HTTPException(
            status_code=404,
            detail=f"No spec found for id={spec_id}",
        )

    result = SpecResult.model_validate(stored["result"])
    validation_issues: list[str] = []
    if result.spec is not None:
        validation_issues = _validator.validate(result.spec)

    return SpecResponse(
        result=stored["result"],
        validation_issues=validation_issues,
    )


@router.post("/api/v1/specs/{spec_id}/clarify", response_model=SpecResponse)
async def clarify_spec(
    spec_id: str,
    body: ClarifyRequest,
    parser: SpecParser = Depends(get_spec_parser),
) -> SpecResponse:
    """Provide clarifications for a spec that needs more information."""
    stored = _spec_store.get(spec_id)
    if stored is None:
        raise HTTPException(
            status_code=404,
            detail=f"No spec found for id={spec_id}",
        )

    raw_text = stored["raw_text"]
    result = await parser.parse(raw_text, clarifications=body.clarifications)
    validation_issues: list[str] = []

    if result.spec is not None:
        # Preserve the original spec ID — the LLM may generate a new one,
        # but clients reference this spec by the original URL path ID.
        spec = result.spec.model_copy(update={"id": spec_id})
        result = result.model_copy(update={"spec": spec})
        validation_issues = _validator.validate(spec)
        _spec_store[spec_id] = {
            "result": result.model_dump(mode="json"),
            "raw_text": raw_text,
        }

    return SpecResponse(
        result=result.model_dump(mode="json"),
        validation_issues=validation_issues,
    )


@router.post("/api/v1/specs/{spec_id}/review", response_model=ReviewResponse)
async def review_spec(
    spec_id: str,
    llm_client: LLMClient = Depends(get_llm_client),
) -> ReviewResponse:
    """Run stakeholder simulation and scope evaluation on an existing spec."""
    stored = _spec_store.get(spec_id)
    if stored is None:
        raise HTTPException(
            status_code=404,
            detail=f"No spec found for id={spec_id}",
        )

    result = SpecResult.model_validate(stored["result"])
    if result.spec is None:
        raise HTTPException(
            status_code=400,
            detail="Cannot review a spec that has not been fully parsed.",
        )

    simulator = StakeholderSimulator(llm_client)
    governor = ScopeGovernor(llm_client)

    stakeholder_review = await simulator.simulate(result.spec)
    scope_report = await governor.evaluate(result.spec)

    return ReviewResponse(
        stakeholder_review=stakeholder_review.model_dump(mode="json"),
        scope_report=scope_report.model_dump(mode="json"),
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check endpoint."""
    return HealthResponse(status=HealthStatus.HEALTHY)
