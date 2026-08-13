"""Warrior Strength — the seven dimensions and what can and cannot move them."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dsaquest.analytics import compute, rank_title
from dsaquest.analytics.strength import (
    ATTENDANCE_SHARE,
    CONSISTENT_DAYS,
    WEIGHTS,
)
from dsaquest.content.loader import load_library
from dsaquest.domain.enums import Dimension, GameMode, Rating
from dsaquest.learning import apply_review, make_scheduler
from dsaquest.storage import repositories as repo
from dsaquest.storage.db import connect

T0 = datetime(2026, 8, 13, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def library():
    return load_library()


@pytest.fixture
def conn(library):
    connection = connect(":memory:")
    repo.ensure_profile(connection)
    repo.ensure_cards(connection, [p.id for p in library])
    yield connection
    connection.close()


@pytest.fixture
def scheduler():
    return make_scheduler(0.90, fuzz=False)


def _strength(conn, library, scheduler, now=T0):
    return compute(conn, library, scheduler=scheduler, now=now)


def _drill(conn, scheduler, pattern, dimension, times, rating=Rating.GOOD):
    at = T0
    for _ in range(times):
        card = apply_review(
            conn,
            repo.get_card(conn, pattern, dimension),
            rating,
            scheduler=scheduler,
            mode=GameMode.SOLVE,
            now=at,
        )
        at = datetime.fromisoformat(card.due_at)


def _attempt(conn, *, pattern="two-pointers", correct, stage=None, mode=GameMode.HUNTER):
    attempt_id = repo.start_attempt(conn, pattern_id=pattern, mode=mode, seed=1)
    repo.finish_attempt(conn, attempt_id, correct=correct, duration_ms=1000)
    if stage is not None:
        repo.record_timing(conn, attempt_id, breakdown={}, pressure_stage=stage)
    return attempt_id


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------


def test_the_weights_are_a_distribution():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_understanding_counts_most_and_speed_least():
    """The weights are the product's opinion, stated numerically."""
    assert WEIGHTS["understanding"] == max(WEIGHTS.values())
    assert WEIGHTS["speed"] == min(WEIGHTS.values())


def test_a_fresh_warrior_has_nothing_to_report(conn, library, scheduler):
    report = _strength(conn, library, scheduler)
    assert not report.started
    assert report.score == 0
    # Consistency is the only dimension knowable with no training at all.
    assert not report["recognition"].known
    assert report["consistency"].known


def test_unknown_dimensions_are_skipped_rather_than_scored_zero(conn, library, scheduler):
    """A learner who has not met a mode is not bad at it.

    Counting the unmet ones as zero would make the score meaningless on day one
    and would punish the learner for the app's own pacing.
    """
    _drill(conn, scheduler, "two-pointers", Dimension.RECOGNITION, 6)
    report = _strength(conn, library, scheduler)

    assert report["recognition"].known
    assert not report["speed"].known
    assert report.score > 0, "a skipped dimension must not drag the score to zero"


# --------------------------------------------------------------------------
# Problem solving resists drilling
# --------------------------------------------------------------------------


def test_problem_solving_counts_only_unaided_work(conn, library, scheduler):
    """Naming the pattern tests fluency; counting it here would let drilling do it."""
    for _ in range(5):
        _attempt(conn, correct=True, stage=None)  # pattern was named
    assert not _strength(conn, library, scheduler)["problem_solving"].known

    _attempt(conn, correct=True, stage=4)  # a trial: pattern hidden
    _attempt(conn, correct=False, stage=4)
    assert _strength(conn, library, scheduler)["problem_solving"].value == pytest.approx(0.5)


def test_named_pattern_successes_cannot_inflate_problem_solving(conn, library, scheduler):
    _attempt(conn, correct=False, stage=4)
    before = _strength(conn, library, scheduler)["problem_solving"].value

    for _ in range(20):
        _attempt(conn, correct=True, stage=None)

    after = _strength(conn, library, scheduler)["problem_solving"].value
    assert after == before


# --------------------------------------------------------------------------
# Consistency
# --------------------------------------------------------------------------


def test_consistency_rewards_turning_up(conn, library, scheduler):
    _attempt(conn, correct=True)
    value = _strength(conn, library, scheduler)["consistency"].value
    assert value == pytest.approx(ATTENDANCE_SHARE / CONSISTENT_DAYS, abs=0.01)


def test_consistency_rewards_coming_back_after_a_failure(conn, library, scheduler):
    _attempt(conn, correct=True)
    before = _strength(conn, library, scheduler)["consistency"].value

    _attempt(conn, pattern="prefix-sum", correct=False)
    _attempt(conn, pattern="prefix-sum", correct=True)

    after = _strength(conn, library, scheduler)
    assert after["consistency"].value > before
    assert "comeback" in after["consistency"].detail


def test_succeeding_then_failing_is_not_a_comeback(conn, library, scheduler):
    _attempt(conn, pattern="prefix-sum", correct=True)
    _attempt(conn, pattern="prefix-sum", correct=False)
    assert repo.comebacks(conn) == 0


# --------------------------------------------------------------------------
# Retention
# --------------------------------------------------------------------------


def test_recognition_alone_does_not_count_as_retention(conn, library, scheduler):
    """The flaw this dimension had: 100% retention on a third of a pattern."""
    _drill(conn, scheduler, "two-pointers", Dimension.RECOGNITION, 6)
    report = _strength(conn, library, scheduler)

    assert report["recognition"].value > 0
    assert report["retention"].value == 0.0


def test_training_every_dimension_lifts_retention(conn, library, scheduler):
    for dimension in Dimension:
        _drill(conn, scheduler, "two-pointers", dimension, 5)
    assert _strength(conn, library, scheduler)["retention"].value > 0


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def test_the_weakest_dimension_is_the_one_to_act_on(conn, library, scheduler):
    _drill(conn, scheduler, "two-pointers", Dimension.RECOGNITION, 8)
    report = _strength(conn, library, scheduler)
    weakest = report.weakest
    assert weakest is not None
    assert weakest.value == min(d.value for d in report.dimensions if d.known)


def test_ranks_rise_with_the_score():
    assert rank_title(0) == "Novice"
    titles = [rank_title(s) for s in range(0, 101, 5)]
    assert titles[0] == "Novice"
    assert titles[-1] == "Elite Challenger"
    # Monotonic: a higher score never yields an earlier title.
    order = [
        "Novice",
        "Weak Warrior",
        "Apprentice",
        "Student of the Masters",
        "Pattern Hunter",
        "Algorithm Warrior",
        "Competitive Programmer",
        "Elite Challenger",
    ]
    indices = [order.index(t) for t in titles]
    assert indices == sorted(indices)


def test_the_score_stays_within_bounds(conn, library, scheduler):
    for pattern in ("two-pointers", "prefix-sum"):
        for dimension in Dimension:
            _drill(conn, scheduler, pattern, dimension, 10)
    for _ in range(30):
        _attempt(conn, correct=True, stage=4)

    report = _strength(conn, library, scheduler)
    assert 0 <= report.overall <= 1.0
    assert 0 <= report.score <= 100


def test_every_dimension_renders_a_bar(conn, library, scheduler):
    report = _strength(conn, library, scheduler)
    for dimension in report.dimensions:
        assert len(dimension.bar(20)) == 20
