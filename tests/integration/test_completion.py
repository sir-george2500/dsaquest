"""Mode C end to end: real compilation, real execution, differential judging.

The central property: for every hole in every shipped template, putting the
template's own code back must be Accepted. If that fails, either the hole
markers are wrong or the sample inputs do not exercise the code — and both are
content bugs that would otherwise surface as the learner being told their
correct answer is wrong.
"""

from __future__ import annotations

import re

import pytest

from dsaquest.content.exercises import samples_for
from dsaquest.content.loader import load_library
from dsaquest.content.paths import read_template
from dsaquest.domain.enums import Verdict
from dsaquest.game.modes.complete import (
    TODO_MARKER,
    exercise_source,
    find_hole,
    judge_completion,
    parse_holes,
    reference_source,
)

pytestmark = pytest.mark.slow

LIBRARY = load_library()
TEMPLATES = sorted({p.template_file for p in LIBRARY})

#: A surviving marker, and nothing else. Asserting on the bare word "HOLE"
#: read the W of "WHOLE" as the start of one: euclidean-gcd.cpp explains that
#: "the SET of common divisors ... IS THE WHOLE METHOD", and two tests called
#: that a leaked marker. The markers are a comment and an arrow, so match them.
MARKER = re.compile(r"//\s*(?:>>>|<<<)\s*HOLE\b")


HOLE_IDS = [
    (template, hole.id) for template in TEMPLATES for hole in parse_holes(read_template(template))
]


def test_every_pattern_template_defines_holes():
    """A template with no holes cannot be played in Mode C."""
    for template in TEMPLATES:
        holes = parse_holes(read_template(template))
        assert len(holes) >= 2, f"{template} defines {len(holes)} holes, expected at least 2"


@pytest.mark.parametrize(("template", "hole_id"), HOLE_IDS, ids=lambda v: str(v))
def test_the_reference_answer_is_accepted(template: str, hole_id: str):
    source = read_template(template)
    hole = find_hole(source, hole_id)
    report = judge_completion(source, hole_id, hole.body, list(samples_for(template)))

    assert not report.reference_failed, report.report.message
    assert report.accepted, (
        f"{template}:{hole_id} rejected its own reference answer — "
        f"{report.report.verdict}: {report.report.first_failure}"
    )


@pytest.mark.parametrize(("template", "hole_id"), HOLE_IDS, ids=lambda v: str(v))
def test_an_empty_answer_is_not_accepted(template: str, hole_id: str):
    """Leaving the hole blank must fail — otherwise the hole is not load-bearing.

    This is the check that catches a hole placed around decorative code: if the
    program still produces identical output with the body deleted, the exercise
    is teaching nothing.
    """
    source = read_template(template)
    report = judge_completion(source, hole_id, "", list(samples_for(template)))

    assert not report.reference_failed
    assert not report.accepted, (
        f"{template}:{hole_id} accepts an empty answer — the hole is not load-bearing"
    )


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_exercise_view_hides_the_answer(template: str):
    """The answer must not be copyable from elsewhere on screen.

    Checked as a *contiguous block*, not line by line. These templates teach
    three variants of one technique on purpose, so individual lines recur
    legitimately — `++l;` appears in every windowing form there is. What would
    actually ruin the exercise is the whole body sitting somewhere visible.
    """
    source = read_template(template)
    for hole in parse_holes(source):
        exercise = exercise_source(source, hole.id)
        assert TODO_MARKER in exercise
        assert hole.prompt in exercise
        assert not MARKER.search(exercise), "marker syntax leaked into the learner's buffer"
        assert _normalise(hole.body) not in _normalise(exercise), (
            f"{template}:{hole.id} — its entire body is visible elsewhere in the exercise"
        )


@pytest.mark.parametrize("template", TEMPLATES)
def test_no_hole_is_a_near_duplicate_of_another(template: str):
    """Two holes with the same body would give each other away."""
    holes = parse_holes(read_template(template))
    bodies = [_normalise(h.body) for h in holes]
    assert len(set(bodies)) == len(bodies), f"{template} has holes with identical bodies"


@pytest.mark.parametrize("template", TEMPLATES)
def test_stripping_markers_leaves_a_clean_program(template: str):
    """The reference is the oracle, so it must be marker-free and intact."""
    source = read_template(template)
    reference = reference_source(source)
    assert not MARKER.search(reference), "a marker survived the strip"
    for hole in parse_holes(source):
        assert _normalise(hole.body) in _normalise(reference), (
            f"{template}:{hole.id} was lost when markers were stripped"
        )


def test_a_syntactically_broken_answer_is_a_compile_error():
    template = TEMPLATES[0]
    source = read_template(template)
    hole_id = parse_holes(source)[0].id
    report = judge_completion(source, hole_id, "this is not c++ ;;;", list(samples_for(template)))

    assert report.report.verdict is Verdict.COMPILE_ERROR
    assert not report.accepted
    assert "/box/" not in report.report.compile_log


def test_an_infinite_loop_in_an_answer_is_a_timeout():
    template = "sliding-window.cpp"
    source = read_template(template)
    hole_id = parse_holes(source)[0].id
    report = judge_completion(source, hole_id, "while (true) {}", list(samples_for(template)))

    assert report.report.verdict is Verdict.TIME_LIMIT
    assert not report.accepted
