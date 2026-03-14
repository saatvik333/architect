"""Spec-compliance evaluation layer."""

from __future__ import annotations

from architect_common.enums import EvalLayer, EvalVerdict
from architect_common.logging import get_logger
from architect_common.types import utcnow
from architect_sandbox_client.client import SandboxClient
from evaluation_engine.layers.base import EvalLayerBase
from evaluation_engine.models import LayerEvaluation, SpecComplianceResult

logger = get_logger(component="evaluation_engine.layers.spec_compliance")

_PYTEST_LIST_COMMAND = "cd /workspace && python -m pytest --collect-only -q 2>&1"


class SpecComplianceLayer(EvalLayerBase):
    """Checks that acceptance criteria have corresponding passing tests.

    Runs ``pytest --collect-only -q`` to enumerate all test names, then performs
    a fuzzy keyword match between each criterion and the test list.

    Verdict mapping:
    - PASS: all criteria matched (or no criteria provided)
    - FAIL_SOFT: >= 50% of criteria met
    - FAIL_HARD: < 50% of criteria met
    """

    def __init__(
        self,
        sandbox_client: SandboxClient,
        acceptance_criteria: list[str] | None = None,
    ) -> None:
        self._sandbox = sandbox_client
        self._criteria = acceptance_criteria or []

    @property
    def layer_name(self) -> EvalLayer:
        return EvalLayer.SPEC_COMPLIANCE

    async def evaluate(self, sandbox_session_id: str) -> LayerEvaluation:
        """Check spec compliance and return the layer evaluation."""
        started_at = utcnow()

        # No criteria -> trivially compliant
        if not self._criteria:
            completed_at = utcnow()
            return LayerEvaluation(
                layer=self.layer_name,
                verdict=EvalVerdict.PASS,
                details=SpecComplianceResult(),
                started_at=started_at,
                completed_at=completed_at,
            )

        session_info = await self._sandbox.get_session(sandbox_session_id)
        from architect_sandbox_client.models import ExecutionRequest

        request = ExecutionRequest(
            task_id=session_info.get("task_id", "task-000000000000"),
            agent_id=session_info.get("agent_id", "agent-000000000000"),
            commands=[_PYTEST_LIST_COMMAND],
            timeout_seconds=120,
        )
        result = await self._sandbox.execute(request)

        completed_at = utcnow()

        # Collect all test names from output
        test_names: list[str] = []
        if result.command_results:
            output = result.command_results[0].stdout or ""
            for line in output.splitlines():
                stripped = line.strip()
                # pytest --collect-only -q outputs lines like "path/test.py::test_func"
                if "::" in stripped:
                    test_names.append(stripped.lower())

        # Match criteria to tests via fuzzy keyword matching
        criteria_met: list[str] = []
        criteria_unmet: list[str] = []

        for criterion in self._criteria:
            if self._criterion_has_test(criterion, test_names):
                criteria_met.append(criterion)
            else:
                criteria_unmet.append(criterion)

        total = len(self._criteria)
        met_count = len(criteria_met)
        score = met_count / total if total > 0 else 1.0

        if met_count == total:
            verdict = EvalVerdict.PASS
        elif score >= 0.5:
            verdict = EvalVerdict.FAIL_SOFT
        else:
            verdict = EvalVerdict.FAIL_HARD

        compliance_result = SpecComplianceResult(
            criteria_total=total,
            criteria_met=met_count,
            criteria_unmet=criteria_unmet,
            compliance_score=score,
        )

        logger.info(
            "spec compliance layer complete",
            verdict=verdict,
            criteria_total=total,
            criteria_met=met_count,
            compliance_score=score,
        )

        return LayerEvaluation(
            layer=self.layer_name,
            verdict=verdict,
            details=compliance_result,
            started_at=started_at,
            completed_at=completed_at,
        )

    @staticmethod
    def _criterion_has_test(criterion: str, test_names: list[str]) -> bool:
        """Check whether any test name contains all keywords from the criterion.

        Uses a simple keyword-overlap heuristic: split the criterion into
        words, normalise to lowercase, and check if any test name contains
        all significant keywords (words longer than 2 characters).
        """
        keywords = [w.lower() for w in criterion.split() if len(w) > 2]
        if not keywords:
            return True  # Degenerate criterion — treat as met

        return any(all(kw in test_name for kw in keywords) for test_name in test_names)
