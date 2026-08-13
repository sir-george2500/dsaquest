"""The trial — where the master stops teaching and starts testing.

This is the third beat of the loop and the one that gives the other two their
point:

    TEACH  ->  DRILL  ->  **TRIAL**

The drills named the pattern on every screen. The trial names nothing. It hands
over a real problem statement and asks the only question that matters: *do you
see it?*

A clock runs, because recognising a pattern eventually has to happen under
pressure. It is a generous clock, and running out of it is explicitly **not**
treated as forgetting — see ``timing.limits`` and the timeout rule in
``learning.rating``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from fsrs import Scheduler

from ..content.loader import PatternLibrary
from ..content.problems import ProblemBank
from ..domain.enums import Difficulty, GameMode
from ..domain.lesson import Curriculum, Stage
from ..domain.problem import Problem
from ..game.modes.hunter import HunterRound, build_round, confusion_counts, judge_round
from ..game.session import ExerciseResult, RecordedOutcome, begin_exercise, complete_exercise
from ..storage import repositories as repo
from ..timing import Phase, PhaseTiming, PressureStage, Stopwatch, TimeBudget, budget_for
from ..world.character import Master, speak
from .session import RESPECT_FAILURE, RESPECT_TRIAL


@dataclass(frozen=True, slots=True)
class Trial:
    """A live trial: a hidden-pattern problem with a clock on it."""

    stage: Stage
    problem: Problem
    round: HunterRound
    budget: TimeBudget
    attempt_id: int
    intro: str
    watch: Stopwatch

    @property
    def secret_name(self) -> str:
        return self.stage.secret.name


@dataclass(frozen=True, slots=True)
class TrialVerdict:
    correct: bool
    timed_out: bool
    chosen_pattern_id: str
    actual_pattern_id: str
    master_line: str
    tell: str
    why: str
    respect_delta: int
    respect_total: int
    outcome: RecordedOutcome
    elapsed_ms: int

    @property
    def passed(self) -> bool:
        return self.correct and not self.timed_out


def pending_trial(conn: sqlite3.Connection, curriculum: Curriculum) -> Stage | None:
    """The first stage that is fluent but has not yet been tested.

    A stage with no trial problems authored is marked tested immediately rather
    than blocking progress — the curriculum should not stall on missing content.
    """
    for stage in curriculum.ordered_stages:
        progress = repo.ensure_secret(conn, curriculum.master_id, stage.secret.id)
        if not progress.is_fluent:
            return None  # earlier stages must be drilled first
        if progress.state == "tested":
            continue
        if not stage.trial_problem_ids:
            repo.set_secret_state(conn, curriculum.master_id, stage.secret.id, "tested")
            continue
        return stage
    return None


def open_trial(
    conn: sqlite3.Connection,
    master: Master,
    library: PatternLibrary,
    bank: ProblemBank,
    curriculum: Curriculum,
    stage: Stage,
    *,
    seed: int,
    now: datetime | None = None,
) -> Trial:
    """Present the trial problem with the pattern hidden and the clock running."""
    problem_id = stage.trial_problem_ids[seed % len(stage.trial_problem_ids)]
    problem = bank[problem_id]

    round_ = build_round(
        library,
        problem,
        seed=seed,
        history=confusion_counts(conn, problem.pattern),
    )

    budget = budget_for(conn, GameMode.HUNTER, problem.difficulty, stage=PressureStage.TRIAL)

    attempt_id = begin_exercise(
        conn,
        pattern_id=problem.pattern,
        mode=GameMode.HUNTER,
        seed=seed,
        difficulty=problem.difficulty,
        problem_id=problem.id,
    )

    watch = Stopwatch()
    watch.start(Phase.RECOGNISE)

    return Trial(
        stage=stage,
        problem=problem,
        round=round_,
        budget=budget,
        attempt_id=attempt_id,
        intro=speak(conn, master, "trial_intro", seed=seed, secret=stage.secret.name),
        watch=watch,
    )


def judge_trial(
    conn: sqlite3.Connection,
    master: Master,
    library: PatternLibrary,
    curriculum: Curriculum,
    trial: Trial,
    chosen_index: int | None,
    *,
    scheduler: Scheduler,
    seed: int,
    now: datetime | None = None,
) -> TrialVerdict:
    """Grade the trial and deliver the master's judgement.

    ``chosen_index`` is ``None`` when the clock ran out before an answer.
    """
    trial.watch.stop()
    timing = PhaseTiming.from_stopwatch(trial.watch)
    elapsed = trial.watch.elapsed_ms
    timed_out = chosen_index is None or trial.budget.expired(elapsed)

    if chosen_index is None:
        chosen = ""
        correct = False
        tell = ""
    else:
        feedback = judge_round(library, trial.round, chosen_index)
        chosen = feedback.chosen_pattern_id
        correct = feedback.correct and not timed_out
        tell = feedback.tell

    outcome = complete_exercise(
        conn,
        trial.attempt_id,
        ExerciseResult(
            correct=correct,
            duration_ms=elapsed,
            chosen_pattern_id=chosen or None,
            timed_out=timed_out,
            phase_breakdown={phase.value: ms for phase, ms in timing.breakdown.items()},
            limit_ms=trial.budget.limit_ms,
            pressure_stage=int(PressureStage.TRIAL),
        ),
        library=library,
        scheduler=scheduler,
        pattern_id=trial.problem.pattern,
        mode=GameMode.HUNTER,
        difficulty=trial.problem.difficulty,
        now=now,
    )

    if correct:
        repo.set_secret_state(conn, curriculum.master_id, trial.stage.secret.id, "tested")
        respect_delta = RESPECT_TRIAL
        pool = "success_fast" if elapsed <= trial.budget.target_ms else "success"
    elif timed_out:
        # Not a knowledge failure. It costs respect, never the memory model.
        respect_delta = RESPECT_FAILURE
        pool = "fail_timeout"
    else:
        respect_delta = RESPECT_FAILURE
        pool = "fail_wrong_pattern"

    respect_total = repo.add_respect(conn, master.id, respect_delta)

    return TrialVerdict(
        correct=correct,
        timed_out=timed_out,
        chosen_pattern_id=chosen,
        actual_pattern_id=trial.problem.pattern,
        master_line=speak(
            conn, master, pool, seed=seed, secret=trial.stage.secret.name, attempts=1
        ),
        tell=tell,
        why=trial.problem.why,
        respect_delta=respect_delta,
        respect_total=respect_total,
        outcome=outcome,
        elapsed_ms=elapsed,
    )


def trial_difficulty(problem: Problem) -> Difficulty:
    return problem.difficulty


def all_trials_passed(conn: sqlite3.Connection, curriculum: Curriculum) -> bool:
    """Every secret drilled *and* tested — the final test becomes available."""
    return all(
        repo.ensure_secret(conn, curriculum.master_id, stage.secret.id).state == "tested"
        for stage in curriculum.ordered_stages
    )


def now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)
