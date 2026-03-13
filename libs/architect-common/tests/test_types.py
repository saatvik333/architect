"""Tests for core types and ID generation."""

from architect_common.types import (
    new_agent_id,
    new_event_id,
    new_proposal_id,
    new_task_id,
)


def test_agent_id_has_prefix() -> None:
    aid = new_agent_id()
    assert aid.startswith("agent-")
    assert len(aid) == 18  # "agent-" (6) + 12 hex chars


def test_task_id_has_prefix() -> None:
    tid = new_task_id()
    assert tid.startswith("task-")
    assert len(tid) == 17


def test_proposal_id_has_prefix() -> None:
    pid = new_proposal_id()
    assert pid.startswith("prop-")
    assert len(pid) == 17


def test_event_id_has_prefix() -> None:
    eid = new_event_id()
    assert eid.startswith("evt-")
    assert len(eid) == 16


def test_ids_are_unique() -> None:
    ids = {new_task_id() for _ in range(100)}
    assert len(ids) == 100
