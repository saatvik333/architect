"""Regression testing evaluation layer."""

from __future__ import annotations

import re

from architect_common.enums import EvalLayer, EvalVerdict
from architect_common.logging import get_logger
from architect_common.types import utcnow
from architect_sandbox_client.client import SandboxClient
from evaluation_engine.layers.base import EvalLayerBase
from evaluation_engine.models import LayerEvaluation, RegressionResult

logger = get_logger(component="evaluation_engine.layers.regression")

_PYTEST_COMMAND = "cd /workspace && python -m pytest --tb=short -q 2>&1"

_SUMMARY_RE = re.compile(
    r"(?:(\d+) passed)?"
    r"(?:,?\s*(\d+) failed)?"
    r"(?:,?\s*(\d+) skipped)?"
    r"(?:,?\s*(\d+) error)?"
    r"\s+in\s+([\d.]+)s"
)


class RegressionLayer(EvalLayerBase):
    """Runs the full test suite and compares against a known baseline.

    Verdict mapping:
    - PASS: all tests pass and count >= baseline (or baseline is 0)
    - FAIL_SOFT: all tests pass but count dropped below baseline
    - FAIL_HARD: regressions found (test failures)
    """

    def __init__(
        self,
        sandbox_client: SandboxClient,
        baseline_test_count: int = 0,
    ) -> None:
        self._sandbox = sandbox_client
        self._baseline = baseline_test_count

    @property
    def layer_name(self) -> EvalLayer:
        return EvalLayer.REGRESSION

    async def evaluate(self, sandbox_session_id: str) -> LayerEvaluation:
        """Run regression tests and return the layer evaluation."""
        started_at = utcnow()

        session_info = await self._sandbox.get_session(sandbox_session_id)
        from architect_sandbox_client.models import ExecutionRequest

        request = ExecutionRequest(
            task_id=session_info.get("task_id", "task-000000000000"),
            agent_id=session_info.get("agent_id", "agent-000000000000"),
            commands=[_PYTEST_COMMAND],
            timeout_seconds=600,
        )
        result = await self._sandbox.execute(request)

        completed_at = utcnow()
        duration = (completed_at - started_at).total_seconds()

        passed = 0
        failed = 0
        errors = 0
        test_duration = duration
        regression_details: list[str] = []

        if result.command_results:
            cmd_result = result.command_results[0]
            output = cmd_result.stdout or cmd_result.stderr or ""

            for line in output.splitlines():
                match = _SUMMARY_RE.search(line)
                if match:
                    passed = int(match.group(1) or 0)
                    failed = int(match.group(2) or 0)
                    errors = int(match.group(4) or 0)
                    test_duration = float(match.group(5) or duration)
                    break

            # Collect failure lines as regression details
            for line in output.splitlines():
                stripped = line.strip()
                if stripped.startswith("FAILED"):
                    regression_details.append(stripped)

        total = passed + failed + errors
        regressions = failed + errors

        # Determine verdict
        if regressions > 0:
            verdict = EvalVerdict.FAIL_HARD
        elif self._baseline > 0 and total < self._baseline:
            verdict = EvalVerdict.FAIL_SOFT
        else:
            verdict = EvalVerdict.PASS

        reg_result = RegressionResult(
            baseline_test_count=self._baseline,
            regressions_found=regressions,
            regression_details=regression_details,
            duration_seconds=test_duration,
        )

        logger.info(
            "regression layer complete",
            verdict=verdict,
            total=total,
            passed=passed,
            regressions=regressions,
            baseline=self._baseline,
            duration_seconds=test_duration,
        )

        return LayerEvaluation(
            layer=self.layer_name,
            verdict=verdict,
            details=reg_result,
            started_at=started_at,
            completed_at=completed_at,
        )
