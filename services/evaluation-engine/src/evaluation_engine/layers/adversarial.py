"""Adversarial testing evaluation layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from architect_common.enums import EvalLayer, EvalVerdict
from architect_common.logging import get_logger
from architect_common.types import utcnow
from architect_sandbox_client.client import SandboxClient
from evaluation_engine.layers.base import EvalLayerBase
from evaluation_engine.models import AdversarialResult, LayerEvaluation

if TYPE_CHECKING:
    from architect_llm.client import LLMClient

logger = get_logger(component="evaluation_engine.layers.adversarial")

_ADVERSARIAL_SYSTEM_PROMPT = """\
You are a security-focused test engineer. Given the source code below, generate
a Python test file (pytest) that exercises adversarial edge cases:
- Null / empty inputs
- Injection attacks (SQL, command, path traversal)
- Boundary values (max int, empty strings, huge payloads)
- Type confusion

Output ONLY valid Python code for a test file, no markdown fences.
"""

_RUN_ADVERSARIAL_TESTS = (
    "cd /workspace && python -m pytest /tmp/test_adversarial_generated.py --tb=short -q 2>&1"
)


class AdversarialLayer(EvalLayerBase):
    """Uses an LLM to generate adversarial test cases and runs them in the sandbox.

    Verdict mapping:
    - PASS: no vulnerabilities found
    - FAIL_SOFT: low or medium severity findings
    - FAIL_HARD: high or critical severity findings, or LLM/execution errors
    """

    def __init__(self, sandbox_client: SandboxClient, llm_client: LLMClient) -> None:
        self._sandbox = sandbox_client
        self._llm = llm_client

    @property
    def layer_name(self) -> EvalLayer:
        return EvalLayer.ADVERSARIAL

    async def evaluate(self, sandbox_session_id: str) -> LayerEvaluation:
        """Generate and run adversarial tests, then return the evaluation."""
        started_at = utcnow()

        session_info = await self._sandbox.get_session(sandbox_session_id)
        from architect_sandbox_client.models import ExecutionRequest

        # Step 1: Read source code from sandbox to feed to LLM
        read_request = ExecutionRequest(
            task_id=session_info.get("task_id", "task-000000000000"),
            agent_id=session_info.get("agent_id", "agent-000000000000"),
            commands=[
                "find /workspace -name '*.py' -not -path '*/__pycache__/*' | head -20 | xargs cat 2>&1"
            ],
            timeout_seconds=60,
        )
        source_result = await self._sandbox.execute(read_request)

        source_code = ""
        if source_result.command_results:
            source_code = source_result.command_results[0].stdout or ""

        # Step 2: Ask LLM to generate adversarial tests
        from architect_llm.models import LLMRequest

        try:
            llm_response = await self._llm.generate(
                LLMRequest(
                    system_prompt=_ADVERSARIAL_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": f"Source code:\n\n{source_code}"}],
                    max_tokens=4000,
                    temperature=0.3,
                )
            )
            test_code = llm_response.content
        except Exception:
            logger.exception("LLM generation failed for adversarial tests")
            completed_at = utcnow()
            return LayerEvaluation(
                layer=self.layer_name,
                verdict=EvalVerdict.FAIL_HARD,
                details=AdversarialResult(
                    duration_seconds=(completed_at - started_at).total_seconds(),
                ),
                started_at=started_at,
                completed_at=completed_at,
            )

        # Step 3: Write test file into sandbox and run it
        write_and_run_request = ExecutionRequest(
            task_id=session_info.get("task_id", "task-000000000000"),
            agent_id=session_info.get("agent_id", "agent-000000000000"),
            files={"/tmp/test_adversarial_generated.py": test_code},  # nosec B108 # path inside sandbox container
            commands=[_RUN_ADVERSARIAL_TESTS],
            timeout_seconds=120,
        )
        run_result = await self._sandbox.execute(write_and_run_request)

        completed_at = utcnow()
        duration = (completed_at - started_at).total_seconds()

        # Step 4: Parse results
        vulnerabilities: list[str] = []
        if run_result.command_results:
            cmd_result = run_result.command_results[0]
            output = cmd_result.stdout or cmd_result.stderr or ""
            exit_code = cmd_result.exit_code

            if exit_code != 0:
                # Each FAILED line represents a potential vulnerability
                for line in output.splitlines():
                    if line.strip().startswith("FAILED"):
                        vulnerabilities.append(line.strip())

        vuln_count = len(vulnerabilities)
        severity = self._classify_severity(vuln_count)
        verdict = self._severity_to_verdict(severity)

        result = AdversarialResult(
            attack_vectors_tested=1,  # One LLM-generated test suite
            vulnerabilities_found=vuln_count,
            findings=vulnerabilities,
            severity=severity,
            duration_seconds=duration,
        )

        logger.info(
            "adversarial layer complete",
            verdict=verdict,
            vulnerabilities_found=vuln_count,
            severity=severity,
            duration_seconds=duration,
        )

        return LayerEvaluation(
            layer=self.layer_name,
            verdict=verdict,
            details=result,
            started_at=started_at,
            completed_at=completed_at,
        )

    @staticmethod
    def _classify_severity(vuln_count: int) -> str:
        """Classify severity based on vulnerability count."""
        if vuln_count == 0:
            return "none"
        if vuln_count <= 2:
            return "low"
        if vuln_count <= 5:
            return "medium"
        if vuln_count <= 10:
            return "high"
        return "critical"

    @staticmethod
    def _severity_to_verdict(severity: str) -> EvalVerdict:
        """Map severity level to an evaluation verdict."""
        if severity == "none":
            return EvalVerdict.PASS
        if severity in ("low", "medium"):
            return EvalVerdict.FAIL_SOFT
        return EvalVerdict.FAIL_HARD
