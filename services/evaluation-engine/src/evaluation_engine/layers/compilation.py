"""Compilation/syntax-check evaluation layer."""

from __future__ import annotations

from architect_common.enums import EvalLayer, EvalVerdict
from architect_common.logging import get_logger
from architect_common.types import utcnow
from architect_sandbox_client.client import SandboxClient
from evaluation_engine.layers.base import EvalLayerBase
from evaluation_engine.models import CompilationResult, LayerEvaluation

logger = get_logger(component="evaluation_engine.layers.compilation")

# Shell command that finds all .py files under /workspace and runs py_compile
# on each.  Non-zero exit means at least one file failed to compile.
_COMPILE_COMMAND = (
    "find /workspace -name '*.py' -not -path '*/__pycache__/*' -exec python -m py_compile {} + 2>&1"
)


class CompilationLayer(EvalLayerBase):
    """Runs ``python -m py_compile`` on every Python file in the sandbox workspace.

    Returns PASS when all files compile cleanly, or FAIL_HARD when any file
    contains a syntax error.
    """

    def __init__(self, sandbox_client: SandboxClient) -> None:
        self._sandbox = sandbox_client

    @property
    def layer_name(self) -> EvalLayer:
        return EvalLayer.COMPILATION

    async def evaluate(self, sandbox_session_id: str) -> LayerEvaluation:
        """Run compilation checks and return the layer evaluation."""
        started_at = utcnow()

        session_info = await self._sandbox.get_session(sandbox_session_id)
        # Execute py_compile against all .py files in the workspace
        from architect_sandbox_client.models import ExecutionRequest

        request = ExecutionRequest(
            task_id=session_info.get("task_id", "task-000000000000"),
            agent_id=session_info.get("agent_id", "agent-000000000000"),
            commands=[_COMPILE_COMMAND],
            timeout_seconds=120,
        )
        result = await self._sandbox.execute(request)

        errors: list[str] = []
        warnings: list[str] = []

        for cmd_result in result.command_results:
            if cmd_result.exit_code != 0:
                # Parse stderr/stdout for compilation error lines
                output = cmd_result.stderr or cmd_result.stdout
                for line in output.splitlines():
                    stripped = line.strip()
                    if stripped:
                        if "SyntaxError" in stripped or "Error" in stripped:
                            errors.append(stripped)
                        elif "Warning" in stripped:
                            warnings.append(stripped)
                        else:
                            errors.append(stripped)

        completed_at = utcnow()
        success = len(errors) == 0
        duration = (completed_at - started_at).total_seconds()

        compilation_result = CompilationResult(
            success=success,
            errors=errors,
            warnings=warnings,
            duration_seconds=duration,
        )

        verdict = EvalVerdict.PASS if success else EvalVerdict.FAIL_HARD

        logger.info(
            "compilation layer complete",
            verdict=verdict,
            error_count=len(errors),
            warning_count=len(warnings),
            duration_seconds=duration,
        )

        return LayerEvaluation(
            layer=self.layer_name,
            verdict=verdict,
            details=compilation_result,
            started_at=started_at,
            completed_at=completed_at,
        )
