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

__all__ = [
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
