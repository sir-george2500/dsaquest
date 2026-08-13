"""Par times — how long a task *should* take.

Two different numbers, and conflating them is the mistake the first draft made:

**Par** is a target. Beating it is fluency, missing it is a diagnosis. Nothing
bad happens when you exceed par.

**The limit** is a deadline, and it lives in ``timing.limits``. It is roughly
double par, because a student must never lose to an artificially short clock.

Calibrated to the generous table in ``docs/game-design.md`` section 4: a
competent learner working without hints should hit par routinely once the
pattern is internalised, and should never feel hurried before then.
"""

from __future__ import annotations

from ..domain.enums import Difficulty, GameMode

_SECOND = 1000
_MINUTE = 60 * _SECOND

#: Par per mode at MEDIUM difficulty.
#:
#: Recognition is generous on purpose — reading a statement takes as long as it
#: takes, and rushing that trains skimming rather than recognition. Code
#: completion is tighter because a cloze hole in a template you know should be
#: near-automatic.
_BASE_MS: dict[GameMode, int] = {
    GameMode.HUNTER: 150 * _SECOND,
    GameMode.DUEL: 4 * _MINUTE,
    GameMode.RECALL: 2 * _MINUTE,
    GameMode.COMPLETE: 6 * _MINUTE,
    GameMode.SOLVE: 20 * _MINUTE,
    GameMode.BOSS: 60 * _MINUTE,
}

#: No task targets less than this, whatever the difficulty scaling says.
#:
#: A recognition round is not a reflex test: the learner has to *read a problem
#: statement* before they can recognise anything. Scaling an easy round down to
#: 54 seconds was asking them to skim, which trains the opposite of what this
#: mode exists for.
MIN_PAR_MS = 75 * _SECOND

#: Multiplier per difficulty. Easy solve lands at 12 min, hard at 36, expert at
#: 56 — inside the 8-15 / 30-60 bands the design calls for.
_DIFFICULTY_SCALE: dict[Difficulty, float] = {
    Difficulty.EASY: 0.6,
    Difficulty.MEDIUM: 1.0,
    Difficulty.HARD: 1.8,
    Difficulty.EXPERT: 2.8,
    Difficulty.BOSS: 4.0,
}

#: How par divides across the phases of a solve. Implementation dominates
#: because that is where the time actually goes; debugging gets a real share
#: because pretending it takes no time is how targets become dishonest.
PHASE_SHARE: dict[str, float] = {
    "recognise": 0.12,
    "plan": 0.18,
    "implement": 0.55,
    "debug": 0.15,
}


def par_ms(mode: GameMode, difficulty: Difficulty = Difficulty.MEDIUM) -> int:
    """Target duration in milliseconds. Not a deadline — see ``timing.limits``."""
    return max(MIN_PAR_MS, int(_BASE_MS[mode] * _DIFFICULTY_SCALE[difficulty]))


def phase_targets(mode: GameMode, difficulty: Difficulty = Difficulty.MEDIUM) -> dict[str, int]:
    """Par split across phases, for the time-analysis report."""
    total = par_ms(mode, difficulty)
    return {phase: int(total * share) for phase, share in PHASE_SHARE.items()}


def pace_label(duration_ms: int, target_ms: int) -> str:
    """How the attempt compared with par. Deliberately non-judgemental wording."""
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


def format_duration(ms: int) -> str:
    """``6:49`` for a solve, ``0:31`` for a recognition. Always m:ss."""
    if ms < 0:
        ms = 0
    total_seconds = ms // 1000
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"
