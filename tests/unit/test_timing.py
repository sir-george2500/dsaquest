"""Deadlines, phase instrumentation, and the time diagnosis."""

from __future__ import annotations

import pytest

from dsaquest.domain.enums import Difficulty, GameMode, Rating, Verdict
from dsaquest.learning.par import format_duration, par_ms, phase_targets
from dsaquest.learning.rating import ReviewOutcome, rate
from dsaquest.storage import repositories as repo
from dsaquest.storage.db import connect
from dsaquest.timing import (
    PERSONAL_CEILING,
    PERSONAL_FLOOR,
    Phase,
    PhaseTiming,
    PressureStage,
    Stopwatch,
    analyse,
    budget_for,
    personal_factor,
    stage_for_mastery,
)
from dsaquest.timing.analysis import timeout_report
from dsaquest.timing.limits import LIMIT_MULTIPLE, PERSONAL_MIN_SAMPLES


@pytest.fixture
def conn():
    connection = connect(":memory:")
    repo.ensure_profile(connection)
    yield connection
    connection.close()


class FakeClock:
    """An injectable clock, so tests do not race wall time."""

    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        return self.now

    def advance(self, ms: int) -> None:
        self.now += ms


# --------------------------------------------------------------------------
# Par
# --------------------------------------------------------------------------


def test_par_is_generous_enough_to_think():
    """A student must have time to read, understand and plan before typing."""
    assert par_ms(GameMode.SOLVE, Difficulty.EASY) >= 8 * 60_000
    assert par_ms(GameMode.SOLVE, Difficulty.MEDIUM) >= 15 * 60_000
    assert par_ms(GameMode.SOLVE, Difficulty.HARD) >= 30 * 60_000
    assert par_ms(GameMode.BOSS, Difficulty.BOSS) >= 45 * 60_000


def test_par_rises_with_difficulty():
    values = [par_ms(GameMode.SOLVE, d) for d in Difficulty]
    assert values == sorted(values)


def test_phase_targets_sum_to_par():
    targets = phase_targets(GameMode.SOLVE, Difficulty.MEDIUM)
    assert abs(sum(targets.values()) - par_ms(GameMode.SOLVE, Difficulty.MEDIUM)) < 10
    assert targets["implement"] > targets["recognise"]


@pytest.mark.parametrize(
    ("ms", "expected"), [(0, "0:00"), (31_000, "0:31"), (409_000, "6:49"), (-5, "0:00")]
)
def test_durations_format_as_minutes_and_seconds(ms, expected):
    assert format_duration(ms) == expected


# --------------------------------------------------------------------------
# Deadlines
# --------------------------------------------------------------------------


def test_calm_training_has_no_deadline_at_all():
    """You cannot learn a technique and race against it in the same breath."""
    budget = budget_for(None, GameMode.SOLVE, stage=PressureStage.CALM)
    assert not budget.has_deadline
    assert budget.limit_ms is None
    assert budget.remaining_ms(10**9) is None
    assert not budget.expired(10**9)


def test_the_deadline_is_at_least_double_par():
    """The limit is generous by construction, not by tuning."""
    for stage in (PressureStage.TIMED, PressureStage.RUTHLESS, PressureStage.TRIAL):
        budget = budget_for(None, GameMode.SOLVE, Difficulty.MEDIUM, stage=stage)
        assert budget.limit_ms >= budget.target_ms * LIMIT_MULTIPLE * 0.95


def test_pressure_never_shortens_the_clock_below_the_base():
    """Higher stages remove help; accelerating a clock punishes thinking."""
    base = budget_for(None, GameMode.SOLVE, stage=PressureStage.TIMED).limit_ms
    for stage in (PressureStage.RUTHLESS, PressureStage.TRIAL, PressureStage.BOSS):
        limit = budget_for(None, GameMode.SOLVE, stage=stage).limit_ms
        assert limit >= base * 0.85, f"{stage.name} squeezed the clock too far"


def test_higher_stages_remove_hints_instead(conn):
    assert PressureStage.CALM.hints_allowed is None
    assert PressureStage.RUTHLESS.hints_allowed == 3
    assert PressureStage.TRIAL.hints_allowed == 1
    assert PressureStage.BOSS.hints_allowed == 0


def test_only_trials_and_bosses_hide_the_pattern():
    """Hiding a pattern before the technique is taught trains frustration."""
    assert not PressureStage.CALM.hides_pattern
    assert not PressureStage.TIMED.hides_pattern
    assert not PressureStage.RUTHLESS.hides_pattern
    assert PressureStage.TRIAL.hides_pattern
    assert PressureStage.BOSS.hides_pattern


def test_pressure_arrives_while_still_improving():
    assert stage_for_mastery(0.0, started=False) is PressureStage.CALM
    assert stage_for_mastery(0.05, started=True) is PressureStage.CALM
    assert stage_for_mastery(0.25, started=True) is PressureStage.TIMED
    assert stage_for_mastery(0.50, started=True) is PressureStage.RUTHLESS
    assert stage_for_mastery(0.80, started=True) is PressureStage.TRIAL


