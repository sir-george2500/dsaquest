"""The learning engine: rating rubric, FSRS bridge, and the mastery blend."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dsaquest.domain.enums import Dimension, GameMode, Rating, Verdict
from dsaquest.learning import (
    GATE_CAP,
    GATE_MIN_IMPLEMENTATION_REPS,
    ReviewOutcome,
    apply_review,
    make_scheduler,
    pattern_mastery,
    rate,
    retrievability,
    weakest_patterns,
)
from dsaquest.learning.mastery import (
    IMPLEMENTATION_SLACK,
    MATURE_STABILITY_DAYS,
    available_patterns,
)
from dsaquest.learning.par import par_ms
from dsaquest.storage import repositories as repo
from dsaquest.storage.db import connect

T0 = datetime(2026, 8, 13, 9, 0, tzinfo=UTC)


@pytest.fixture
def conn():
    connection = connect(":memory:")
    repo.ensure_profile(connection)
    repo.ensure_cards(connection, ["sliding-window", "two-pointers", "prefix-sum"])
    yield connection
    connection.close()


@pytest.fixture
def scheduler():
    # Fuzzing makes intervals non-deterministic; tests need reproducibility.
    return make_scheduler(0.90, fuzz=False)


# --------------------------------------------------------------------------
# Rating rubric
# --------------------------------------------------------------------------


def test_a_judge_failure_never_produces_a_rating():
    """Our bug must not become the learner's lapse."""
    outcome = ReviewOutcome(mode=GameMode.SOLVE, correct=False, verdict=Verdict.INTERNAL_ERROR)
    assert rate(outcome) is None


@pytest.mark.parametrize(
    ("pace", "expected"),
    [(0.3, Rating.EASY), (1.0, Rating.GOOD), (2.0, Rating.HARD)],
)
def test_recognition_speed_decides_the_grade(pace, expected):
    """Being right on a four-way choice is cheap; being fast is the evidence."""
    par = par_ms(GameMode.HUNTER)
    outcome = ReviewOutcome(
        mode=GameMode.HUNTER, correct=True, duration_ms=int(par * pace), par_ms=par
    )
    assert rate(outcome) is expected


def test_recognition_second_guess_is_elimination_not_recall():
    outcome = ReviewOutcome(mode=GameMode.HUNTER, correct=True, tries=2)
    assert rate(outcome) is Rating.HARD


def test_wrong_recognition_is_again():
    assert rate(ReviewOutcome(mode=GameMode.HUNTER, correct=False)) is Rating.AGAIN


def test_self_grade_is_trusted_for_nuance(self_grade=Rating.EASY):
    outcome = ReviewOutcome(mode=GameMode.RECALL, correct=True, self_grade=self_grade)
    assert rate(outcome) is Rating.EASY


def test_a_missed_essential_point_overrules_a_generous_self_grade():
    """You may be generous about the details; not about the invariant."""
    outcome = ReviewOutcome(
        mode=GameMode.RECALL, correct=True, self_grade=Rating.EASY, essential_missed=True
    )
    assert rate(outcome) is Rating.AGAIN


def test_revealing_hints_caps_a_recall_review_at_good():
    outcome = ReviewOutcome(
        mode=GameMode.RECALL, correct=True, self_grade=Rating.EASY, hints_used=1
    )
    assert rate(outcome) is Rating.GOOD


def test_implementation_requires_an_accepted_verdict():
    outcome = ReviewOutcome(mode=GameMode.SOLVE, correct=True, verdict=Verdict.WRONG_ANSWER)
    assert rate(outcome) is Rating.AGAIN


def test_implementation_with_hints_is_hard_however_fast():
    par = par_ms(GameMode.SOLVE)
    outcome = ReviewOutcome(
        mode=GameMode.SOLVE,
        correct=True,
        verdict=Verdict.ACCEPTED,
        hints_used=1,
        duration_ms=int(par * 0.2),
        par_ms=par,
    )
    assert rate(outcome) is Rating.HARD


