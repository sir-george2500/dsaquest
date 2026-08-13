"""The master's final test — every secret at once, nothing named.

A trial tests one secret shortly after teaching it, which is a fair test of
*that lesson*. The final test is different: it comes after all five, mixes them,
and gives no clue which is which. That gap between "I just learned this" and "I
have to pick it out of everything he taught me" is the whole point.

Rules that differ from a trial:

* **Several problems in a row**, drawn across every secret.
* **No hints at any point.**
* **A threshold, not perfection.** Requiring every answer would make one
  unlucky guess erase a week of work; requiring half would let guessing pass.
* **Passing is permanent.** A later rematch that goes badly does not un-prove
  what was proved.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from fsrs import Scheduler

from ..content.loader import PatternLibrary
from ..content.problems import ProblemBank
from ..domain.enums import GameMode
from ..domain.lesson import Curriculum
from ..domain.problem import Problem
from ..game.modes.hunter import HunterRound, build_round, confusion_counts, judge_round
from ..game.session import ExerciseResult, begin_exercise, complete_exercise
from ..storage import repositories as repo
from ..storage.repositories import MasterProgress
from ..timing import Phase, PhaseTiming, PressureStage, Stopwatch, TimeBudget, budget_for
from ..world.character import Master, speak
from .trial import all_trials_passed

#: Fraction of the test that must be answered correctly.
#:
#: Three of four. Demanding perfection would let one unlucky guess erase a
#: week's training; a simple majority would let guessing through on a four-way
#: choice often enough to be meaningless.
PASS_FRACTION = 0.75

RESPECT_FINAL_TEST = 50
RESPECT_FINAL_FAILURE = -2


@dataclass(frozen=True, slots=True)
class FinalRound:
    problem: Problem
    round: HunterRound
    budget: TimeBudget
    attempt_id: int
    watch: Stopwatch
    number: int
    total: int


@dataclass(frozen=True, slots=True)
class RoundOutcome:
    problem: Problem
    correct: bool
    timed_out: bool
    chosen_pattern_id: str
    elapsed_ms: int


@dataclass(slots=True)
class FinalTest:
    """A live sitting of the final test."""

    curriculum: Curriculum
    problems: tuple[Problem, ...]
    index: int = 0
    outcomes: list[RoundOutcome] = field(default_factory=list)
    current: FinalRound | None = None

    @property
    def total(self) -> int:
        return len(self.problems)

    @property
    def score(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.correct)

    @property
    def finished(self) -> bool:
        return self.index >= self.total

    @property
    def required(self) -> int:
        import math

        return math.ceil(self.total * PASS_FRACTION)

    @property
    def passed(self) -> bool:
        return self.score >= self.required

    @property
    def still_winnable(self) -> bool:
        """False once enough answers are wrong that the threshold is out of reach."""
        remaining = self.total - len(self.outcomes)
        return self.score + remaining >= self.required


@dataclass(frozen=True, slots=True)
class FinalVerdict:
    passed: bool
    score: int
    total: int
    required: int
    master_line: str
    respect_delta: int
    respect_total: int
    progress: MasterProgress
    weakest: tuple[str, ...]
    """Patterns missed in this sitting — what to train before returning."""


def available(conn: sqlite3.Connection, curriculum: Curriculum) -> bool:
    """The final test opens only once every secret is drilled and tested."""
    return all_trials_passed(conn, curriculum)


def open_test(
    conn: sqlite3.Connection, bank: ProblemBank, curriculum: Curriculum, *, seed: int
) -> FinalTest:
    problems = tuple(bank[pid] for pid in curriculum.final_test_problem_ids)
    if not problems:
        raise LookupError(f"{curriculum.master_id} has no final test problems")
    return FinalTest(curriculum=curriculum, problems=problems)


def next_round(
    conn: sqlite3.Connection,
    library: PatternLibrary,
    test: FinalTest,
    *,
    seed: int,
) -> FinalRound | None:
    """Present the next problem, or None when the sitting is over."""
    if test.finished:
        test.current = None
        return None

    problem = test.problems[test.index]
    round_ = build_round(
        library, problem, seed=seed, history=confusion_counts(conn, problem.pattern)
    )
    budget = budget_for(conn, GameMode.HUNTER, problem.difficulty, stage=PressureStage.BOSS)
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

    test.current = FinalRound(
        problem=problem,
        round=round_,
        budget=budget,
        attempt_id=attempt_id,
        watch=watch,
        number=test.index + 1,
        total=test.total,
    )
    return test.current


def answer_round(
    conn: sqlite3.Connection,
    library: PatternLibrary,
    test: FinalTest,
    chosen_index: int | None,
    *,
    scheduler: Scheduler,
) -> RoundOutcome:
    """Grade one round. No feedback is given until the sitting ends."""
    live = test.current
    assert live is not None, "no round is open"

    live.watch.stop()
    timing = PhaseTiming.from_stopwatch(live.watch)
    elapsed = live.watch.elapsed_ms
    timed_out = chosen_index is None or live.budget.expired(elapsed)

    if chosen_index is None:
        chosen, correct = "", False
    else:
        feedback = judge_round(library, live.round, chosen_index)
        chosen = feedback.chosen_pattern_id
        correct = feedback.correct and not timed_out

    complete_exercise(
        conn,
        live.attempt_id,
        ExerciseResult(
            correct=correct,
            duration_ms=elapsed,
            chosen_pattern_id=chosen or None,
            timed_out=timed_out,
            phase_breakdown={phase.value: ms for phase, ms in timing.breakdown.items()},
            limit_ms=live.budget.limit_ms,
            pressure_stage=int(PressureStage.BOSS),
        ),
        library=library,
        scheduler=scheduler,
        pattern_id=live.problem.pattern,
        mode=GameMode.HUNTER,
        difficulty=live.problem.difficulty,
    )

    outcome = RoundOutcome(
        problem=live.problem,
        correct=correct,
        timed_out=timed_out,
        chosen_pattern_id=chosen,
        elapsed_ms=elapsed,
    )
    test.outcomes.append(outcome)
    test.index += 1
    test.current = None
    return outcome


def conclude(
    conn: sqlite3.Connection,
    master: Master,
    test: FinalTest,
    *,
    seed: int,
) -> FinalVerdict:
    """Deliver the master's judgement on the whole sitting."""
    passed = test.passed
    progress = repo.record_final_test(
        conn, master.id, score=test.score, total=test.total, passed=passed
    )

    respect_delta = RESPECT_FINAL_TEST if passed else RESPECT_FINAL_FAILURE
    respect_total = repo.add_respect(conn, master.id, respect_delta)

    # praise_major is the rarest pool the master has. Passing his final test at
    # the first attempt is what it is for.
    if passed and progress.attempts <= 1:
        pool = "praise_major"
    elif passed:
        pool = "victory"
    else:
        pool = "fail_wrong_pattern"

    weakest = tuple(
        dict.fromkeys(outcome.problem.pattern for outcome in test.outcomes if not outcome.correct)
    )

    return FinalVerdict(
        passed=passed,
        score=test.score,
        total=test.total,
        required=test.required,
        master_line=speak(conn, master, pool, seed=seed, score=test.score, total=test.total),
        respect_delta=respect_delta,
        respect_total=respect_total,
        progress=progress,
        weakest=weakest,
    )
