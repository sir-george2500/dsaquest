"""Content invariants.

These are the checks that keep a pattern *teachable* rather than merely valid.
Pydantic guarantees the shape; this file guarantees the substance — every
pattern must carry at least one near-decisive signal, must say what rules it
out, and must be gradeable.
"""

from __future__ import annotations

import pytest

from dsaquest.content.loader import load_library
from dsaquest.domain.enums import MistakeCode

#: Patterns that must always be present. Deliberately a *subset* check, not an
#: equality one: the roster grows every time a master is authored, and a test
#: that has to be edited to add content is a test that will be edited without
#: being read.
REQUIRED_PATTERNS = {
    "hashing-frequency",
    "prefix-sum",
    "two-pointers",
    "sliding-window",
    "binary-search",
    "binary-search-answer",
    "bit-manipulation",
}


def _all_pattern_ids():
    return sorted(load_library().patterns)


@pytest.fixture(scope="module")
def library():
    return load_library()


def test_library_loads_and_cross_validates(library):
    """Strict load already checks refs, reciprocity, template files and cycles."""
    assert set(library.patterns) >= REQUIRED_PATTERNS


def test_patterns_are_arranged_into_worlds(library):
    """Worlds must be contiguous from 1 — a gap would render an empty region."""
    worlds = sorted(library.worlds)
    assert worlds == list(range(1, max(worlds) + 1)), worlds
    assert [p.id for p in library.worlds[2]] == ["binary-search", "binary-search-answer"]


@pytest.mark.parametrize("pattern_id", _all_pattern_ids())
def test_every_pattern_has_a_near_decisive_signal(library, pattern_id):
    """A pattern with no strength-3 cue cannot be recognised, only guessed."""
    assert library[pattern_id].strong_signals


@pytest.mark.parametrize("pattern_id", _all_pattern_ids())
def test_every_pattern_says_what_rules_it_out(library, pattern_id):
    """Recognition is half elimination, and that half is what learners skip."""
    assert library[pattern_id].anti_signals


@pytest.mark.parametrize("pattern_id", _all_pattern_ids())
def test_every_pattern_is_gradeable(library, pattern_id):
    """Mode B self-grading needs concrete checkpoints, at least two of them essential."""
    pattern = library[pattern_id]
    assert len(pattern.recall_rubric) >= 5
    assert len(pattern.essential_rubric) >= 2
    assert all(r.accepts for r in pattern.recall_rubric), "each rubric point needs match hints"


@pytest.mark.parametrize("pattern_id", _all_pattern_ids())
def test_every_pattern_documents_its_traps(library, pattern_id):
    """A trap without a symptom cannot be recognised from a failing test."""
    traps = library[pattern_id].traps
    assert len(traps) >= 3
    assert all(t.symptom for t in traps)


@pytest.mark.parametrize("pattern_id", _all_pattern_ids())
def test_every_pattern_states_an_invariant_and_complexity(library, pattern_id):
    pattern = library[pattern_id]
    assert len(pattern.invariant.split()) >= 8, "an invariant needs to be a real sentence"
    assert pattern.complexity.time.startswith("O(")
    assert pattern.complexity.space.startswith("O(")


def test_confusions_are_mutual_and_carry_a_discriminator(library):
    for pattern in library:
        for confusion in pattern.confusable_with:
            other = library[confusion.pattern_id]
            assert other.confusion_with(pattern.id) is not None, (
                f"{pattern.id} <-> {other.id} confusion is one-way"
            )
            assert len(confusion.tell.split()) >= 8, (
                f"{pattern.id} -> {other.id} tell is too short to be usable under pressure"
            )


def test_every_pattern_is_confusable_with_something(library):
    """A pattern with no confusions produces no distractors and no duels."""
    for pattern in library:
        assert pattern.confusable_with, f"{pattern.id} has no confusions"


def test_confusion_mistake_codes_point_the_right_way(library):
    """Direction convention: the code reads ``<chosen>_OVER_<actual>``.

    The code on sliding-window's confusion with prefix-sum describes picking
    *prefix sums* on a problem that was really a window — not the reverse.
    Getting this backwards silently inverts the analytics.
    """
    window = library["sliding-window"]
    confusion = window.confusion_with("prefix-sum")
    assert confusion is not None
    assert confusion.mistake_code is MistakeCode.PATTERN_PREFIX_OVER_WINDOW

    prefix = library["prefix-sum"]
    reciprocal = prefix.confusion_with("sliding-window")
    assert reciprocal is not None
    assert reciprocal.mistake_code is MistakeCode.PATTERN_WINDOW_OVER_PREFIX


def test_unrecognised_is_not_used_as_a_filler_for_pair_confusions(library):
    """PATTERN_UNRECOGNISED means "identified nothing", not "no code fitted".

    The ordered pair is already stored in attempt.chosen_pattern_id, so a
    confusion with no named narrative should simply omit the code.
    """
    for pattern in library:
        for confusion in pattern.confusable_with:
            assert confusion.mistake_code is not MistakeCode.PATTERN_UNRECOGNISED, (
                f"{pattern.id} -> {confusion.pattern_id} uses UNRECOGNISED as filler; omit instead"
            )


def test_prerequisites_only_point_backwards_through_the_campaign(library):
    """You can never be gated behind something you meet later."""
    position = {p.id: (p.world, p.order) for p in library}
    for pattern in library:
        for prereq in pattern.prerequisites:
            assert position[prereq] < position[pattern.id], (
                f"{pattern.id} requires {prereq}, which appears later in the campaign"
            )


def test_the_first_pattern_of_the_campaign_needs_no_prerequisites(library):
    assert library.ordered[0].prerequisites == ()


def test_dependents_are_discoverable(library):
    """The unlock DAG must be walkable in both directions."""
    assert "sliding-window" in library.dependents("two-pointers")
    assert "binary-search-answer" in library.dependents("binary-search")
