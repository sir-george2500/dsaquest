"""Recording an exercise — where every subsystem meets.

One completed exercise has to move six things at once: the attempt log, the
FSRS card, XP, the streak, unlocks, and achievements. Doing that in one place
with one transaction is what keeps them consistent; scattering it across the UI
is how a crash mid-award leaves a card scheduled for a review that no log
explains.

The order matters and is deliberate:

1. Decide the rating *before* touching XP, because "was this card due?" must be
   read from the pre-review state.
2. Award XP from the outcome, never from the rating — XP is for showing up and
   doing the work; the rating is for scheduling. Conflating them would mean an
   honest ``Again`` costs you money, which is a direct incentive to cheat.
3. Persist everything together.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from fsrs import Scheduler

from ..content.loader import PatternLibrary
from ..domain.enums import Difficulty, GameMode, MistakeCode, Rating, Verdict
from ..learning.fsrs_bridge import apply_review
from ..learning.mastery import PatternMastery, all_mastery
from ..learning.par import par_ms
from ..learning.rating import ReviewOutcome, rate
from ..storage import repositories as repo
from ..storage.db import transaction
from ..storage.repositories import CardRecord, Streak
from . import achievements as ach
from .levels import LevelProgress, levelled_up, progress
from .unlocks import refresh_unlocks
from .xp import XpAward, award


@dataclass(frozen=True, slots=True)
class ExerciseResult:
    """What the UI observed. Everything else is derived from this."""

    correct: bool
    duration_ms: int
    verdict: Verdict | None = None
    chosen_pattern_id: str | None = None
    hints_used: int = 0
    tries: int = 1
    self_grade: Rating | None = None
    essential_missed: bool = False
    mistakes: tuple[MistakeCode, ...] = field(default_factory=tuple)
    source: str | None = None
    tests_passed: int = 0
    tests_total: int = 0
    max_cpu_ms: int | None = None
    max_memory_kb: int | None = None
    compile_log: str = ""


@dataclass(frozen=True, slots=True)
class RecordedOutcome:
    attempt_id: int
    xp: XpAward
    xp_total: int
    rating: Rating | None
    card: CardRecord | None
    levels_gained: tuple[int, ...]
    level: LevelProgress
    streak: Streak
    newly_unlocked: tuple[str, ...]
    achievements: tuple[ach.Achievement, ...]
    was_due: bool

    @property
    def levelled_up(self) -> bool:
        return bool(self.levels_gained)


def begin_exercise(
    conn: sqlite3.Connection,
    *,
    pattern_id: str,
    mode: GameMode,
    seed: int,
    difficulty: Difficulty = Difficulty.MEDIUM,
    problem_id: str | None = None,
    session_id: int | None = None,
) -> int:
    """Open an attempt and return its id. Pairs with :func:`complete_exercise`.

    Split from completion so ``started_at`` is the moment the learner saw the
    problem, not the moment they submitted — otherwise every attempt looks
    instantaneous and the speed dimension is meaningless.
    """
    return repo.start_attempt(
        conn,
        pattern_id=pattern_id,
        mode=mode,
        seed=seed,
        problem_id=problem_id,
        difficulty=difficulty.value,
        session_id=session_id,
        par_ms=par_ms(mode, difficulty),
    )


def complete_exercise(
    conn: sqlite3.Connection,
    attempt_id: int,
    result: ExerciseResult,
    *,
    library: PatternLibrary,
    scheduler: Scheduler,
    pattern_id: str,
    mode: GameMode,
    difficulty: Difficulty = Difficulty.MEDIUM,
    now: datetime | None = None,
    today: date | None = None,
) -> RecordedOutcome:
    at = now or datetime.now(UTC)
    local_today = today or at.astimezone().date()

    card = repo.get_card(conn, pattern_id, mode.trains)
    was_due = card.due_at <= at.isoformat(timespec="seconds")
    repeats_today = repo.attempts_today(conn, pattern_id, today=local_today)

    rating = rate(
        ReviewOutcome(
            mode=mode,
            correct=result.correct,
            hints_used=result.hints_used,
            tries=result.tries,
            duration_ms=result.duration_ms,
            par_ms=par_ms(mode, difficulty),
            verdict=result.verdict,
            self_grade=result.self_grade,
            essential_missed=result.essential_missed,
        )
    )

    streak_before = repo.get_streak(conn, "daily", today=local_today)
    xp = award(
        mode=mode,
        correct=result.correct,
        difficulty=difficulty,
        repeats_today=repeats_today,
        was_due=was_due,
        streak_days=streak_before.current,
        hints_used=result.hints_used,
        tries=result.tries,
    )

    xp_before = repo.get_profile(conn).xp

    with transaction(conn):
        repo.finish_attempt(
            conn,
            attempt_id,
            correct=result.correct,
            verdict=result.verdict,
            chosen_pattern_id=result.chosen_pattern_id,
            hints_used=result.hints_used,
            tries=result.tries,
            duration_ms=result.duration_ms,
            xp_awarded=xp.total,
        )
        if result.source is not None and result.verdict is not None:
            repo.record_submission(
                conn,
                attempt_id=attempt_id,
                source=result.source,
                verdict=result.verdict,
                tests_passed=result.tests_passed,
                tests_total=result.tests_total,
                max_cpu_ms=result.max_cpu_ms,
                max_memory_kb=result.max_memory_kb,
                compile_log=result.compile_log,
            )
        for code in result.mistakes:
            repo.record_mistake(conn, attempt_id=attempt_id, pattern_id=pattern_id, code=code)
        xp_total = repo.add_xp(conn, xp.total) if xp.total else xp_before
        streak = repo.touch_streak(conn, "daily", today=local_today)

    # The scheduler update runs in its own transaction inside apply_review.
    updated_card: CardRecord | None = None
    if rating is not None:
        updated_card = apply_review(
            conn,
            card,
            rating,
            scheduler=scheduler,
            mode=mode,
            now=at,
            attempt_id=attempt_id,
            duration_ms=result.duration_ms,
        )

    mastery = all_mastery(conn, library, scheduler=scheduler, now=at)
    newly_unlocked = refresh_unlocks(conn, library, mastery)
    unlocked_achievements = ach.evaluate(
        conn, build_snapshot(conn, library, mastery, streak=streak, xp_total=xp_total)
    )

    return RecordedOutcome(
        attempt_id=attempt_id,
        xp=xp,
        xp_total=xp_total,
        rating=rating,
        card=updated_card,
        levels_gained=levelled_up(xp_before, xp_total),
        level=progress(xp_total),
        streak=streak,
        newly_unlocked=newly_unlocked,
        achievements=unlocked_achievements,
        was_due=was_due,
    )


def build_snapshot(
    conn: sqlite3.Connection,
    library: PatternLibrary,
    mastery: dict[str, PatternMastery],
    *,
    streak: Streak,
    xp_total: int,
) -> ach.Snapshot:
    mastered = [m for m in mastery.values() if m.unlocks_dependents]
    return ach.Snapshot(
        level=progress(xp_total).level,
        xp=xp_total,
        daily_streak=streak.current,
        best_daily_streak=streak.best,
        patterns_started=sum(1 for m in mastery.values() if m.started),
        patterns_mastered=len(mastered),
        patterns_total=len(library),
        implementations_passed=repo.implementations_passed(conn),
        perfect_bosses=repo.perfect_boss_count(conn),
        sessions=repo.sessions_completed(conn),
        # A recovery is a pattern that has genuinely lapsed and has since been
        # brought back — the behaviour worth rewarding, because the alternative
        # is quietly abandoning anything you got wrong.
        recovered_lapses=sum(
            1 for m in mastered if any(dimension.lapses > 0 for dimension in m.dimensions)
        ),
        fastest_solve_ratio=repo.best_solve_ratio(conn),
    )
