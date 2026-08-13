"""XP awards.

The design problem with gamifying a study tool is that the fun thing and the
useful thing usually diverge: grinding the pattern you already like feels
great and teaches nothing. Two multipliers exist to close that gap.

**Diminishing returns.** The k-th exercise on the same pattern in one day is
worth ``0.5^(k-1)``. Drilling your favourite pattern stops paying almost
immediately, so breadth is the profitable strategy.

**Due-review bonus.** Anything the scheduler says is decaying is worth 1.5x.
Whatever FSRS most wants you to see is also the highest-scoring thing on the
board — so the greedy play *is* the correct study plan, and the game never has
to nag.

Two smaller rules:

* Wrong answers pay a small effort award on the modes where real work happened.
  Losing a Boss Fight after half an hour and receiving literally nothing is how
  you teach someone to stop opening the app.
* Nothing ever subtracts XP. Mistakes cost time, not progress.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.enums import Difficulty, GameMode

#: Flat base for the modes whose value does not scale with problem difficulty.
_MODE_BASE: dict[GameMode, int] = {
    GameMode.HUNTER: 10,
    GameMode.DUEL: 20,
    GameMode.RECALL: 20,
}

#: The k-th attempt at one pattern in a day is worth this to the power (k-1).
REPEAT_DECAY = 0.5

#: Decay floor, so a deliberate drilling session still pays something.
REPEAT_FLOOR = 0.125

#: Multiplier for exercising a card the scheduler had marked due.
DUE_REVIEW_BONUS = 1.5

#: Daily-streak multiplier: +1% per day, capped. Big enough to notice, small
#: enough that breaking a streak is not catastrophic — a punitive streak bonus
#: turns one missed day into a reason to quit.
STREAK_BONUS_PER_DAY = 0.01
STREAK_BONUS_CAP = 0.25

#: Fraction of base paid for a genuine but unsuccessful attempt.
EFFORT_FRACTION = 0.10

#: Modes where a failed attempt still represents real work.
_EFFORT_MODES = frozenset({GameMode.COMPLETE, GameMode.SOLVE, GameMode.BOSS})

#: Flat bonus for a Boss Fight cleared first try with no hints.
PERFECT_BOSS_BONUS = 150


@dataclass(frozen=True, slots=True)
class XpComponent:
    label: str
    factor: float


@dataclass(frozen=True, slots=True)
class XpAward:
    base: int
    components: tuple[XpComponent, ...]
    flat_bonus: int
    total: int

    def explain(self) -> str:
        """One-line breakdown, e.g. ``50 base x1.5 due x0.5 repeat = 38``."""
        parts = [f"{self.base} base"]
        parts += [f"x{c.factor:g} {c.label}" for c in self.components]
        if self.flat_bonus:
            parts.append(f"+{self.flat_bonus} perfect")
        return " ".join(parts) + f" = {self.total}"


def base_xp(mode: GameMode, difficulty: Difficulty = Difficulty.MEDIUM) -> int:
    """Base award for a successful exercise, before any multipliers."""
    if mode in _MODE_BASE:
        return _MODE_BASE[mode]
    if mode is GameMode.COMPLETE:
        # Filling holes in a template is real implementation work, but less of
        # it than writing the solution from nothing.
        return max(10, difficulty.base_xp // 2)
    return difficulty.base_xp


def award(
    *,
    mode: GameMode,
    correct: bool,
    difficulty: Difficulty = Difficulty.MEDIUM,
    repeats_today: int = 0,
    was_due: bool = False,
    streak_days: int = 0,
    hints_used: int = 0,
    tries: int = 1,
) -> XpAward:
    """Compute the XP for one completed exercise.

    ``repeats_today`` is how many times this same pattern has *already* been
    exercised today, so the first attempt of the day passes 0.
    """
    base = base_xp(mode, difficulty)

    if not correct:
        # No multipliers on an effort award: it is a consolation, not a score.
        effort = int(base * EFFORT_FRACTION) if mode in _EFFORT_MODES else 0
        return XpAward(base=base, components=(), flat_bonus=0, total=effort)

    components: list[XpComponent] = []

    if repeats_today > 0:
        factor = max(REPEAT_FLOOR, REPEAT_DECAY**repeats_today)
        components.append(XpComponent("repeat", round(factor, 4)))

    if was_due:
        components.append(XpComponent("due", DUE_REVIEW_BONUS))

    if streak_days > 1:
        bonus = min(STREAK_BONUS_CAP, STREAK_BONUS_PER_DAY * streak_days)
        components.append(XpComponent("streak", round(1.0 + bonus, 4)))

    total = float(base)
    for component in components:
        total *= component.factor

    flat = PERFECT_BOSS_BONUS if (mode is GameMode.BOSS and tries == 1 and hints_used == 0) else 0

    return XpAward(
        base=base,
        components=tuple(components),
        flat_bonus=flat,
        total=int(round(total)) + flat,
    )
