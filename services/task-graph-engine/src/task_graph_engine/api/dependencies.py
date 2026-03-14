"""FastAPI dependency injection for the Task Graph Engine."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from architect_db.engine import create_engine, create_session_factory
from architect_db.repositories.task_repo import TaskRepository
from architect_db.session import get_session
from architect_events.publisher import EventPublisher
from task_graph_engine.config import TaskGraphEngineConfig
from task_graph_engine.decomposer import TaskDecomposer
from task_graph_engine.graph import TaskDAG
from task_graph_engine.scheduler import TaskScheduler


@lru_cache(maxsize=1)
def get_config() -> TaskGraphEngineConfig:
    """Return the singleton service configuration."""
    return TaskGraphEngineConfig()


# ── Database ──────────────────────────────────────────────────────

_session_factory = None


def _get_session_factory(config: TaskGraphEngineConfig = Depends(get_config)) -> Any:
    """Lazily create and cache the async session factory."""
    global _session_factory
    if _session_factory is None:
        engine = create_engine(
            config.postgres.dsn,
            pool_min=config.postgres.pool_min,
            pool_max=config.postgres.pool_max,
        )
        _session_factory = create_session_factory(engine)
    return _session_factory


async def get_db_session(
    factory: Any = Depends(_get_session_factory),
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional database session."""
    async for session in get_session(factory):
        yield session


# ── Repositories ──────────────────────────────────────────────────


def get_task_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskRepository:
    """Provide a TaskRepository bound to the current session."""
    return TaskRepository(session)


# ── Event Publisher ───────────────────────────────────────────────

_event_publisher: EventPublisher | None = None


async def get_event_publisher(
    config: Annotated[TaskGraphEngineConfig, Depends(get_config)],
) -> EventPublisher:
    """Provide the singleton EventPublisher (lazily connected)."""
    global _event_publisher
    if _event_publisher is None:
        _event_publisher = EventPublisher(config.redis.url)
        await _event_publisher.connect()
    return _event_publisher


# ── DAG (in-memory per-process) ───────────────────────────────────

_task_dag = TaskDAG()


def get_task_dag() -> TaskDAG:
    """Return the in-process TaskDAG instance."""
    return _task_dag


# ── Decomposer ────────────────────────────────────────────────────


def get_decomposer() -> TaskDecomposer:
    """Provide a TaskDecomposer (no LLM client in Phase 1)."""
    return TaskDecomposer()


# ── Scheduler ─────────────────────────────────────────────────────


async def get_scheduler(
    task_repo: Annotated[TaskRepository, Depends(get_task_repo)],
    event_publisher: Annotated[EventPublisher, Depends(get_event_publisher)],
    dag: Annotated[TaskDAG, Depends(get_task_dag)],
) -> TaskScheduler:
    """Provide a TaskScheduler wired to the repo, publisher, and DAG."""
    return TaskScheduler(task_repo=task_repo, event_publisher=event_publisher, dag=dag)
