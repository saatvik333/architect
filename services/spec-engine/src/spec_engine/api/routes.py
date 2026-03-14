"""FastAPI route definitions for the Spec Engine."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from architect_common.enums import HealthStatus
from spec_engine.api.dependencies import get_spec_parser
from spec_engine.models import SpecResult
from spec_engine.parser import SpecParser
from spec_engine.validator import SpecValidator

router = APIRouter()

# ── In-memory spec store (production would use a database) ─────────────
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
        validation_issues = _validator.validate(result.spec)
        # Update the store with the new result
        _spec_store[result.spec.id] = {
            "result": result.model_dump(mode="json"),
            "raw_text": raw_text,
        }
        # Remove the old entry if the ID changed
        if result.spec.id != spec_id:
            _spec_store.pop(spec_id, None)

    return SpecResponse(
        result=result.model_dump(mode="json"),
        validation_issues=validation_issues,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check endpoint."""
    return HealthResponse(status=HealthStatus.HEALTHY)
