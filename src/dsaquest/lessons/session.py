"""Running a training session under a master.

The loop this drives is the whole product:

    TEACH a secret  ->  DRILL it until fluent  ->  TRIAL with nothing named

Respect is deliberately **not** awarded per drill. Drills are cheap and
numerous; paying for each would make grinding the fastest route to a master's
regard, which is exactly what the design forbids. Respect arrives at the
moments that actually mean something: reaching fluency on a secret, passing a
trial, and passing the final test.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..domain.lesson import Curriculum, Drill, Secret, Stage
from ..storage import repositories as repo
from ..storage.repositories import SecretProgress
from ..world.character import Master, speak
from .plan import DrillVerdict, assess, check_answer, next_drill

#: Respect awarded at the moments that represent real progress.
RESPECT_FLUENT = 3
RESPECT_TRIAL = 10
RESPECT_FINAL_TEST = 50
RESPECT_FAILURE = -1

#: Correct drills in a row before the master acknowledges the run at all.
STREAK_ACKNOWLEDGED = 4


@dataclass(frozen=True, slots=True)
class Teaching:
    """Everything the master says and shows when introducing a secret."""

    secret: Secret
    intro: str
    memorise_line: str | None
    stage_number: int
    stage_count: int

    @property
    def must_memorise(self) -> bool:
        return self.secret.memorise


@dataclass(frozen=True, slots=True)
class DrillOutcome:
    drill: Drill
    correct: bool
    given: str
    master_line: str
    explanation: str
    verdict: DrillVerdict
    progress: SecretProgress
    respect_delta: int
    became_fluent: bool


def current_stage(conn: sqlite3.Connection, curriculum: Curriculum) -> Stage | None:
    """The stage the student is on: the first not yet fluent or tested.

    Stages are strictly ordered because each secret builds on the last —
    counting set bits is derived from clearing the lowest one.
    """
    for stage in curriculum.ordered_stages:
        progress = repo.ensure_secret(conn, curriculum.master_id, stage.secret.id)
        if not progress.is_fluent:
            return stage
    return None


def progress_summary(
    conn: sqlite3.Connection, curriculum: Curriculum
) -> tuple[tuple[Stage, SecretProgress], ...]:
    return tuple(
        (stage, repo.ensure_secret(conn, curriculum.master_id, stage.secret.id))
        for stage in curriculum.ordered_stages
    )


def teach(
    conn: sqlite3.Connection,
    master: Master,
    curriculum: Curriculum,
    stage: Stage,
    *,
    seed: int = 0,
) -> Teaching:
    """Deliver the lesson and record that it was given."""
    repo.mark_taught(conn, curriculum.master_id, stage.secret.id)
    stages = curriculum.ordered_stages
    return Teaching(
        secret=stage.secret,
        intro=speak(conn, master, "lesson_intro", seed=seed, secret=stage.secret.name),
        memorise_line=(
            speak(conn, master, "lesson_memorise", seed=seed, idiom=stage.secret.idiom)
            if stage.secret.memorise
            else None
        ),
        stage_number=stages.index(stage) + 1,
        stage_count=len(stages),
    )


def deal(
    conn: sqlite3.Connection, curriculum: Curriculum, stage: Stage, *, seed: int
) -> Drill | None:
    """Choose the next drill for this stage, or None if there is nothing left."""
    master_id = curriculum.master_id
    secret_id = stage.secret.id
    progress = repo.ensure_secret(conn, master_id, secret_id)
    return next_drill(
        stage.secret,
        progress,
        answered=repo.drills_answered(conn, master_id, secret_id),
        kinds_passed=repo.drill_kinds_passed(conn, master_id, secret_id),
        seed=seed,
        failure_streak=repo.drill_failure_streak(conn, master_id, secret_id),
    )


def grade(
    conn: sqlite3.Connection,
    master: Master,
    curriculum: Curriculum,
    stage: Stage,
    drill: Drill,
    given: str,
    *,
    duration_ms: int | None = None,
    seed: int = 0,
) -> DrillOutcome:
    """Mark one drill, advance the state machine, and choose what the master says."""
    master_id = curriculum.master_id
    secret = stage.secret
    correct = check_answer(drill, given)

    progress = repo.record_drill(
        conn,
        master_id=master_id,
        secret_id=secret.id,
        drill_id=drill.id,
        kind=drill.kind.value,
        correct=correct,
        given=given,
        duration_ms=duration_ms,
    )

    kinds_passed = repo.drill_kinds_passed(conn, master_id, secret.id)
    verdict = assess(secret, progress, kinds_passed)

    became_fluent = verdict.fluent and not progress.is_fluent
    respect_delta = 0
    if became_fluent:
        repo.set_secret_state(conn, master_id, secret.id, "fluent")
        respect_delta = RESPECT_FLUENT
        progress = repo.get_secret_progress(conn, master_id, secret.id)
    elif verdict.exhausted:
        # Not fluent, but grinding is not working. Move on; spaced repetition
        # brings it back. No respect lost — the student did the work.
        repo.set_secret_state(conn, master_id, secret.id, "drilling")

    if respect_delta:
        repo.add_respect(conn, master_id, respect_delta)

    return DrillOutcome(
        drill=drill,
        correct=correct,
        given=given,
        master_line=_line_for(conn, master, correct, progress, seed=seed),
        explanation=drill.explanation,
        verdict=verdict,
        progress=progress,
        respect_delta=respect_delta,
        became_fluent=became_fluent,
    )


def _line_for(
    conn: sqlite3.Connection,
    master: Master,
    correct: bool,
    progress: SecretProgress,
    *,
    seed: int,
) -> str:
    """Which pool fits what just happened.

    A streak is acknowledged only once it is genuinely a run. Congratulating a
    second correct answer would make the praise worthless by the fifth.
    """
    if not correct:
        return speak(conn, master, "drill_wrong", seed=seed)
    if progress.consecutive_correct >= STREAK_ACKNOWLEDGED:
        return speak(conn, master, "drill_streak", seed=seed, streak=progress.consecutive_correct)
    return speak(conn, master, "drill_correct", seed=seed)


def greet(conn: sqlite3.Connection, master: Master, *, seed: int = 0) -> str:
    """What the master says on arrival. Absence is something he notices."""
    from ..world.character import greeting_pool

    days = repo.days_since_seen(conn, master.id)
    pool = greeting_pool(days)
    line = speak(conn, master, pool, seed=seed, days=days if days is not None else 0)
    # Touch respect so last_seen advances even when nothing is earned today.
    repo.add_respect(conn, master.id, 0)
    return line


def training_complete(conn: sqlite3.Connection, curriculum: Curriculum) -> bool:
    """Every secret drilled to fluency — the final test becomes available."""
    return current_stage(conn, curriculum) is None
