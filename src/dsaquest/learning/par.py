"""Par times — how long an exercise *should* take.

Par is what makes "speed" measurable and what lets the rating rubric tell
fluency from mere correctness. The numbers are calibrated to a competent
learner working without hints, not to a red coder: par is a target you can hit
routinely once the pattern is internalised, not a stretch goal.

They are deliberately generous for recognition (reading a statement takes as
long as it takes) and tight for code completion (a cloze hole in a template you
know should be near-instant).
"""

from __future__ import annotations

from ..domain.enums import Difficulty, GameMode

_SECOND = 1000
_MINUTE = 60 * _SECOND

#: Base par per mode, at MEDIUM difficulty.
_BASE_MS: dict[GameMode, int] = {
    GameMode.HUNTER: 45 * _SECOND,
    GameMode.DUEL: 75 * _SECOND,
    GameMode.RECALL: 3 * _MINUTE,
    GameMode.COMPLETE: 4 * _MINUTE,
    GameMode.SOLVE: 15 * _MINUTE,
    GameMode.BOSS: 30 * _MINUTE,
}

#: Multiplier applied to the base for each difficulty.
_DIFFICULTY_SCALE: dict[Difficulty, float] = {
    Difficulty.EASY: 0.6,
    Difficulty.MEDIUM: 1.0,
    Difficulty.HARD: 1.8,
    Difficulty.EXPERT: 2.8,
    Difficulty.BOSS: 4.0,
}


def par_ms(mode: GameMode, difficulty: Difficulty = Difficulty.MEDIUM) -> int:
    """Target duration in milliseconds for one exercise."""
    return int(_BASE_MS[mode] * _DIFFICULTY_SCALE[difficulty])


def pace_label(duration_ms: int, target_ms: int) -> str:
    """Human phrasing for how the attempt compared with par."""
    if target_ms <= 0:
        return ""
    ratio = duration_ms / target_ms
    if ratio <= 0.6:
        return "fast"
    if ratio <= 1.0:
        return "on par"
    if ratio <= 2.0:
        return "slow"
    return "very slow"
