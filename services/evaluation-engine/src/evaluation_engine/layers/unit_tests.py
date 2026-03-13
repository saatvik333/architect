"""Unit test evaluation layer."""

from __future__ import annotations

import re

from architect_common.enums import EvalLayer, EvalVerdict
from architect_common.logging import get_logger
from architect_common.types import utcnow
from architect_sandbox_client.client import SandboxClient
from evaluation_engine.layers.base import EvalLayerBase
from evaluation_engine.models import LayerEvaluation, TestFailureDetail, UnitTestResult

logger = get_logger(component="evaluation_engine.layers.unit_tests")

_PYTEST_COMMAND = "cd /workspace && python -m pytest --tb=short -q 2>&1"

# Regex patterns for parsing pytest summary line, e.g.:
#   "5 passed, 2 failed, 1 skipped in 1.23s"
#   "3 passed in 0.45s"
_SUMMARY_RE = re.compile(
    r"(?:(\d+) passed)?"
    r"(?:,?\s*(\d+) failed)?"
    r"(?:,?\s*(\d+) skipped)?"
    r"(?:,?\s*(\d+) error)?"
    r"\s+in\s+([\d.]+)s"
)

# Pattern matching "FAILED path/to/test.py::test_name - message"
_FAILURE_RE = re.compile(r"FAILED\s+([\w/.]+)::(\w+)\s*(?:-\s*(.*))?")


class UnitTestLayer(EvalLayerBase):
    """Runs ``pytest --tb=short -q`` inside the sandbox and parses results.

    Verdict mapping:
    - PASS: all tests pass
    - FAIL_SOFT: some tests fail (but pytest itself ran successfully)
    - FAIL_HARD: pytest execution itself errored (e.g. import errors)
    """

    def __init__(self, sandbox_client: SandboxClient) -> None:
        self._sandbox = sandbox_client

    @property
    def layer_name(self) -> EvalLayer:
        return EvalLayer.UNIT_TESTS

    async def evaluate(self, sandbox_session_id: str) -> LayerEvaluation:
        """Run pytest and return the layer evaluation."""
        started_at = utcnow()

        session_info = await self._sandbox.get_session(sandbox_session_id)
        from architect_sandbox_client.models import ExecutionRequest

        request = ExecutionRequest(
            task_id=session_info.get("task_id", "task-000000000000"),
            agent_id=session_info.get("agent_id", "agent-000000000000"),
            commands=[_PYTEST_COMMAND],
            timeout_seconds=300,
        )
        result = await self._sandbox.execute(request)

        completed_at = utcnow()
        duration = (completed_at - started_at).total_seconds()

        # Default empty result
        test_result = UnitTestResult(duration_seconds=duration)
        verdict = EvalVerdict.PASS

        if not result.command_results:
            # No command ran — treat as FAIL_HARD
            test_result = UnitTestResult(
                errors=1,
                duration_seconds=duration,
            )
            verdict = EvalVerdict.FAIL_HARD
        else:
            cmd_result = result.command_results[0]
            output = cmd_result.stdout or cmd_result.stderr or ""
            exit_code = cmd_result.exit_code

            parsed = self._parse_pytest_output(output, duration)

            if exit_code >= 2:
                # Exit code 2+ means pytest internal/collection error
                verdict = EvalVerdict.FAIL_HARD
                parsed = UnitTestResult(
                    total=parsed.total,
                    passed=parsed.passed,
                    failed=parsed.failed,
                    skipped=parsed.skipped,
                    errors=max(parsed.errors, 1),
                    duration_seconds=duration,
                    failure_details=parsed.failure_details,
                )
            elif parsed.failed > 0:
                verdict = EvalVerdict.FAIL_SOFT
            else:
                verdict = EvalVerdict.PASS

            test_result = parsed

        logger.info(
            "unit test layer complete",
            verdict=verdict,
            total=test_result.total,
            passed=test_result.passed,
            failed=test_result.failed,
            errors=test_result.errors,
            duration_seconds=duration,
        )

        return LayerEvaluation(
            layer=self.layer_name,
            verdict=verdict,
            details=test_result,
            started_at=started_at,
            completed_at=completed_at,
        )

    @staticmethod
    def _parse_pytest_output(output: str, duration: float) -> UnitTestResult:
        """Parse pytest's ``-q`` output into a :class:`UnitTestResult`."""
        passed = 0
        failed = 0
        skipped = 0
        errors = 0
        test_duration = duration
        failure_details: list[TestFailureDetail] = []

        lines = output.splitlines()

        # Look for the summary line
        for line in lines:
            match = _SUMMARY_RE.search(line)
            if match:
                passed = int(match.group(1) or 0)
                failed = int(match.group(2) or 0)
                skipped = int(match.group(3) or 0)
                errors = int(match.group(4) or 0)
                test_duration = float(match.group(5) or duration)
                break

        # Parse individual failure lines
        for line in lines:
            match = _FAILURE_RE.search(line)
            if match:
                file_path = match.group(1)
                test_name = match.group(2)
                message = match.group(3) or ""
                failure_details.append(
                    TestFailureDetail(
                        test_name=test_name,
                        file_path=file_path,
                        message=message.strip(),
                    )
                )

        total = passed + failed + skipped + errors

        return UnitTestResult(
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            duration_seconds=test_duration,
            failure_details=failure_details,
        )