def test_a_budget_tracks_what_is_left(conn):
    budget = budget_for(conn, GameMode.HUNTER, stage=PressureStage.TIMED)
    assert budget.remaining_ms(0) == budget.limit_ms
    assert budget.remaining_ms(budget.limit_ms + 5000) == 0
    assert budget.expired(budget.limit_ms)
    assert budget.fraction_used(budget.limit_ms // 2) == pytest.approx(0.5, abs=0.01)
    assert set(budget.bar(0)) == {"░"}


# --------------------------------------------------------------------------
# Learning the student's speed
# --------------------------------------------------------------------------


def _log_attempt(conn, ratio: float, mode=GameMode.SOLVE, difficulty=Difficulty.MEDIUM):
    par = par_ms(mode, difficulty)
    attempt_id = repo.start_attempt(
        conn,
        pattern_id="p",
        mode=mode,
        seed=1,
        difficulty=difficulty.value,
        par_ms=par,
    )
    repo.finish_attempt(conn, attempt_id, correct=True, duration_ms=int(par * ratio))


def test_history_is_ignored_until_there_is_enough_of_it(conn):
    """Two fast answers are noise, not a measurement."""
    for _ in range(PERSONAL_MIN_SAMPLES - 1):
        _log_attempt(conn, 0.4)
    factor, samples = personal_factor(conn, GameMode.SOLVE, Difficulty.MEDIUM)
    assert factor == 1.0
    assert samples < PERSONAL_MIN_SAMPLES


def test_a_fast_student_gets_a_tighter_clock(conn):
    for _ in range(8):
        _log_attempt(conn, 0.5)
    factor, _ = personal_factor(conn, GameMode.SOLVE, Difficulty.MEDIUM)
    assert factor < 1.0


def test_a_slow_student_gets_a_longer_clock(conn):
    for _ in range(8):
        _log_attempt(conn, 1.9)
    factor, _ = personal_factor(conn, GameMode.SOLVE, Difficulty.MEDIUM)
    assert factor > 1.0


def test_the_clamp_stops_the_system_punishing_improvement(conn):
    """Without a floor, getting faster would spiral into impossible limits."""
    for _ in range(10):
        _log_attempt(conn, 0.05)
    factor, _ = personal_factor(conn, GameMode.SOLVE, Difficulty.MEDIUM)
    assert factor == PERSONAL_FLOOR


def test_the_clamp_stops_the_clock_becoming_meaningless(conn):
    for _ in range(10):
        _log_attempt(conn, 12.0)
    factor, _ = personal_factor(conn, GameMode.SOLVE, Difficulty.MEDIUM)
    assert factor == PERSONAL_CEILING


def test_history_is_kept_separate_per_mode_and_difficulty(conn):
    for _ in range(8):
        _log_attempt(conn, 0.5, mode=GameMode.SOLVE, difficulty=Difficulty.EASY)
    fast, _ = personal_factor(conn, GameMode.SOLVE, Difficulty.EASY)
    untouched, samples = personal_factor(conn, GameMode.SOLVE, Difficulty.HARD)
    assert fast < 1.0
    assert untouched == 1.0 and samples == 0


# --------------------------------------------------------------------------
# Phase instrumentation
# --------------------------------------------------------------------------


def test_a_stopwatch_accumulates_per_phase():
    clock = FakeClock()
    watch = Stopwatch(clock=clock)
    watch.start(Phase.RECOGNISE)
    clock.advance(31_000)
    watch.enter(Phase.PLAN)
    clock.advance(58_000)
    watch.enter(Phase.IMPLEMENT)
    clock.advance(252_000)
    watch.stop()

    breakdown = watch.breakdown()
    assert breakdown[Phase.RECOGNISE] == 31_000
    assert breakdown[Phase.PLAN] == 58_000
    assert breakdown[Phase.IMPLEMENT] == 252_000
    assert watch.total_ms == 341_000


def test_returning_to_a_phase_adds_rather_than_restarts():
    """A student who replans after a failure has both stretches counted."""
    clock = FakeClock()
    watch = Stopwatch(clock=clock)
    watch.start(Phase.PLAN)
    clock.advance(10_000)
    watch.enter(Phase.IMPLEMENT)
    clock.advance(20_000)
    watch.enter(Phase.PLAN)
    clock.advance(5_000)
    watch.stop()

    assert watch.breakdown()[Phase.PLAN] == 15_000


def test_a_running_phase_is_included_in_the_breakdown():
    clock = FakeClock()
    watch = Stopwatch(clock=clock)
    watch.start(Phase.IMPLEMENT)
    clock.advance(7_000)
    assert watch.breakdown()[Phase.IMPLEMENT] == 7_000
    assert watch.running


def test_debugging_is_absent_unless_something_failed():
    """Its presence is the signal — a student who never failed never debugged."""
    clock = FakeClock()
    watch = Stopwatch(clock=clock)
    watch.start(Phase.RECOGNISE)
    clock.advance(1_000)
    watch.enter(Phase.IMPLEMENT)
    clock.advance(1_000)
    watch.stop()

    timing = PhaseTiming.from_stopwatch(watch)
    assert Phase.DEBUG not in timing.breakdown
    assert not timing.reached_debugging


def test_stopping_twice_does_not_double_count():
    clock = FakeClock()
    watch = Stopwatch(clock=clock)
    watch.start(Phase.PLAN)
    clock.advance(5_000)
    watch.stop()
    clock.advance(9_000)
    watch.stop()
    assert watch.breakdown()[Phase.PLAN] == 5_000


def test_an_unstarted_stopwatch_is_empty():
    watch = Stopwatch(clock=FakeClock())
    assert watch.breakdown() == {}
    assert watch.total_ms == 0
    assert not watch.running


# --------------------------------------------------------------------------
# The diagnosis
# --------------------------------------------------------------------------


def _timing(**phases) -> PhaseTiming:
    breakdown = {Phase(k): v for k, v in phases.items()}
    return PhaseTiming(breakdown=breakdown, total_ms=sum(breakdown.values()))


def test_being_on_target_names_no_bottleneck():
    targets = phase_targets(GameMode.SOLVE, Difficulty.MEDIUM)
    timing = _timing(
        recognise=targets["recognise"] // 2,
        plan=targets["plan"] // 2,
        implement=targets["implement"] // 2,
    )
    analysis = analyse(timing, GameMode.SOLVE, Difficulty.MEDIUM)
    assert analysis.bottleneck is None
    assert analysis.within_target


def test_the_bottleneck_is_ranked_by_time_lost_not_by_ratio():
    """A high ratio on a short phase must lose to a modest ratio on a long one.

    Recognition here is 3x over target and implementation only 1.5x, but
    implementation's target is far larger, so it sheds more minutes and is the
    thing actually worth fixing.
    """
    targets = phase_targets(GameMode.SOLVE, Difficulty.MEDIUM)
    recognise = targets["recognise"] * 3
    implement = int(targets["implement"] * 1.5)
    assert (recognise - targets["recognise"]) < (implement - targets["implement"])

    analysis = analyse(
        _timing(recognise=recognise, implement=implement),
        GameMode.SOLVE,
        Difficulty.MEDIUM,
    )
    assert analysis.bottleneck is Phase.IMPLEMENT


def test_slow_implementation_with_fast_recognition_says_so():
    targets = phase_targets(GameMode.SOLVE, Difficulty.MEDIUM)
    timing = _timing(
        recognise=targets["recognise"] // 3,
        plan=targets["plan"] // 2,
        implement=targets["implement"] * 2,
    )
    analysis = analyse(timing, GameMode.SOLVE, Difficulty.MEDIUM)
    assert analysis.bottleneck is Phase.IMPLEMENT
    assert "not recognition" in analysis.assessment
    assert analysis.advice


def test_heavy_debugging_is_diagnosed_as_coding_before_thinking():
    targets = phase_targets(GameMode.SOLVE, Difficulty.MEDIUM)
    timing = _timing(
        recognise=targets["recognise"],
        implement=targets["implement"],
        debug=targets["debug"] * 5,
    )
    analysis = analyse(timing, GameMode.SOLVE, Difficulty.MEDIUM)
    assert analysis.bottleneck is Phase.DEBUG
    assert "planning" in analysis.assessment


def test_the_report_renders_every_phase_entered():
    timing = _timing(recognise=31_000, plan=58_000, implement=252_000, debug=68_000)
    rendered = analyse(timing, GameMode.SOLVE, Difficulty.MEDIUM).render()
    for label in ("Pattern recognition", "Planning", "Implementation", "Debugging", "Total"):
        assert label in rendered


def test_a_timeout_report_names_where_the_time_went():
    timing = _timing(recognise=200_000, plan=40_000)
    report = timeout_report(240_000, 240_000, timing)
    assert "recognition" in report.lower()
    assert "fail" not in report.lower(), "a timeout is a speed result, not a failure verdict"


def test_a_timeout_with_nothing_committed_still_reports():
    assert timeout_report(60_000, 60_000, _timing())


# --------------------------------------------------------------------------
# Timeouts and the memory model
# --------------------------------------------------------------------------


def test_a_timeout_is_never_rated_as_forgotten():
    """The load-bearing rule: slow is not the same as forgotten.

    Rating a timeout AGAIN would tell the scheduler a memory was lost that is
    in fact intact, shortening every future interval for material the learner
    actually holds.
    """
    for mode in (GameMode.HUNTER, GameMode.SOLVE, GameMode.COMPLETE, GameMode.RECALL):
        rating = rate(ReviewOutcome(mode=mode, correct=False, timed_out=True))
        assert rating is Rating.HARD, mode


def test_a_wrong_answer_without_a_timeout_is_still_forgotten():
    assert rate(ReviewOutcome(mode=GameMode.HUNTER, correct=False)) is Rating.AGAIN


def test_a_judge_failure_outranks_a_timeout():
    """Our bug must not become the learner's lapse, timer or no timer."""
    outcome = ReviewOutcome(
        mode=GameMode.SOLVE, correct=False, timed_out=True, verdict=Verdict.INTERNAL_ERROR
    )
    assert rate(outcome) is None
