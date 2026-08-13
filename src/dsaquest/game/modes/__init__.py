"""Game modes — one module per way of exercising a pattern."""

from .complete import (
    CompletionReport,
    Hole,
    TemplateError,
    exercise_source,
    find_hole,
    judge_completion,
    parse_holes,
    reference_source,
    splice,
)
from .hunter import (
    HunterFeedback,
    HunterOption,
    HunterRound,
    build_round,
    build_round_for,
    choose_problem,
    confusion_counts,
    judge_round,
)
from .recall import (
    RecallOutcome,
    RecallRound,
    auto_match,
    canonical_answer,
    expected_phrases,
)

__all__ = [
    "expected_phrases",
    "canonical_answer",
    "auto_match",
    "RecallRound",
    "RecallOutcome",
    "CompletionReport",
    "Hole",
    "HunterFeedback",
    "HunterOption",
    "HunterRound",
    "TemplateError",
    "build_round",
    "build_round_for",
    "choose_problem",
    "confusion_counts",
    "exercise_source",
    "find_hole",
    "judge_completion",
    "judge_round",
    "parse_holes",
    "reference_source",
    "splice",
]