def test_clean_fast_implementation_is_easy():
    par = par_ms(GameMode.SOLVE)
    outcome = ReviewOutcome(
        mode=GameMode.SOLVE,
        correct=True,
        verdict=Verdict.ACCEPTED,
        duration_ms=int(par * 0.4),
        par_ms=par,
    )
    assert rate(outcome) is Rating.EASY


def test_missing_timing_data_falls_back_to_good_not_to_a_guess():
    outcome = ReviewOutcome(mode=GameMode.SOLVE, correct=True, verdict=Verdict.ACCEPTED)
    assert rate(outcome) is Rating.GOOD


# --------------------------------------------------------------------------
# FSRS bridge
# --------------------------------------------------------------------------


def _review(conn, scheduler, pattern, dimension, rating, at):
    card = repo.get_card(conn, pattern, dimension)
    return apply_review(conn, card, rating, scheduler=scheduler, mode=GameMode.SOLVE, now=at)


def test_a_new_card_has_no_retrievability(conn, scheduler):
    card = repo.get_card(conn, "sliding-window", Dimension.RECALL)
    assert card.is_new
    assert retrievability(card, scheduler=scheduler, now=T0) == 0.0


def test_review_advances_state_and_schedules_the_future(conn, scheduler):
    updated = _review(conn, scheduler, "sliding-window", Dimension.RECALL, Rating.GOOD, T0)
    assert updated.reps == 1
    assert updated.stability is not None and updated.stability > 0
    assert updated.last_review_at is not None
    assert datetime.fromisoformat(updated.due_at) > T0


def test_learning_step_is_persisted_so_cards_can_graduate(conn, scheduler):
    """The regression this guards against is invisible without it.

    If ``step`` is not round-tripped through the database, every reload
    restarts the learning phase: the card returns to step 0, reaches step 1
    again, and never reaches Review. Nothing errors — it just never graduates.
    """
    first = _review(conn, scheduler, "sliding-window", Dimension.RECALL, Rating.GOOD, T0)
    assert first.state == "learning" and first.step == 1

    reloaded = repo.get_card(conn, "sliding-window", Dimension.RECALL)
    assert reloaded.step == 1, "step was lost on the round trip"

    second = _review(
        conn,
        scheduler,
        "sliding-window",
        Dimension.RECALL,
        Rating.GOOD,
        datetime.fromisoformat(reloaded.due_at),
    )
    assert second.state == "review", "card failed to graduate out of learning"


def test_forgetting_learned_material_counts_as_a_lapse(conn, scheduler):
    at = T0
    for _ in range(2):
        card = _review(conn, scheduler, "sliding-window", Dimension.RECALL, Rating.GOOD, at)
        at = datetime.fromisoformat(card.due_at)
    assert card.state == "review" and card.lapses == 0

    lapsed = _review(conn, scheduler, "sliding-window", Dimension.RECALL, Rating.AGAIN, at)
    assert lapsed.lapses == 1
    assert lapsed.state == "relearning"


def test_failing_during_initial_learning_is_not_a_lapse(conn, scheduler):
    """Every new pattern would look fragile if first-contact failures counted."""
    card = _review(conn, scheduler, "sliding-window", Dimension.RECALL, Rating.AGAIN, T0)
    assert card.lapses == 0


def test_every_review_is_logged_for_the_optimiser(conn, scheduler):
    at = T0
    for rating in (Rating.GOOD, Rating.GOOD, Rating.HARD):
        card = _review(conn, scheduler, "sliding-window", Dimension.RECALL, rating, at)
        at = datetime.fromisoformat(card.due_at)

    rows = conn.execute("SELECT rating, elapsed_days FROM review_log ORDER BY id").fetchall()
    assert [r["rating"] for r in rows] == ["good", "good", "hard"]
    assert rows[0]["elapsed_days"] is None, "the first review has no elapsed time"
    assert rows[1]["elapsed_days"] > 0


