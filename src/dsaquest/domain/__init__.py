"""Pure domain types. This package imports nothing from the rest of dsaquest."""

from .enums import Difficulty, Dimension, GameMode, MistakeCode, Rating, Verdict
from .judging import (
    CheckerKind,
    CompileResult,
    JudgeReport,
    Limits,
    Submission,
    TestCase,
    TestOutcome,
)
from .lesson import Curriculum, Demonstration, Drill, DrillKind, Secret, Stage, WatchOut
from .pattern import (
    AntiSignal,
    Complexity,
    Confusion,
    Pattern,
    RubricPoint,
    Signal,
    Trap,
)

__all__ = [
    "WatchOut",
    "Stage",
    "Secret",
    "DrillKind",
    "Drill",
    "Demonstration",
    "Curriculum",
    "AntiSignal",
    "CheckerKind",
    "Complexity",
    "CompileResult",
    "Confusion",
    "Difficulty",
    "Dimension",
    "GameMode",
    "JudgeReport",
    "Limits",
    "MistakeCode",
    "Pattern",
    "Rating",
    "RubricPoint",
    "Signal",
    "Submission",
    "TestCase",
    "TestOutcome",
    "Trap",
    "Verdict",
]
