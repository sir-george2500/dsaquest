"""Achievements.

Kept deliberately small and deliberately aligned with the learning model. An
achievement for "answered 1000 questions" rewards volume; these reward the
behaviours that actually produce retention — coming back, closing the gap on a
weak pattern, and writing code rather than recognising it.

Each is a pure predicate over a snapshot, so they are trivially testable and
carry no state of their own.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from ..storage.db import utcnow


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Everything the predicates are allowed to look at."""

    level: int
    xp: int
    daily_streak: int
    best_daily_streak: int
    patterns_started: int
    patterns_mastered: int
    patterns_total: int
    implementations_passed: int
    perfect_bosses: int
    sessions: int
    recovered_lapses: int
    """Patterns that lapsed and were subsequently brought back to mastery."""
    fastest_solve_ratio: float | None
    """Best solve time as a fraction of par. Lower is faster."""


@dataclass(frozen=True, slots=True)
class Achievement:
    code: str
    name: str
    description: str
    predicate: Callable[[Snapshot], bool]
    hidden: bool = False


ACHIEVEMENTS: tuple[Achievement, ...] = (
    Achievement(
        "FIRST_BLOOD",
        "First Blood",
        "Pass your first implementation.",
        lambda s: s.implementations_passed >= 1,
    ),
    Achievement(
        "WEEK_ONE",
        "Habit Forming",
        "Practise seven days running.",
        lambda s: s.daily_streak >= 7,
    ),
    Achievement(
        "MONTH_ONE",
        "Ritual",
        "Practise thirty days running.",
        lambda s: s.daily_streak >= 30,
    ),
    Achievement(
        "PATTERN_HUNTER",
        "Pattern Hunter",
        "Reach level 10.",
        lambda s: s.level >= 10,
    ),
    Achievement(
        "FIRST_MASTERY",
        "Internalised",
        "Bring a pattern to full mastery.",
        lambda s: s.patterns_mastered >= 1,
    ),
    Achievement(
        "WORLD_ONE",
        "Foundations",
        "Master every pattern in World 1.",
        lambda s: s.patterns_mastered >= 4,
    ),
    Achievement(
        "COMPLETIONIST",
        "Full Deck",
        "Master every pattern in the game.",
        lambda s: s.patterns_total > 0 and s.patterns_mastered >= s.patterns_total,
    ),
    Achievement(
        "FLAWLESS",
        "Flawless",
        "Clear a Boss Fight first try with no hints.",
        lambda s: s.perfect_bosses >= 1,
    ),
    Achievement(
        "COMEBACK",
        "Comeback",
        "Recover a pattern you had forgotten back to mastery.",
        lambda s: s.recovered_lapses >= 1,
    ),
    Achievement(
        "SPEED_DEMON",
        "Sharp",
        "Solve a problem in under half its par time.",
        lambda s: s.fastest_solve_ratio is not None and s.fastest_solve_ratio < 0.5,
    ),
)

BY_CODE: dict[str, Achievement] = {a.code: a for a in ACHIEVEMENTS}


def earned(conn: sqlite3.Connection) -> set[str]:
    return {row["code"] for row in conn.execute("SELECT code FROM achievement")}


def evaluate(conn: sqlite3.Connection, snapshot: Snapshot) -> tuple[Achievement, ...]:
    """Award any newly satisfied achievements; return them for celebration.

    Awarding is idempotent — an achievement already held is never re-awarded,
    even if its condition lapses and is met again.
    """
    already = earned(conn)
    unlocked: list[Achievement] = []

    for achievement in ACHIEVEMENTS:
        if achievement.code in already:
            continue
        if achievement.predicate(snapshot):
            conn.execute(
                "INSERT OR IGNORE INTO achievement (code, unlocked_at, detail) VALUES (?, ?, ?)",
                (achievement.code, utcnow(), achievement.name),
            )
            unlocked.append(achievement)

    return tuple(unlocked)
