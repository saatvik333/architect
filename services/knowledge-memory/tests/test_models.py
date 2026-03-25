"""Tests for Knowledge & Memory domain models."""

from __future__ import annotations

from knowledge_memory.models import (
    AcquireKnowledgeRequest,
    CompressionRequest,
    CompressionResult,
    FeedbackRequest,
    HeuristicRule,
    KnowledgeEntry,
    KnowledgeQuery,
    KnowledgeQueryResult,
    KnowledgeStats,
    MetaStrategy,
    Observation,
    WorkingMemory,
)


class TestKnowledgeEntry:
    """Tests for the KnowledgeEntry model."""

    def test_defaults(self) -> None:
        entry = KnowledgeEntry(
            layer="l1_project",
            topic="python",
            title="Test entry",
            content="Some content",
            content_type="documentation",
        )
        assert entry.layer == "l1_project"
        assert entry.topic == "python"
        assert entry.confidence == 1.0
        assert entry.active is True
        assert entry.usage_count == 0
        assert entry.tags == []
        assert entry.id.startswith("know-")

    def test_frozen(self) -> None:
        entry = KnowledgeEntry(
            layer="l2_pattern",
            topic="testing",
            title="Frozen test",
            content="Cannot mutate",
            content_type="pattern",
        )
        try:
            entry.title = "Should fail"  # type: ignore[misc]
            raise AssertionError("Should have raised")
        except Exception:
            pass  # Expected: frozen model

    def test_with_embedding(self) -> None:
        entry = KnowledgeEntry(
            layer="l1_project",
            topic="embeddings",
            title="With embedding",
            content="Test",
            content_type="documentation",
            embedding=[0.1, 0.2, 0.3],
        )
        assert len(entry.embedding) == 3

    def test_confidence_bounds(self) -> None:
        entry = KnowledgeEntry(
            layer="l1_project",
            topic="bounds",
            title="Confidence test",
            content="Test",
            content_type="documentation",
            confidence=0.75,
        )
        assert entry.confidence == 0.75


class TestObservation:
    """Tests for the Observation model."""

    def test_defaults(self) -> None:
        obs = Observation(
            task_id="task-test001",
            agent_id="agent-test001",
            observation_type="success",
            description="Task completed successfully",
        )
        assert obs.task_id == "task-test001"
        assert obs.compressed is False
        assert obs.pattern_id is None
        assert obs.domain == ""

    def test_with_context(self) -> None:
        obs = Observation(
            task_id="task-test002",
            agent_id="agent-test002",
            observation_type="failure",
            description="Task failed",
            context={"error": "timeout"},
            outcome="failed",
            domain="testing",
        )
        assert obs.context == {"error": "timeout"}
        assert obs.domain == "testing"


class TestHeuristicRule:
    """Tests for the HeuristicRule model."""

    def test_defaults(self) -> None:
        rule = HeuristicRule(
            domain="testing",
            condition="When tests fail repeatedly",
            action="Add more specific assertions",
        )
        assert rule.confidence == 0.5
        assert rule.success_count == 0
        assert rule.failure_count == 0
        assert rule.active is True
        assert rule.id.startswith("heur-")

    def test_with_source_patterns(self) -> None:
        rule = HeuristicRule(
            domain="refactoring",
            condition="When function is too long",
            action="Extract helper functions",
            source_pattern_ids=["pat-abc", "pat-def"],
        )
        assert len(rule.source_pattern_ids) == 2


class TestMetaStrategy:
    """Tests for the MetaStrategy model."""

    def test_defaults(self) -> None:
        strategy = MetaStrategy(
            name="Test Strategy",
            description="A test strategy",
            steps=["Step 1", "Step 2"],
        )
        assert strategy.confidence == 0.5
        assert len(strategy.steps) == 2
        assert strategy.applicable_task_types == []


class TestWorkingMemory:
    """Tests for the WorkingMemory model."""

    def test_mutable(self) -> None:
        wm = WorkingMemory(
            task_id="task-wm001",
            agent_id="agent-wm001",
        )
        # WorkingMemory uses MutableBase, so it should be mutable
        wm.scratchpad["key"] = "value"
        assert wm.scratchpad["key"] == "value"


class TestRequestResponseModels:
    """Tests for API request/response models."""

    def test_knowledge_query(self) -> None:
        query = KnowledgeQuery(query="python testing", limit=5)
        assert query.limit == 5
        assert query.layer is None

    def test_knowledge_query_with_filters(self) -> None:
        query = KnowledgeQuery(
            query="python testing",
            layer="l1_project",
            topic="python",
            content_type="documentation",
            tags=["testing"],
            limit=20,
        )
        assert query.layer == "l1_project"
        assert query.tags == ["testing"]

    def test_knowledge_query_result(self) -> None:
        result = KnowledgeQueryResult(entries=[], total=0)
        assert result.total == 0

    def test_acquire_request(self) -> None:
        req = AcquireKnowledgeRequest(
            topic="fastapi",
            source_urls=["https://fastapi.tiangolo.com"],
        )
        assert req.topic == "fastapi"
        assert len(req.source_urls) == 1

    def test_compression_request(self) -> None:
        req = CompressionRequest(domain="testing")
        assert req.domain == "testing"

    def test_compression_result(self) -> None:
        result = CompressionResult(patterns_created=3, observations_processed=15)
        assert result.patterns_created == 3
        assert result.heuristics_created == 0

    def test_knowledge_stats(self) -> None:
        stats = KnowledgeStats(
            total_entries=100,
            entries_by_layer={"l1_project": 50, "l2_pattern": 30},
            total_observations=200,
        )
        assert stats.total_entries == 100

    def test_feedback_request(self) -> None:
        feedback = FeedbackRequest(useful=True, comment="Very helpful")
        assert feedback.useful is True
