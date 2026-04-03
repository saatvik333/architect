"""Domain models for the Knowledge & Memory system."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from architect_common.enums import ContentType, MemoryLayer, ObservationType, TaskType
from architect_common.types import (
    AgentId,
    ArchitectBase,
    HeuristicId,
    KnowledgeId,
    MutableBase,
    PatternId,
    TaskId,
    new_heuristic_id,
    new_knowledge_id,
    utcnow,
)

# ── Domain models (frozen) ────────────────────────────────────────


class KnowledgeEntry(ArchitectBase):
    """A single piece of stored knowledge at any layer."""

    id: KnowledgeId = Field(default_factory=new_knowledge_id)
    layer: MemoryLayer
    topic: str
    title: str
    content: str
    content_type: ContentType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] = Field(default_factory=list)
    version_tag: str = ""
    source: str = ""
    usage_count: int = 0
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Observation(ArchitectBase):
    """A raw observation from task execution."""

    id: KnowledgeId = Field(default_factory=new_knowledge_id)
    task_id: TaskId
    agent_id: AgentId
    observation_type: ObservationType
    description: str
    context: dict[str, object] = Field(default_factory=dict)
    outcome: str = ""
    domain: str = ""
    project_id: str = Field(default="", description="Project scope; empty = global.")
    embedding: list[float] = Field(default_factory=list)
    compressed: bool = False
    pattern_id: PatternId | None = None
    created_at: datetime = Field(default_factory=utcnow)


class HeuristicRule(ArchitectBase):
    """A heuristic rule synthesized from patterns."""

    id: HeuristicId = Field(default_factory=new_heuristic_id)
    domain: str
    condition: str
    action: str
    rationale: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    success_count: int = 0
    failure_count: int = 0
    active: bool = True
    project_id: str = Field(default="", description="Project scope; empty = global.")
    source_pattern_ids: list[PatternId] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class MetaStrategy(ArchitectBase):
    """A high-level meta-strategy derived from heuristics."""

    id: KnowledgeId = Field(default_factory=new_knowledge_id)
    name: str
    description: str
    applicable_task_types: list[TaskType] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    source_heuristic_ids: list[HeuristicId] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    # Phase 4: A/B testing and validation
    validation_status: str = Field(
        default="unvalidated",
        description="Validation state: unvalidated, testing, validated, rejected.",
    )
    tasks_applied: int = Field(default=0, ge=0)
    tasks_succeeded: int = Field(default=0, ge=0)
    tasks_failed: int = Field(default=0, ge=0)
    ab_test_group: str = Field(default="", description="'control' or 'experiment'.")
    ab_test_id: str = Field(default="", description="Links strategies being compared.")
    created_at: datetime = Field(default_factory=utcnow)


# ── Mutable state ────────────────────────────────────────────────


class WorkingMemory(MutableBase):
    """L0 working memory for an active task-agent pair."""

    task_id: TaskId
    agent_id: AgentId
    scratchpad: dict[str, object] = Field(default_factory=dict)
    context_entries: list[KnowledgeId] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    last_accessed: datetime = Field(default_factory=utcnow)


# ── API request / response models ────────────────────────────────


class KnowledgeQuery(ArchitectBase):
    """Request body for querying knowledge."""

    query: str
    layer: MemoryLayer | None = None
    topic: str | None = None
    content_type: ContentType | None = None
    tags: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=100)


class KnowledgeQueryResult(ArchitectBase):
    """Response for a knowledge query."""

    entries: list[KnowledgeEntry] = Field(default_factory=list)
    total: int = 0


class AcquireKnowledgeRequest(ArchitectBase):
    """Request body for triggering knowledge acquisition."""

    topic: str
    source_urls: list[str] = Field(default_factory=list)
    layer: MemoryLayer = MemoryLayer.L1_PROJECT
    tags: list[str] = Field(default_factory=list)


class CompressionRequest(ArchitectBase):
    """Request body for triggering the compression pipeline."""

    domain: str | None = None


class CompressionResult(ArchitectBase):
    """Result of a compression pipeline run."""

    patterns_created: int = 0
    heuristics_created: int = 0
    strategies_proposed: int = 0
    observations_processed: int = 0


class KnowledgeStats(ArchitectBase):
    """Statistics about the knowledge store."""

    total_entries: int = 0
    entries_by_layer: dict[str, int] = Field(default_factory=dict)
    total_observations: int = 0
    total_heuristics: int = 0
    total_meta_strategies: int = 0


class FeedbackRequest(ArchitectBase):
    """Request body for providing feedback on a knowledge entry."""

    useful: bool = True
    comment: str = ""
