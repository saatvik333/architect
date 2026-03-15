"""Complexity scoring for task routing decisions."""

from __future__ import annotations

from pydantic import BaseModel, Field

from architect_common.enums import ModelTier, TaskType
from multi_model_router.models import ComplexityScore

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


class ScorerConfig(BaseModel, frozen=True):
    """Configuration for the :class:`ComplexityScorer`.

    All weights, thresholds, and tuning parameters are exposed here so
    they can be adjusted without modifying scoring logic.
    """

    # ── Task-type weights ────────────────────────────────────────────
    review_code_weight: float = Field(
        default=0.8,
        description="Complexity weight for code-review tasks (higher = more complex).",
    )
    fix_bug_weight: float = Field(
        default=0.7,
        description="Complexity weight for bug-fix tasks.",
    )
    implement_feature_weight: float = Field(
        default=0.5,
        description="Complexity weight for new-feature tasks.",
    )
    refactor_weight: float = Field(
        default=0.4,
        description="Complexity weight for refactoring tasks.",
    )
    write_test_weight: float = Field(
        default=0.2,
        description="Complexity weight for test-authoring tasks.",
    )
    default_task_weight: float = Field(
        default=0.5,
        description="Fallback weight for unknown task types.",
    )

    # ── Token estimate ───────────────────────────────────────────────
    token_cap: int = Field(
        default=100_000,
        description="Token count at which the token factor saturates at 1.0.",
    )

    # ── Description length thresholds ────────────────────────────────
    desc_short_max: int = Field(
        default=50,
        description="Descriptions shorter than this are considered trivial.",
    )
    desc_medium_max: int = Field(
        default=200,
        description="Descriptions shorter than this are considered medium complexity.",
    )
    desc_long_max: int = Field(
        default=500,
        description="Descriptions shorter than this are considered moderately complex.",
    )
    desc_short_factor: float = Field(
        default=0.1,
        description="Score factor for short (trivial) descriptions.",
    )
    desc_medium_factor: float = Field(
        default=0.3,
        description="Score factor for medium-length descriptions.",
    )
    desc_long_factor: float = Field(
        default=0.5,
        description="Score factor for moderately long descriptions.",
    )
    desc_very_long_factor: float = Field(
        default=0.8,
        description="Score factor for very long descriptions.",
    )

    # ── Keyword scoring ──────────────────────────────────────────────
    keyword_increment: float = Field(
        default=0.2,
        description="Score added per matching complexity keyword (capped at 1.0).",
    )

    # ── Factor weights (must sum to 1.0) ─────────────────────────────
    weight_task_type: float = Field(
        default=0.35,
        description="Contribution of task-type factor to the final score.",
    )
    weight_token_estimate: float = Field(
        default=0.25,
        description="Contribution of token-estimate factor to the final score.",
    )
    weight_description: float = Field(
        default=0.20,
        description="Contribution of description-length factor to the final score.",
    )
    weight_keywords: float = Field(
        default=0.20,
        description="Contribution of keyword-signal factor to the final score.",
    )

    # ── Tier thresholds ──────────────────────────────────────────────
    tier_1_threshold: float = Field(
        default=0.7,
        description="Minimum score to recommend Tier 1 (most capable model).",
    )
    tier_2_threshold: float = Field(
        default=0.3,
        description="Minimum score to recommend Tier 2 (mid-range model).",
    )

    def task_type_weight(self, task_type: TaskType) -> float:
        """Return the configured weight for *task_type*."""
        mapping: dict[TaskType, float] = {
            TaskType.REVIEW_CODE: self.review_code_weight,
            TaskType.FIX_BUG: self.fix_bug_weight,
            TaskType.IMPLEMENT_FEATURE: self.implement_feature_weight,
            TaskType.REFACTOR: self.refactor_weight,
            TaskType.WRITE_TEST: self.write_test_weight,
        }
        return mapping.get(task_type, self.default_task_weight)


class ComplexityScorer:
    """Score tasks by complexity to drive tier selection."""

    def __init__(self, config: ScorerConfig | None = None) -> None:
        self._cfg = config or ScorerConfig()

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
          - token_estimate (linear 0..1 over 0..token_cap)
          - description length heuristic
          - keyword signals from known complex-domain words
        """
        cfg = self._cfg
        factors: dict[str, float] = {}

        # Factor 1: task type
        factors["task_type"] = cfg.task_type_weight(task_type)

        # Factor 2: token estimate (scale linearly, cap at 1.0)
        if token_estimate <= 0:
            token_factor = 0.0
        elif token_estimate >= cfg.token_cap:
            token_factor = 1.0
        else:
            token_factor = token_estimate / cfg.token_cap
        factors["token_estimate"] = round(token_factor, 4)

        # Factor 3: description complexity (length heuristic)
        desc_len = len(description)
        if desc_len < cfg.desc_short_max:
            desc_factor = cfg.desc_short_factor
        elif desc_len < cfg.desc_medium_max:
            desc_factor = cfg.desc_medium_factor
        elif desc_len < cfg.desc_long_max:
            desc_factor = cfg.desc_long_factor
        else:
            desc_factor = cfg.desc_very_long_factor
        factors["description"] = desc_factor

        # Factor 4: keyword signals
        kw_list = keywords or []
        all_words = {w.lower() for w in kw_list} | {w.lower() for w in description.split()}
        matches = all_words & _COMPLEX_KEYWORDS
        keyword_factor = min(len(matches) * cfg.keyword_increment, 1.0)
        factors["keywords"] = round(keyword_factor, 4)

        # Weighted average
        weights = {
            "task_type": cfg.weight_task_type,
            "token_estimate": cfg.weight_token_estimate,
            "description": cfg.weight_description,
            "keywords": cfg.weight_keywords,
        }
        raw_score = sum(factors[k] * weights[k] for k in weights)
        final_score = round(min(max(raw_score, 0.0), 1.0), 4)

        # Determine recommended tier from score
        if final_score >= cfg.tier_1_threshold:
            tier = ModelTier.TIER_1
        elif final_score >= cfg.tier_2_threshold:
            tier = ModelTier.TIER_2
        else:
            tier = ModelTier.TIER_3

        return ComplexityScore(
            score=final_score,
            factors=factors,
            recommended_tier=tier,
        )