def test_retrievability_decays_with_time(conn, scheduler):
    at = T0
    for _ in range(3):
        card = _review(conn, scheduler, "sliding-window", Dimension.RECALL, Rating.GOOD, at)
        at = datetime.fromisoformat(card.due_at)

    just_after = retrievability(card, scheduler=scheduler, now=at)
    much_later = retrievability(card, scheduler=scheduler, now=at + timedelta(days=365))
    assert just_after > much_later
    assert 0.0 <= much_later < just_after <= 1.0


def test_easy_schedules_further_out_than_hard(conn, scheduler):
    card = repo.get_card(conn, "two-pointers", Dimension.RECOGNITION)
    from dsaquest.learning import preview

    intervals = preview(card, scheduler=scheduler, now=T0)
    assert intervals[Rating.AGAIN] < intervals[Rating.GOOD] <= intervals[Rating.EASY]


# --------------------------------------------------------------------------
# Mastery
# --------------------------------------------------------------------------


def _drill(conn, scheduler, pattern, dimension, times, rating=Rating.GOOD, start=T0):
    at = start
    card = None
    for _ in range(times):
        card = _review(conn, scheduler, pattern, dimension, rating, at)
        at = datetime.fromisoformat(card.due_at)
    return card, at


def test_untouched_pattern_is_zero(conn, scheduler):
    mastery = pattern_mastery(conn, "prefix-sum", scheduler=scheduler, now=T0)
    assert mastery.overall == 0.0
    assert not mastery.started
    assert mastery.retention == 0.0


def test_recognition_alone_cannot_pass_the_gate(conn, scheduler):
    """Acing multiple choice is not mastery, and must not unlock anything."""
    _, at = _drill(conn, scheduler, "two-pointers", Dimension.RECOGNITION, 8)
    _drill(conn, scheduler, "two-pointers", Dimension.RECALL, 8, start=T0)

    mastery = pattern_mastery(conn, "two-pointers", scheduler=scheduler, now=at)
    assert mastery.gated
    assert mastery.overall <= GATE_CAP
    assert not mastery.unlocks_dependents


def test_the_gate_lifts_once_the_code_has_been_written(conn, scheduler):
    for dimension in Dimension:
        _, at = _drill(conn, scheduler, "two-pointers", dimension, 6)

    mastery = pattern_mastery(conn, "two-pointers", scheduler=scheduler, now=at)
    assert not mastery.gated
    assert mastery.implementation.reps >= GATE_MIN_IMPLEMENTATION_REPS
    assert mastery.overall > GATE_CAP


def test_repeated_implementation_failure_cannot_buy_its_way_past_the_gate(conn, scheduler):
    """The reps gate counts attempts, not successes — so it is not enough alone.

    A learner who aces recognition and recall but fails every implementation
    review still accumulates implementation reps, clearing the reps gate. Left
    unchecked, that unlocks dependent patterns for someone who cannot write a
    line of the pattern. Overall mastery is therefore also capped at
    implementation's own score plus a small slack.
    """
    at = {dimension: T0 for dimension in Dimension}
    for _ in range(6):
        for dimension in Dimension:
            rating = Rating.AGAIN if dimension is Dimension.IMPLEMENTATION else Rating.GOOD
            card = _review(conn, scheduler, "two-pointers", dimension, rating, at[dimension])
            at[dimension] = datetime.fromisoformat(card.due_at)

    mastery = pattern_mastery(conn, "two-pointers", scheduler=scheduler, now=min(at.values()))
    assert mastery.implementation.reps >= GATE_MIN_IMPLEMENTATION_REPS, "reps gate is cleared"
    assert mastery.recognition.score > 0.9, "recognition is genuinely strong"
    assert not mastery.unlocks_dependents, "must not unlock without being able to implement"
    assert mastery.overall <= mastery.implementation.score + IMPLEMENTATION_SLACK + 1e-9


