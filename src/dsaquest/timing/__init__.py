"""Timing: generous deadlines, phase instrumentation, and the time diagnosis."""

from .analysis import PhaseLine, TimeAnalysis, analyse, timeout_report
from .limits import (
    PERSONAL_CEILING,
    PERSONAL_FLOOR,
    PressureStage,
    TimeBudget,
    budget_for,
    personal_factor,
    stage_for_mastery,
)
from .phases import PHASE_ORDER, Phase, PhaseTiming, Stopwatch

__all__ = [
    "PERSONAL_CEILING",
    "PERSONAL_FLOOR",
    "PHASE_ORDER",
    "Phase",
    "PhaseLine",
    "PhaseTiming",
    "PressureStage",
    "Stopwatch",
    "TimeAnalysis",
    "TimeBudget",
    "analyse",
    "budget_for",
    "personal_factor",
    "stage_for_mastery",
    "timeout_report",
]
