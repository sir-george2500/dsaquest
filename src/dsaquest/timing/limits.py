"""Deadlines.

The rule this module exists to enforce: **a student must never lose because the
clock was artificially short.** The limit is roughly double par, and pressure is
applied by *removing assistance*, not by squeezing the clock.

    limit = par x LIMIT_MULTIPLE x personal_factor x stage_factor

``personal_factor`` learns your normal speed and then asks for slightly better.
It is clamped hard in both directions, and the clamp is the interesting part:

* without a **floor**, a fast learner spirals into limits nobody could meet —
  the system would punish exactly the improvement it is meant to reward;
* without a **ceiling**, a slow learner never experiences pressure at all and
  the timer stops meaning anything.

Stage 1 has no deadline whatsoever. You cannot learn a technique and race
against it in the same breath.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import IntEnum

from ..domain.enums import Difficulty, GameMode
from ..learning.par import par_ms

#: The deadline is this multiple of par before any adjustment.
LIMIT_MULTIPLE = 2.0

#: Clamp on how far personal history may move the limit.
PERSONAL_FLOOR = 0.75
PERSONAL_CEILING = 1.5

#: Attempts required before personal history is trusted at all. Below this the
#: factor is 1.0 — two fast answers are noise, not a measurement.
PERSONAL_MIN_SAMPLES = 5


class PressureStage(IntEnum):
    """How much help the student gets, and whether a clock runs at all.

    Advancing is per-pattern, driven by that pattern's own mastery. You can be
    at TRIAL on Two Pointers and CALM on dynamic programming.
    """

    CALM = 1
    """Learning the concept. No timer. Hints free. Pattern named."""

    TIMED = 2
    """A generous clock appears. Hints still free. Pattern named."""

    RUTHLESS = 3
    """Same clock. Hints now cost. Pattern still named."""

    TRIAL = 4
    """Same clock. One hint only. Pattern HIDDEN."""

    BOSS = 5
    """Same clock. No hints. Pattern hidden, multiple patterns composed."""

    @property
    def has_timer(self) -> bool:
        return self is not PressureStage.CALM

    @property
    def hides_pattern(self) -> bool:
        return self >= PressureStage.TRIAL

    @property
    def hints_allowed(self) -> int | None:
        """None means unlimited."""
        return {
            PressureStage.CALM: None,
            PressureStage.TIMED: None,
            PressureStage.RUTHLESS: 3,
            PressureStage.TRIAL: 1,
            PressureStage.BOSS: 0,
        }[self]

    @property
    def label(self) -> str:
        return {
            PressureStage.CALM: "Calm Training",
            PressureStage.TIMED: "Timed Training",
            PressureStage.RUTHLESS: "Ruthless Training",
            PressureStage.TRIAL: "Master's Trial",
            PressureStage.BOSS: "Boss Fight",
        }[self]


#: Stage never shortens the clock. Higher stages remove help instead, which is
#: dramatic and fair; accelerating a timer punishes careful thought, which is
#: the opposite of what the timer is supposed to teach.
_STAGE_FACTOR: dict[PressureStage, float] = {
    PressureStage.CALM: 0.0,  # no limit at all
    PressureStage.TIMED: 1.15,
    PressureStage.RUTHLESS: 1.0,
    PressureStage.TRIAL: 1.0,
    PressureStage.BOSS: 1.1,  # a boss composes patterns; give the reading time back
}


@dataclass(frozen=True, slots=True)
class TimeBudget:
    """What the clock shows and what it means."""

    target_ms: int
    limit_ms: int | None
    stage: PressureStage
    personal_factor: float
    samples: int

    @property
    def has_deadline(self) -> bool:
        return self.limit_ms is not None

    @property
    def is_personalised(self) -> bool:
        return self.samples >= PERSONAL_MIN_SAMPLES

    def remaining_ms(self, elapsed_ms: int) -> int | None:
        if self.limit_ms is None:
            return None
        return max(0, self.limit_ms - elapsed_ms)

    def expired(self, elapsed_ms: int) -> bool:
        return self.limit_ms is not None and elapsed_ms >= self.limit_ms

    def fraction_used(self, elapsed_ms: int) -> float:
        if not self.limit_ms:
            return 0.0
        return min(1.0, elapsed_ms / self.limit_ms)

    def bar(self, elapsed_ms: int, width: int = 24) -> str:
        used = int(self.fraction_used(elapsed_ms) * width)
        return "█" * used + "░" * (width - used)


def stage_for_mastery(overall: float, started: bool) -> PressureStage:
    """Which pressure stage a pattern has earned.

    The thresholds sit below the 0.65 unlock bar on purpose: pressure should
    arrive while you are still improving, not as a reward once you are done.
    """
    if not started:
        return PressureStage.CALM
    if overall >= 0.65:
        return PressureStage.TRIAL
    if overall >= 0.40:
        return PressureStage.RUTHLESS
    if overall >= 0.15:
        return PressureStage.TIMED
    return PressureStage.CALM


def personal_factor(
    conn: sqlite3.Connection, mode: GameMode, difficulty: Difficulty
) -> tuple[float, int]:
    """Learn this student's normal speed for this kind of task.

    Returns ``(factor, samples)``. A factor below 1.0 means they are faster than
    par and the limit tightens toward them; above 1.0 means the opposite. Both
    directions are clamped, and both are needed: the floor stops the system
    punishing improvement, the ceiling stops the clock becoming meaningless.
    """
    rows = conn.execute(
        """
        SELECT duration_ms, par_ms FROM attempt
         WHERE mode = ? AND difficulty = ? AND correct = 1
           AND duration_ms IS NOT NULL AND par_ms IS NOT NULL AND par_ms > 0
         ORDER BY started_at DESC LIMIT 20
        """,
        (mode.value, difficulty.value),
    ).fetchall()

    if len(rows) < PERSONAL_MIN_SAMPLES:
        return 1.0, len(rows)

    ratios = sorted(row["duration_ms"] / row["par_ms"] for row in rows)
    middle = len(ratios) // 2
    median = ratios[middle] if len(ratios) % 2 else (ratios[middle - 1] + ratios[middle]) / 2
    return max(PERSONAL_FLOOR, min(PERSONAL_CEILING, median)), len(rows)


def budget_for(
    conn: sqlite3.Connection | None,
    mode: GameMode,
    difficulty: Difficulty = Difficulty.MEDIUM,
    *,
    stage: PressureStage = PressureStage.TIMED,
) -> TimeBudget:
    """The clock for one exercise."""
    target = par_ms(mode, difficulty)

    if not stage.has_timer:
        return TimeBudget(
            target_ms=target, limit_ms=None, stage=stage, personal_factor=1.0, samples=0
        )

    factor, samples = personal_factor(conn, mode, difficulty) if conn is not None else (1.0, 0)
    limit = target * LIMIT_MULTIPLE * factor * _STAGE_FACTOR[stage]

    return TimeBudget(
        target_ms=target,
        limit_ms=int(limit),
        stage=stage,
        personal_factor=factor,
        samples=samples,
    )
