"""The mastery model.

Six numbers, of two different kinds — and keeping them apart is the point.

**Scheduled** (each owns an FSRS memory state, each independently due):
recognition, recall, implementation.

**Derived** (computed from the event log, never scheduled):
speed, accuracy, retention.

Overall mastery is a weighted blend of the *scheduled three only*. Speed and
accuracy are deliberately excluded from it despite being displayed, because
they already fed the rating rubric that produced those memory states — folding
them in again would count the same evidence twice and make a fast learner look
better-retained than they are.

The gate
--------
Two rules, both guarding the same claim: *mastery means you can use the
pattern*, and you cannot use a pattern you cannot implement.

1. **You must have written the code.** Overall is capped at ``GATE_CAP`` until
   implementation has ``GATE_MIN_IMPLEMENTATION_REPS`` reviews behind it.
   Recognising Monotonic Stack in a four-way multiple choice is not knowing it.

2. **Overall can never outrun implementation.** Rule 1 alone counts *attempts*,
   not success — a learner who failed six implementation reviews still clears
   it, and would unlock dependents on the strength of recognition and recall
   while being unable to write a line. So overall is additionally capped at
   implementation's own score plus a small slack.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from fsrs import Scheduler

from ..content.loader import PatternLibrary
from ..domain.enums import Dimension, GameMode
from ..storage import repositories as repo
from ..storage.repositories import CardRecord
from .fsrs_bridge import retrievability

#: Stability at which a memory counts as fully consolidated. Three weeks is the
#: point past which material behaves like something you know rather than
#: something you recently studied.
MATURE_STABILITY_DAYS = 21.0

#: How much each scheduled dimension contributes to overall mastery.
#: Implementation dominates because it is the only one that cannot be faked.
DIMENSION_WEIGHTS: dict[Dimension, float] = {
    Dimension.RECOGNITION: 0.30,
    Dimension.RECALL: 0.25,
    Dimension.IMPLEMENTATION: 0.45,
}

#: Within a dimension, consolidation matters more than current recall
#: probability. R swings between ~1.0 just after a review and the target
#: retention just before the next one; weighting it heavily would make mastery
#: visibly oscillate day to day and make unlocks flicker.
MATURITY_WEIGHT = 0.65
RETRIEVABILITY_WEIGHT = 0.35

#: Ceiling applied until the implementation gate is satisfied.
GATE_CAP = 0.60
GATE_MIN_IMPLEMENTATION_REPS = 3

#: How far overall mastery may exceed implementation mastery.
#:
#: Small and non-zero: recognising and recalling a pattern genuinely is worth
#: something beyond writing it, but not much. Without this cap a learner who
#: keeps failing implementation still accumulates reps, clears the reps gate,
#: and unlocks dependents on recognition alone.
IMPLEMENTATION_SLACK = 0.15

#: Mastery a prerequisite must reach before it unlocks what depends on it.
UNLOCK_THRESHOLD = 0.65


@dataclass(frozen=True, slots=True)
class DimensionMastery:
    dimension: Dimension
    seen: bool
    retrievability: float
    maturity: float
    stability_days: float
    difficulty: float | None
    reps: int
    lapses: int
    due_at: str

    @property
    def score(self) -> float:
        if not self.seen:
            return 0.0
        return MATURITY_WEIGHT * self.maturity + RETRIEVABILITY_WEIGHT * self.retrievability


@dataclass(frozen=True, slots=True)
class PatternMastery:
    pattern_id: str
    recognition: DimensionMastery
    recall: DimensionMastery
    implementation: DimensionMastery
    speed: float | None
    accuracy: float | None
    overall: float
    gated: bool

    @property
    def dimensions(self) -> tuple[DimensionMastery, ...]:
        return (self.recognition, self.recall, self.implementation)

    @property
    def retention(self) -> float:
        """Recall probability of the *weakest* dimension right now.

        The minimum rather than the mean: a pattern you can recognise but no
        longer implement is not 70% retained, it is a pattern you cannot use.
        """
        seen = [d.retrievability for d in self.dimensions if d.seen]
        return min(seen) if seen else 0.0

    @property
    def started(self) -> bool:
        return any(d.seen for d in self.dimensions)

    @property
    def weakest(self) -> DimensionMastery:
        return min(self.dimensions, key=lambda d: d.score)

    @property
    def unlocks_dependents(self) -> bool:
        return self.overall >= UNLOCK_THRESHOLD


def _dimension_mastery(
    card: CardRecord, *, scheduler: Scheduler, now: datetime
) -> DimensionMastery:
    stability = float(card.stability or 0.0)
    return DimensionMastery(
        dimension=card.dimension,
        seen=not card.is_new,
        retrievability=retrievability(card, scheduler=scheduler, now=now),
        maturity=min(1.0, stability / MATURE_STABILITY_DAYS),
        stability_days=stability,
        difficulty=card.difficulty,
        reps=card.reps,
        lapses=card.lapses,
        due_at=card.due_at,
    )


def _speed_score(conn: sqlite3.Connection, pattern_id: str) -> float | None:
    """Median solve time against par, as a 0-1 score. ``None`` without history.

    Capped at 1.0 — being faster than par is not extra mastery, it is just
    fast, and letting it exceed 1 would let speed paper over weak retention.
    """
    from .par import par_ms

    for mode in (GameMode.SOLVE, GameMode.COMPLETE):
        median = repo.median_duration_ms(conn, pattern_id, mode)
        if median:
            return min(1.0, par_ms(mode) / median)
    return None


def pattern_mastery(
    conn: sqlite3.Connection,
    pattern_id: str,
    *,
    scheduler: Scheduler,
    now: datetime | None = None,
) -> PatternMastery:
    at = now or datetime.now(UTC)
    cards = {c.dimension: c for c in repo.cards_for(conn, pattern_id)}
    if len(cards) != len(Dimension):
        raise LookupError(
            f"{pattern_id} has {len(cards)} of {len(Dimension)} cards; run ensure_cards first"
        )

    per_dimension = {
        dim: _dimension_mastery(cards[dim], scheduler=scheduler, now=at) for dim in Dimension
    }

    raw = sum(per_dimension[dim].score * weight for dim, weight in DIMENSION_WEIGHTS.items())

    implementation = per_dimension[Dimension.IMPLEMENTATION]

    # Rule 2: overall may not outrun implementation by more than the slack.
    # Applied before the reps gate so that failing repeatedly cannot buy its way
    # past rule 1 simply by accumulating attempts.
    overall = min(raw, implementation.score + IMPLEMENTATION_SLACK)

    # Rule 1: you must actually have written the code, several times.
    gated = implementation.reps < GATE_MIN_IMPLEMENTATION_REPS
    if gated:
        overall = min(overall, GATE_CAP)

    return PatternMastery(
        pattern_id=pattern_id,
        recognition=per_dimension[Dimension.RECOGNITION],
        recall=per_dimension[Dimension.RECALL],
        implementation=implementation,
        speed=_speed_score(conn, pattern_id),
        accuracy=repo.accuracy(conn, pattern_id),
        # Deliberately not rounded: rounding here can round *up* past the very
        # cap just applied, breaking the invariant by a few parts per million.
        # Formatting is the display layer's job.
        overall=overall,
        gated=gated,
    )


def all_mastery(
    conn: sqlite3.Connection,
    library: PatternLibrary,
    *,
    scheduler: Scheduler,
    now: datetime | None = None,
) -> dict[str, PatternMastery]:
    at = now or datetime.now(UTC)
    return {
        pattern.id: pattern_mastery(conn, pattern.id, scheduler=scheduler, now=at)
        for pattern in library
    }


def available_patterns(
    library: PatternLibrary, mastery: dict[str, PatternMastery]
) -> tuple[str, ...]:
    """Patterns whose prerequisites are all sufficiently mastered.

    Walks the prerequisite DAG rather than the world list, so a pattern becomes
    available the moment its own prerequisites are met — you are never made to
    grind through an unrelated corner of a world to reach the next thing.
    """
    available: list[str] = []
    for pattern in library:
        if all(
            pattern_id in mastery and mastery[pattern_id].unlocks_dependents
            for pattern_id in pattern.prerequisites
        ):
            available.append(pattern.id)
    return tuple(available)


def weakest_patterns(
    mastery: dict[str, PatternMastery], *, among: tuple[str, ...] | None = None, limit: int = 3
) -> tuple[PatternMastery, ...]:
    """Started patterns with the lowest mastery — what to practise next.

    Untouched patterns are excluded: they score 0.0 by definition and would
    otherwise permanently occupy every "weakest" slot, drowning out the
    patterns you have actually started and are actually losing.
    """
    pool = [
        m
        for pattern_id, m in mastery.items()
        if m.started and (among is None or pattern_id in among)
    ]
    return tuple(sorted(pool, key=lambda m: m.overall)[:limit])
