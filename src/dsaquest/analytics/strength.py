"""Warrior Strength — seven dimensions, aggregated across every pattern.

Strength is never "problems solved". Each dimension is derived so that grinding
easy content cannot inflate it, and the weights say plainly what this product
believes: understanding counts for most, speed for least.

Two of the seven exist specifically to resist gaming:

* **Problem Solving** is measured *only* where the pattern was hidden. An
  exercise that names its pattern tests fluency, and counting those here would
  let drilling do the work.
* **Consistency** is the one dimension talent cannot shortcut. It rewards
  turning up and coming back after a bad session, which is the behaviour that
  actually produces retention.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from fsrs import Scheduler

from ..content.loader import PatternLibrary
from ..learning.mastery import PatternMastery, all_mastery
from ..storage import repositories as repo

#: How much each dimension contributes. Understanding highest, speed lowest.
WEIGHTS: dict[str, float] = {
    "understanding": 0.22,
    "implementation": 0.20,
    "recognition": 0.18,
    "problem_solving": 0.16,
    "retention": 0.12,
    "consistency": 0.08,
    "speed": 0.04,
}

#: Practising this many days out of the last 28 counts as full consistency.
#: Not 28: demanding perfect attendance would make one missed day feel like
#: failure, which is how streak mechanics turn into a reason to quit.
CONSISTENT_DAYS = 20

#: Comebacks needed for full credit on the recovery half of consistency.
COMEBACK_TARGET = 5

#: Split of the consistency score between showing up and coming back.
ATTENDANCE_SHARE = 0.75


@dataclass(frozen=True, slots=True)
class Dimension:
    key: str
    label: str
    value: float | None
    detail: str = ""

    @property
    def known(self) -> bool:
        return self.value is not None

    @property
    def percent(self) -> int:
        return int(round((self.value or 0.0) * 100))

    def bar(self, width: int = 20) -> str:
        if self.value is None:
            return "·" * width
        filled = int(round(self.value * width))
        return "█" * filled + "░" * (width - filled)


@dataclass(frozen=True, slots=True)
class WarriorStrength:
    dimensions: tuple[Dimension, ...]
    overall: float
    patterns_started: int
    patterns_total: int

    def __getitem__(self, key: str) -> Dimension:
        for dimension in self.dimensions:
            if dimension.key == key:
                return dimension
        raise KeyError(key)

    @property
    def score(self) -> int:
        return int(round(self.overall * 100))

    @property
    def weakest(self) -> Dimension | None:
        known = [d for d in self.dimensions if d.known and d.value is not None]
        return min(known, key=lambda d: d.value or 0.0) if known else None

    @property
    def strongest(self) -> Dimension | None:
        known = [d for d in self.dimensions if d.known and d.value is not None]
        return max(known, key=lambda d: d.value or 0.0) if known else None

    @property
    def started(self) -> bool:
        return self.patterns_started > 0


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _consistency(conn: sqlite3.Connection) -> tuple[float, str]:
    days = repo.active_days(conn, within=28)
    recoveries = repo.comebacks(conn)

    attendance = min(1.0, days / CONSISTENT_DAYS)
    recovery = min(1.0, recoveries / COMEBACK_TARGET)
    value = ATTENDANCE_SHARE * attendance + (1 - ATTENDANCE_SHARE) * recovery

    detail = f"{days} of the last 28 days"
    if recoveries:
        detail += f", {recoveries} comeback{'s' if recoveries != 1 else ''}"
    return value, detail


def compute(
    conn: sqlite3.Connection,
    library: PatternLibrary,
    *,
    scheduler: Scheduler,
    now: datetime | None = None,
) -> WarriorStrength:
    at = now or datetime.now(UTC)
    mastery: dict[str, PatternMastery] = all_mastery(conn, library, scheduler=scheduler, now=at)
    started = [m for m in mastery.values() if m.started]

    recognition = _mean([m.recognition.score for m in started])
    understanding = _mean([m.recall.score for m in started])
    implementation = _mean([m.implementation.score for m in started])
    retention = _mean([m.retention for m in started])
    speed = _mean([m.speed for m in started if m.speed is not None])

    problem_solving = repo.unaided_accuracy(conn)
    consistency, consistency_detail = _consistency(conn)

    dimensions = (
        Dimension(
            "recognition",
            "Pattern Recognition",
            recognition,
            "unlabelled statements",
        ),
        Dimension(
            "understanding",
            "Conceptual Understanding",
            understanding,
            "invariant and complexity",
        ),
        Dimension("implementation", "Implementation", implementation, "correct C++ under time"),
        Dimension(
            "problem_solving",
            "Problem Solving",
            problem_solving,
            "unaided only",
        ),
        Dimension("retention", "Retention", retention, "weakest per pattern"),
        Dimension("speed", "Speed", speed, "median against par"),
        Dimension("consistency", "Consistency", consistency, consistency_detail),
    )

    # Unknown dimensions are skipped rather than counted as zero: a learner who
    # has not met a mode yet is not bad at it, and scoring them as such would
    # make the number meaningless on day one.
    weighted = sum(WEIGHTS[d.key] * (d.value or 0.0) for d in dimensions if d.known)
    total_weight = sum(WEIGHTS[d.key] for d in dimensions if d.known)
    overall = weighted / total_weight if total_weight else 0.0

    return WarriorStrength(
        dimensions=dimensions,
        overall=overall,
        patterns_started=len(started),
        patterns_total=len(library),
    )


def rank_title(score: int) -> str:
    """The warrior's standing, from the journey in the design document."""
    for threshold, title in (
        (90, "Elite Challenger"),
        (75, "Competitive Programmer"),
        (60, "Algorithm Warrior"),
        (45, "Pattern Hunter"),
        (30, "Student of the Masters"),
        (15, "Apprentice"),
        (1, "Weak Warrior"),
    ):
        if score >= threshold:
            return title
    return "Novice"
