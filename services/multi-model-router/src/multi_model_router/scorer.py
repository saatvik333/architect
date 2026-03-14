"""Complexity scoring for task routing decisions."""

from __future__ import annotations

from architect_common.enums import ModelTier, TaskType
from multi_model_router.models import ComplexityScore

# ── Task-type complexity weights ─────────────────────────────────────
_TASK_TYPE_WEIGHTS: dict[TaskType, float] = {
    TaskType.REVIEW_CODE: 0.8,
    TaskType.FIX_BUG: 0.7,
    TaskType.IMPLEMENT_FEATURE: 0.5,
    TaskType.REFACTOR: 0.4,
    TaskType.WRITE_TEST: 0.2,
}

# ── Keywords that signal higher complexity ───────────────────────────
_COMPLEX_KEYWORDS: frozenset[str] = frozenset(
    {
        "security",
        "concurrent",
        "migration",
        "distributed",
        "cryptography",
        "optimisation",
        "optimization",
        "architecture",
        "performance",
        "scalability",
    }
)


class ComplexityScorer:
    """Score tasks by complexity to drive tier selection."""

    def score(
        self,
        task_type: TaskType,
        description: str,
        token_estimate: int = 0,
        keywords: list[str] | None = None,
    ) -> ComplexityScore:
        """Compute a weighted complexity score for a task.

        Factors:
          - task_type weight (predefined per TaskType)
          - token_estimate (linear 0..1 over 0..100_000)
          - description length heuristic
          - keyword signals from known complex-domain words
        """
        factors: dict[str, float] = {}

        # Factor 1: task type
        task_weight = _TASK_TYPE_WEIGHTS.get(task_type, 0.5)
        factors["task_type"] = task_weight

        # Factor 2: token estimate (scale linearly, cap at 1.0)
        if token_estimate <= 0:
            token_factor = 0.0
        elif token_estimate >= 100_000:
            token_factor = 1.0
        else:
            token_factor = token_estimate / 100_000
        factors["token_estimate"] = round(token_factor, 4)

        # Factor 3: description complexity (length heuristic)
        desc_len = len(description)
        if desc_len < 50:
            desc_factor = 0.1
        elif desc_len < 200:
            desc_factor = 0.3
        elif desc_len < 500:
            desc_factor = 0.5
        else:
            desc_factor = 0.8
        factors["description"] = desc_factor

        # Factor 4: keyword signals
        kw_list = keywords or []
        all_words = {w.lower() for w in kw_list} | {w.lower() for w in description.split()}
        matches = all_words & _COMPLEX_KEYWORDS
        keyword_factor = min(len(matches) * 0.2, 1.0)
        factors["keywords"] = round(keyword_factor, 4)

        # Weighted average (weights sum to 1.0)
        weights = {
            "task_type": 0.35,
            "token_estimate": 0.25,
            "description": 0.20,
            "keywords": 0.20,
        }
        raw_score = sum(factors[k] * weights[k] for k in weights)
        final_score = round(min(max(raw_score, 0.0), 1.0), 4)

        # Determine recommended tier from score
        if final_score >= 0.7:
            tier = ModelTier.TIER_1
        elif final_score >= 0.3:
            tier = ModelTier.TIER_2
        else:
            tier = ModelTier.TIER_3

        return ComplexityScore(
            score=final_score,
            factors=factors,
            recommended_tier=tier,
        )
