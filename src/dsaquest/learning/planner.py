"""Deciding what to practise next.

The scheduler knows what is decaying; the mastery model knows what is weak; the
unlock DAG knows what is legal. This turns those three into an ordered queue.

Priority, highest first:

1. **Due reviews**, most overdue first. Forgetting is the thing this app exists
   to prevent, and the XP rules already pay 1.5x here so the incentive agrees.
2. **Weakest started patterns.** Reinforce what is wobbling before adding more.
3. **New unlocked patterns**, in campaign order — but only after the first two
   are satisfied, so the campaign never outruns retention.

A session deliberately mixes modes rather than blocking them. Ten recognition
questions in a row become pattern-matching on the question format; interleaving
is what forces retrieval from scratch each time.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from fsrs import Scheduler

from ..content.loader import PatternLibrary
from ..content.problems import ProblemBank
from ..domain.enums import Difficulty, Dimension, GameMode
from ..game.unlocks import playable
from ..storage import repositories as repo
from .mastery import PatternMastery, all_mastery

#: Which mode exercises each scheduled dimension in the MVP.
_MODE_FOR: dict[Dimension, GameMode] = {
    Dimension.RECOGNITION: GameMode.HUNTER,
    Dimension.IMPLEMENTATION: GameMode.COMPLETE,
    # Recall (Mode B) is not in the MVP; its cards simply are not scheduled yet.
}


@dataclass(frozen=True, slots=True)
class PlannedItem:
    pattern_id: str
    mode: GameMode
    difficulty: Difficulty
    reason: str
    overdue_days: float = 0.0

    @property
    def dimension(self) -> Dimension:
        return self.mode.trains


@dataclass(frozen=True, slots=True)
class SessionPlan:
    items: tuple[PlannedItem, ...]
    due_count: int
    recommendation: str

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)


def _difficulty_for(mastery: PatternMastery | None) -> Difficulty:
    """Scale difficulty to current mastery, so problems stay just past comfort."""
    if mastery is None or not mastery.started:
        return Difficulty.EASY
    if mastery.overall >= 0.75:
        return Difficulty.HARD
    if mastery.overall >= 0.45:
        return Difficulty.MEDIUM
    return Difficulty.EASY


def build_session(
    conn: sqlite3.Connection,
    library: PatternLibrary,
    bank: ProblemBank,
    *,
    scheduler: Scheduler,
    size: int = 8,
    now: datetime | None = None,
) -> SessionPlan:
    at = now or datetime.now(UTC)
    mastery = all_mastery(conn, library, scheduler=scheduler, now=at)
    allowed = set(playable(conn, library, mastery)) & bank.patterns_with_problems()

    items: list[PlannedItem] = []
    seen: set[tuple[str, GameMode]] = set()

    def add(pattern_id: str, mode: GameMode, reason: str, overdue: float = 0.0) -> None:
        key = (pattern_id, mode)
        if key in seen or len(items) >= size:
            return
        seen.add(key)
        items.append(
            PlannedItem(
                pattern_id=pattern_id,
                mode=mode,
                difficulty=_difficulty_for(mastery.get(pattern_id)),
                reason=reason,
                overdue_days=overdue,
            )
        )

    # 1. Due reviews.
    due = repo.due_cards(conn, now=at.isoformat(timespec="seconds"), limit=size * 3)
    due_count = 0
    for card in due:
        if card.pattern_id not in allowed:
            continue
        mode = _MODE_FOR.get(card.dimension)
        if mode is None:
            continue
        if card.is_new:
            continue  # a never-seen card is "new", not "due" — handled below
        due_count += 1
        overdue = (at - datetime.fromisoformat(card.due_at)).total_seconds() / 86400
        add(card.pattern_id, mode, "due for review", max(0.0, overdue))

    # 2. Weakest started patterns.
    started = sorted(
        (m for pid, m in mastery.items() if m.started and pid in allowed),
        key=lambda m: m.overall,
    )
    for weak in started:
        mode = _MODE_FOR.get(weak.weakest.dimension, GameMode.HUNTER)
        add(weak.pattern_id, mode, f"weakest: {weak.weakest.dimension.value}")

    # 3. New material, in campaign order.
    for pattern in library:
        if pattern.id not in allowed:
            continue
        if mastery[pattern.id].started:
            continue
        add(pattern.id, GameMode.HUNTER, "new pattern")

    return SessionPlan(
        items=tuple(items[:size]),
        due_count=due_count,
        recommendation=_recommend(mastery, due_count, allowed),
    )


def _recommend(mastery: dict[str, PatternMastery], due_count: int, allowed: set[str]) -> str:
    """One sentence telling the learner what this session is for."""
    if due_count:
        plural = "review" if due_count == 1 else "reviews"
        return f"{due_count} {plural} due — clearing these first is worth 1.5x XP"

    started = [m for pid, m in mastery.items() if m.started and pid in allowed]
    if not started:
        return "Starting fresh: recognition on the World 1 patterns"

    weakest = min(started, key=lambda m: m.overall)
    if weakest.gated:
        return (
            f"{weakest.pattern_id} needs implementation reps — "
            f"recognition alone will not unlock what follows"
        )
    return f"Nothing due. Reinforcing your weakest pattern: {weakest.pattern_id}"


def next_review_at(conn: sqlite3.Connection) -> datetime | None:
    """When the next card falls due, for the 'come back at' line on the home screen."""
    row = conn.execute("SELECT MIN(due_at) FROM card WHERE last_review_at IS NOT NULL").fetchone()
    return datetime.fromisoformat(row[0]) if row and row[0] else None