def test_overall_never_outruns_implementation_by_more_than_the_slack(conn, scheduler):
    for dimension in (Dimension.RECOGNITION, Dimension.RECALL):
        _drill(conn, scheduler, "prefix-sum", dimension, 8)
    _, at = _drill(conn, scheduler, "prefix-sum", Dimension.IMPLEMENTATION, 1)

    mastery = pattern_mastery(conn, "prefix-sum", scheduler=scheduler, now=at)
    assert mastery.overall <= mastery.implementation.score + IMPLEMENTATION_SLACK + 1e-9


def test_retention_is_the_weakest_dimension_not_the_average(conn, scheduler):
    """A pattern you can name but not write is not 'partly retained'."""
    _drill(conn, scheduler, "two-pointers", Dimension.RECOGNITION, 5)
    _drill(conn, scheduler, "two-pointers", Dimension.RECALL, 5)
    card, at = _drill(conn, scheduler, "two-pointers", Dimension.IMPLEMENTATION, 1)

    far_future = at + timedelta(days=400)
    mastery = pattern_mastery(conn, "two-pointers", scheduler=scheduler, now=far_future)
    assert mastery.retention == min(d.retrievability for d in mastery.dimensions)


def test_an_untrained_dimension_makes_retention_zero(conn, scheduler):
    """Recognition alone is not retention of the pattern.

    Counting only trained dimensions flattered the learner: drilling
    recognition and nothing else reported 100% retention while two thirds of
    the pattern did not exist.
    """
    _drill(conn, scheduler, "two-pointers", Dimension.RECOGNITION, 5)
    mastery = pattern_mastery(conn, "two-pointers", scheduler=scheduler, now=T0)

    assert mastery.recognition.seen
    assert not mastery.implementation.seen
    assert mastery.retention == 0.0


def test_maturity_is_capped_so_ancient_cards_do_not_exceed_one(conn, scheduler):
    card, at = _drill(conn, scheduler, "two-pointers", Dimension.RECALL, 8)
    mastery = pattern_mastery(conn, "two-pointers", scheduler=scheduler, now=at)
    assert 0.0 <= mastery.recall.maturity <= 1.0
    if card.stability and card.stability > MATURE_STABILITY_DAYS:
        assert mastery.recall.maturity == 1.0


def test_overall_stays_within_bounds(conn, scheduler):
    for dimension in Dimension:
        _, at = _drill(conn, scheduler, "two-pointers", dimension, 10)
    mastery = pattern_mastery(conn, "two-pointers", scheduler=scheduler, now=at)
    assert 0.0 <= mastery.overall <= 1.0


def test_weakest_patterns_ignores_untouched_ones(conn, scheduler):
    """Unstarted patterns score 0 and would otherwise fill every slot."""
    _drill(conn, scheduler, "two-pointers", Dimension.RECOGNITION, 4)
    from dsaquest.content.loader import load_library
    from dsaquest.learning.mastery import all_mastery

    library = load_library()
    repo.ensure_cards(conn, [p.id for p in library])
    mastery = all_mastery(conn, library, scheduler=scheduler, now=T0)

    weakest = weakest_patterns(mastery, limit=3)
    assert [m.pattern_id for m in weakest] == ["two-pointers"]
    assert all(m.started for m in weakest)


def test_availability_follows_the_prerequisite_dag(conn, scheduler):
    from dsaquest.content.loader import load_library
    from dsaquest.learning.mastery import all_mastery

    library = load_library()
    repo.ensure_cards(conn, [p.id for p in library])

    mastery = all_mastery(conn, library, scheduler=scheduler, now=T0)
    available = available_patterns(library, mastery)
    # sliding-window needs two-pointers and hashing-frequency; nothing is mastered yet.
    assert "sliding-window" not in available
    # Root patterns have no prerequisites and are available from the start.
    assert "two-pointers" in available
    assert "binary-search" in available
    # binary-search-answer is gated behind binary-search.
    assert "binary-search-answer" not in available
