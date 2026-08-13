"""Mode B — Pattern Recall, and the line between self-grading and honesty."""

from __future__ import annotations

import pytest

from dsaquest.content.loader import load_library
from dsaquest.domain.enums import GameMode, Rating
from dsaquest.game.modes.recall import (
    auto_match,
    build_round,
    canonical_answer,
    expected_phrases,
    grade,
    match_point,
)
from dsaquest.learning.rating import ReviewOutcome, rate


@pytest.fixture(scope="module")
def library():
    return load_library()


@pytest.fixture(scope="module")
def round_(library):
    return build_round(library["sliding-window"])


def _rate(outcome) -> Rating | None:
    return rate(
        ReviewOutcome(
            mode=GameMode.RECALL,
            correct=outcome.correct,
            self_grade=outcome.self_grade,
            essential_missed=outcome.essential_missed,
        )
    )


GOOD_ANSWER = (
    "Keep [l, r] as the longest window ending at r that satisfies the constraint. "
    "Shrink with a while loop until it is valid again, never an if. Each index "
    "enters once so it is amortised O(n). The constraint must be monotonic — "
    "'at most k' is the giveaway."
)


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------


def test_matching_ignores_case_punctuation_and_spacing(round_):
    point = next(p for p in round_.points if p.accepts)
    phrase = point.accepts[0]
    for variant in (phrase, phrase.upper(), f"...{phrase}!!!", f"  {phrase}  "):
        assert match_point(point, f"blah {variant} blah"), variant


def test_a_point_with_no_accepted_phrases_can_never_match(library):
    from dsaquest.domain.pattern import RubricPoint

    orphan = RubricPoint(key="x", prompt="something", essential=False, accepts=())
    assert not match_point(orphan, "anything at all")


def test_auto_match_covers_every_point(round_):
    matches = auto_match(round_, GOOD_ANSWER)
    assert set(matches) == {p.key for p in round_.points}


# --------------------------------------------------------------------------
# The honesty boundary
# --------------------------------------------------------------------------


def test_a_real_answer_is_credited_and_rated(round_):
    outcome = grade(round_, GOOD_ANSWER, auto_match(round_, GOOD_ANSWER))
    assert outcome.correct
    assert not outcome.essential_missed
    assert outcome.credited >= len(round_.essential)
    assert _rate(outcome) is Rating.GOOD


def test_ticking_every_box_cannot_fake_an_essential(round_):
    """The self-grade is trusted for nuance and overruled on essentials."""
    bluff = "it slides a window along"
    outcome = grade(
        round_,
        bluff,
        {p.key: True for p in round_.points},
        self_grade=Rating.EASY,
    )
    assert outcome.essential_missed
    assert not outcome.correct
    assert _rate(outcome) is Rating.AGAIN, "claiming a point does not make it so"


def test_a_tick_does_credit_a_non_essential_point(round_):
    """Be generous with yourself about the details — just not the invariant."""
    optional = next(p for p in round_.points if not p.essential)
    outcome = grade(round_, "nothing of substance", {optional.key: True})
    result = next(r for r in outcome.results if r.point.key == optional.key)
    assert result.credited
    assert result.overridden


def test_an_essential_tick_is_recorded_as_an_override(round_):
    essential = round_.essential[0]
    outcome = grade(round_, "nothing", {essential.key: True})
    overridden = {r.point.key for r in outcome.overrides}
    assert essential.key in overridden
    assert not next(r for r in outcome.results if r.point.key == essential.key).credited


def test_claiming_nothing_still_credits_objective_matches(round_):
    outcome = grade(round_, GOOD_ANSWER)
    assert outcome.credited > 0
    assert outcome.correct


def test_an_empty_answer_misses_everything(round_):
    outcome = grade(round_, "")
    assert outcome.credited == 0
    assert outcome.essential_missed
    assert _rate(outcome) is Rating.AGAIN


# --------------------------------------------------------------------------
# Feedback
# --------------------------------------------------------------------------


def test_a_missed_essential_reveals_the_wording_expected(round_):
    """A missed match should teach vocabulary, not be a silent mark against you."""
    outcome = grade(round_, "")
    for result in outcome.missed:
        if result.point.essential:
            assert expected_phrases(result.point), result.point.key


def test_the_canonical_answer_carries_the_whole_structure(library):
    for pattern in library:
        if not pattern.recall_rubric:
            continue
        rendered = canonical_answer(pattern)
        assert "SIGNALS" in rendered
        assert "INVARIANT" in rendered
        assert "COMPLEXITY" in rendered
        assert pattern.invariant.strip()[:40] in rendered


def test_every_pattern_can_be_recalled(library):
    """A pattern with no rubric cannot be trained in this mode at all."""
    for pattern in library:
        round_ = build_round(pattern)
        assert round_.points
        assert round_.essential, f"{pattern.id} has no essential point to hold you to"


def test_every_essential_point_is_matchable(library):
    """An essential with no accepted phrasing can never be satisfied.

    That would make the pattern permanently un-recallable, and the learner
    would have no way of knowing why.
    """
    for pattern in library:
        for point in pattern.essential_rubric:
            assert point.accepts, f"{pattern.id}/{point.key} is unsatisfiable"
