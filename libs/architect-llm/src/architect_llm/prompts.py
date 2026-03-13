"""Reusable prompt templates for ARCHITECT agents."""

from __future__ import annotations

from string import Template


class PromptTemplate:
    """Simple string-template wrapper with variable validation.

    Uses :class:`string.Template` (``$variable`` syntax) under the hood.
    """

    def __init__(self, template: str, variables: list[str]) -> None:
        self._template = Template(template)
        self._variables = frozenset(variables)

    @property
    def variables(self) -> frozenset[str]:
        return self._variables

    def render(self, **kwargs: str) -> str:
        """Substitute variables and return the rendered prompt.

        Raises:
            ValueError: If required variables are missing or unexpected
                variables are supplied.
        """
        provided = set(kwargs.keys())
        missing = self._variables - provided
        if missing:
            raise ValueError(f"Missing template variables: {sorted(missing)}")

        extra = provided - self._variables
        if extra:
            raise ValueError(f"Unexpected template variables: {sorted(extra)}")

        return self._template.substitute(**kwargs)


# ── Built-in system prompts ──────────────────────────────────────────

SYSTEM_PROMPT_CODER = PromptTemplate(
    template=(
        "You are a senior software engineer working on the $project_name project.\n"
        "\n"
        "## Context\n"
        "$task_context\n"
        "\n"
        "## Instructions\n"
        "- Write clean, production-quality $language code.\n"
        "- Follow existing conventions in the codebase.\n"
        "- Include docstrings and type annotations.\n"
        "- Write unit tests for all new public functions.\n"
        "- Do not introduce new dependencies without justification.\n"
        "- Explain your reasoning before writing code.\n"
    ),
    variables=["project_name", "task_context", "language"],
)

SYSTEM_PROMPT_REVIEWER = PromptTemplate(
    template=(
        "You are a meticulous code reviewer for the $project_name project.\n"
        "\n"
        "## Review scope\n"
        "$review_scope\n"
        "\n"
        "## Criteria\n"
        "- Correctness: does the code do what the spec requires?\n"
        "- Security: are there injection, auth, or data-leak risks?\n"
        "- Performance: any unnecessary allocations, N+1 queries, or blocking calls?\n"
        "- Readability: clear naming, appropriate abstractions, sufficient docs?\n"
        "- Testing: adequate coverage, edge cases, no flaky patterns?\n"
        "\n"
        "Provide actionable feedback with file paths and line references.\n"
        "Classify each finding as: CRITICAL, WARNING, or SUGGESTION.\n"
    ),
    variables=["project_name", "review_scope"],
)
