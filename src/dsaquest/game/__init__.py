"""Game mechanics: XP, levels, streaks, unlocks, achievements."""

from .achievements import ACHIEVEMENTS, Achievement, Snapshot
from .levels import (
    MAX_LEVEL,
    LevelProgress,
    level_for_xp,
    levelled_up,
    progress,
    title_for_level,
    xp_to_next,
)
from .session import ExerciseResult, RecordedOutcome, begin_exercise, complete_exercise
from .unlocks import LockState, lock_state, playable, refresh_unlocks
from .xp import XpAward, award, base_xp

__all__ = [
    "ACHIEVEMENTS",
    "MAX_LEVEL",
    "Achievement",
    "ExerciseResult",
    "LevelProgress",
    "LockState",
    "RecordedOutcome",
    "Snapshot",
    "XpAward",
    "award",
    "base_xp",
    "begin_exercise",
    "complete_exercise",
    "level_for_xp",
    "levelled_up",
    "lock_state",
    "playable",
    "progress",
    "refresh_unlocks",
    "title_for_level",
    "xp_to_next",
]
