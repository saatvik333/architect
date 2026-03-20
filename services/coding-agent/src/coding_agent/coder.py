"""Code generator: produces code files via LLM and supports iterative fixing."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from architect_common.logging import get_logger
from architect_llm.models import LLMRequest
from coding_agent.context_builder import ContextBuilder
from coding_agent.models import CodebaseContext, GeneratedFile, SpecContext

if TYPE_CHECKING:
    from architect_llm.client import LLMClient
    from coding_agent.models import AgentConfig

logger = get_logger(component="coding_agent.coder")

# ── Post-generation security scanning ────────────────────────────────

_SUSPICIOUS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("os.system call", re.compile(r"\bos\.system\s*\(")),
    ("subprocess with shell=True", re.compile(r"subprocess\.\w+\([^)]*shell\s*=\s*True")),
    ("eval() call", re.compile(r"\beval\s*\(")),
    ("exec() call", re.compile(r"\bexec\s*\(")),
    ("__import__('os')", re.compile(r"__import__\s*\(\s*['\"]os['\"]\s*\)")),
    ("pickle.loads", re.compile(r"pickle\.loads?\s*\(")),
    ("unsafe yaml.load", re.compile(r"yaml\.load\s*\([^)]*(?!Loader\s*=\s*SafeLoader)")),
    ("outbound requests.get", re.compile(r"requests\.(get|post|put|delete)\s*\(")),
    ("urllib request", re.compile(r"urllib\.request\.\w+\s*\(")),
    ("socket.connect", re.compile(r"socket\.connect\s*\(")),
]


def _scan_generated_code(files: list[GeneratedFile]) -> list[dict[str, str]]:
    """Scan generated files for suspicious patterns. Returns list of warnings."""
    warnings: list[dict[str, str]] = []
    for f in files:
        for label, pattern in _SUSPICIOUS_PATTERNS:
            if pattern.search(f.content):
                warnings.append({"file": f.path, "pattern": label})
    return warnings


# Regex to extract fenced code blocks with optional file-path comments.
# Matches: ```python\n# path/to/file.py\n<content>\n```
_CODE_BLOCK_RE = re.compile(
    r"```(?:python|py)?\s*\n"
    r"#\s*([\w/._ -]+\.py)\s*\n"
    r"(.*?)"
    r"\n```",
    re.DOTALL,
)


class CodeGenerator:
    """Generates code files via LLM and supports iterative error fixing.

    The generator parses fenced code blocks from the LLM response, extracting
    file paths from leading ``# path/to/file.py`` comments.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client
        self._context_builder = ContextBuilder()

    async def generate(
        self,
        plan: str,
        spec: SpecContext,
        codebase: CodebaseContext,
        config: AgentConfig | None = None,
    ) -> list[GeneratedFile]:
        """Generate code files from the plan and specification.

        Args:
            plan: The implementation plan.
            spec: Task specification.
            codebase: Relevant codebase snapshot.
            config: Optional agent config for prompt/model tuning.

        Returns:
            A list of :class:`GeneratedFile` instances.
        """
        from coding_agent.models import AgentConfig as _AgentConfig

        cfg = config or _AgentConfig()

        system_prompt = self._context_builder.build_system_prompt(cfg)
        user_prompt = self._context_builder.build_user_prompt(spec, codebase, plan)

        request = LLMRequest(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=cfg.max_output_tokens,
            temperature=cfg.temperature,
            model_id=cfg.model_id,
        )

        logger.info("generating code", task_title=spec.title)

        response = await self._llm.generate(request)

        files = self._parse_files(response.content)

        # Post-generation security scan
        scan_warnings = _scan_generated_code(files)
        if scan_warnings:
            logger.warning(
                "suspicious_patterns_in_generated_code",
                warnings=scan_warnings,
            )

        logger.info(
            "code generated",
            file_count=len(files),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )

        return files

    async def fix_errors(
        self,
        files: list[GeneratedFile],
        errors: list[str],
        spec: SpecContext,
    ) -> list[GeneratedFile]:
        """Attempt to fix errors in previously generated files.

        Sends the current files, the error messages, and the spec back to
        the LLM and asks it to produce corrected versions.

        Args:
            files: The files that caused errors.
            errors: Error messages from compilation or test execution.
            spec: The task specification (for context).

        Returns:
            A corrected list of :class:`GeneratedFile` instances.
        """
        file_listing = "\n\n".join(f"### {f.path}\n```python\n{f.content}\n```" for f in files)
        error_listing = "\n".join(f"- {e}" for e in errors)

        prompt = (
            "The following code was generated but produced errors. "
            "Please fix the issues and return ALL files with corrections.\n"
            "\n"
            f"## Task: {spec.title}\n"
            f"{spec.description}\n"
            "\n"
            f"## Current Files\n{file_listing}\n"
            "\n"
            f"## Errors\n{error_listing}\n"
            "\n"
            "Output each corrected file as a fenced code block with the "
            "file path as a comment on the first line."
        )

        request = LLMRequest(
            system_prompt=(
                "You are a senior software engineer debugging code. "
                "Fix all errors while preserving the original design intent."
            ),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=16_000,
            temperature=0.1,
        )

        logger.info("fixing errors", error_count=len(errors))

        response = await self._llm.generate(request)
        fixed_files = self._parse_files(response.content)

        logger.info(
            "errors fixed",
            file_count=len(fixed_files),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )

        return fixed_files if fixed_files else files

    @staticmethod
    def _parse_files(llm_output: str) -> list[GeneratedFile]:
        """Extract :class:`GeneratedFile` instances from LLM output.

        Looks for fenced code blocks starting with ``# path/to/file.py``.
        """
        files: list[GeneratedFile] = []
        seen_paths: set[str] = set()

        for match in _CODE_BLOCK_RE.finditer(llm_output):
            path = match.group(1).strip()
            content = match.group(2)

            if path in seen_paths:
                # Deduplicate: keep the last occurrence
                files = [f for f in files if f.path != path]
            seen_paths.add(path)

            is_test = "test" in path.lower()

            files.append(
                GeneratedFile(
                    path=path,
                    content=content,
                    is_test=is_test,
                )
            )

        return files
