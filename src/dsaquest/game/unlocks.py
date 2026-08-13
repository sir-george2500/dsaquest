"""Unlocking patterns.

Worlds are how the campaign is *displayed*; the prerequisite DAG is what
actually gates content. A pattern opens the moment its own prerequisites are
mastered, so you are never made to grind an unrelated corner of a world to
reach the thing you want next.

Being locked is only useful if the learner can see the way out, so every locked
pattern can explain exactly what it is waiting for and how close that is.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..content.loader import PatternLibrary
from ..learning.mastery import UNLOCK_THRESHOLD, PatternMastery, available_patterns
from ..storage import repositories as repo


@dataclass(frozen=True, slots=True)
class LockState:
    pattern_id: str
    unlocked: bool
    blockers: tuple[tuple[str, float], ...]
    """(prerequisite id, its current mastery) for each one not yet met."""

    def explain(self) -> str:
        if self.unlocked:
            return "unlocked"
        if not self.blockers:
            return "locked"
        parts = [
            f"{pattern_id} at {mastery:.0%} of {UNLOCK_THRESHOLD:.0%}"
            for pattern_id, mastery in self.blockers
        ]
        return "needs " + ", ".join(parts)


def lock_state(
    library: PatternLibrary, mastery: dict[str, PatternMastery], pattern_id: str
) -> LockState:
    pattern = library[pattern_id]
    blockers = tuple(
        (prereq, mastery[prereq].overall if prereq in mastery else 0.0)
        for prereq in pattern.prerequisites
        if not (prereq in mastery and mastery[prereq].unlocks_dependents)
    )
    return LockState(pattern_id=pattern_id, unlocked=not blockers, blockers=blockers)


def refresh_unlocks(
    conn: sqlite3.Connection,
    library: PatternLibrary,
    mastery: dict[str, PatternMastery],
) -> tuple[str, ...]:
    """Persist any newly available patterns; return the ones just unlocked.

    Unlocks are recorded rather than recomputed on the fly so that an unlock is
    a one-time event the UI can celebrate — and so that a pattern which later
    decays below the threshold does not silently re-lock, which would be a
    miserable experience and would punish the honest reporting of a lapse.
    """
    newly: list[str] = []
    for pattern_id in available_patterns(library, mastery):
        if repo.unlock_pattern(conn, pattern_id):
            newly.append(pattern_id)
    return tuple(newly)


def playable(
    conn: sqlite3.Connection,
    library: PatternLibrary,
    mastery: dict[str, PatternMastery],
) -> tuple[str, ...]:
    """Patterns the learner may practise right now, in campaign order.

    The union of what has ever been unlocked and what is available now, so a
    decayed prerequisite never takes away access you already had.
    """
    unlocked = repo.unlocked_patterns(conn)
    available = set(available_patterns(library, mastery))
    allowed = unlocked | available
    return tuple(pattern.id for pattern in library if pattern.id in allowed)
