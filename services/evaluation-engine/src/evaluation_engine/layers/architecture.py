"""Architecture compliance evaluation layer."""

from __future__ import annotations

from architect_common.enums import EvalLayer, EvalVerdict
from architect_common.logging import get_logger
from architect_common.types import utcnow
from architect_sandbox_client.client import SandboxClient
from evaluation_engine.layers.base import EvalLayerBase
from evaluation_engine.models import ArchitectureResult, LayerEvaluation

logger = get_logger(component="evaluation_engine.layers.architecture")

# Check for cross-service imports (services must never import other services)
_CROSS_IMPORT_COMMAND = (
    "grep -rn "
    "'from\\s\\+\\(world_state_ledger\\|task_graph_engine\\|execution_sandbox"
    "\\|evaluation_engine\\|coding_agent\\|agent_comm_bus\\|codebase_comprehension"
    "\\|deployment_pipeline\\|economic_governor\\|failure_taxonomy\\|human_interface"
    "\\|knowledge_memory\\|multi_model_router\\|security_immune\\|spec_engine\\)' "
    "/workspace/src/ 2>/dev/null || true"
)

# Run ruff for lint violations
_RUFF_COMMAND = "cd /workspace && ruff check --output-format=text . 2>&1 || true"


class ArchitectureComplianceLayer(EvalLayerBase):
    """Checks architectural conventions inside the sandbox workspace.

    Runs two checks:
    1. No cross-service imports (services must only import shared libs)
    2. ruff lint check for code quality violations

    Verdict mapping:
    - PASS: no violations found
    - FAIL_SOFT: lint warnings or minor import issues
    - FAIL_HARD: critical cross-service import violations
    """

    def __init__(self, sandbox_client: SandboxClient) -> None:
        self._sandbox = sandbox_client

    @property
    def layer_name(self) -> EvalLayer:
        return EvalLayer.ARCHITECTURE

    async def evaluate(self, sandbox_session_id: str) -> LayerEvaluation:
        """Run architecture compliance checks and return the evaluation."""
        started_at = utcnow()

        session_info = await self._sandbox.get_session(sandbox_session_id)
        from architect_sandbox_client.models import ExecutionRequest

        # Run both checks
        request = ExecutionRequest(
            task_id=session_info.get("task_id", "task-000000000000"),
            agent_id=session_info.get("agent_id", "agent-000000000000"),
            commands=[_CROSS_IMPORT_COMMAND, _RUFF_COMMAND],
            timeout_seconds=120,
        )
        result = await self._sandbox.execute(request)

        completed_at = utcnow()

        import_violations: list[str] = []
        lint_violations: list[str] = []

        if len(result.command_results) >= 1:
            # Parse cross-import check output
            cross_import_output = result.command_results[0].stdout or ""
            for line in cross_import_output.splitlines():
                stripped = line.strip()
                if stripped:
                    import_violations.append(stripped)

        if len(result.command_results) >= 2:
            # Parse ruff output
            ruff_output = result.command_results[1].stdout or ""
            for line in ruff_output.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("Found"):
                    lint_violations.append(stripped)

        all_violations = import_violations + lint_violations
        conventions_checked = 2  # cross-import check + ruff check
        conventions_violated = (1 if import_violations else 0) + (1 if lint_violations else 0)

        # Import violations are critical; lint-only is soft
        if import_violations:
            verdict = EvalVerdict.FAIL_HARD
        elif lint_violations:
            verdict = EvalVerdict.FAIL_SOFT
        else:
            verdict = EvalVerdict.PASS

        arch_result = ArchitectureResult(
            violations=all_violations,
            conventions_checked=conventions_checked,
            conventions_violated=conventions_violated,
            import_violations=import_violations,
        )

        logger.info(
            "architecture layer complete",
            verdict=verdict,
            import_violation_count=len(import_violations),
            lint_violation_count=len(lint_violations),
        )

        return LayerEvaluation(
            layer=self.layer_name,
            verdict=verdict,
            details=arch_result,
            started_at=started_at,
            completed_at=completed_at,
        )
