"""Tests for enum definitions."""

from architect_common.enums import (
    AgentType,
    EvalLayer,
    EvalVerdict,
    EventType,
    ModelTier,
    ProposalVerdict,
    SandboxStatus,
    StatusEnum,
    TaskType,
)


class TestEnums:
    def test_status_enum_values(self) -> None:
        assert StatusEnum.PENDING == "pending"
        assert StatusEnum.COMPLETED == "completed"

    def test_proposal_verdict_values(self) -> None:
        assert ProposalVerdict.ACCEPTED == "accepted"
        assert ProposalVerdict.REJECTED == "rejected"

    def test_eval_verdict_values(self) -> None:
        assert EvalVerdict.PASS == "pass"
        assert EvalVerdict.FAIL_HARD == "fail_hard"

    def test_sandbox_status_values(self) -> None:
        assert SandboxStatus.READY == "ready"
        assert SandboxStatus.DESTROYED == "destroyed"

    def test_event_type_has_dotted_values(self) -> None:
        assert "." in EventType.TASK_CREATED.value
        assert EventType.TASK_CREATED == "task.created"

    def test_eval_layer_count(self) -> None:
        assert len(EvalLayer) == 7

    def test_model_tier_count(self) -> None:
        assert len(ModelTier) == 3

    def test_all_enums_importable(self) -> None:
        """Verify all enum types used in the tests are valid StrEnums."""
        for enum_cls in (
            StatusEnum,
            ProposalVerdict,
            EvalVerdict,
            SandboxStatus,
            EventType,
            EvalLayer,
            ModelTier,
            AgentType,
            TaskType,
        ):
            # Every member value should be a string (StrEnum guarantee)
            for member in enum_cls:
                assert isinstance(member.value, str)
