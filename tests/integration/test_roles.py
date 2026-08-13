"""The problem-role rule: nothing may serve two jobs.

The bank is always the real one, so ``for_pattern`` and the pattern of each
problem are real. Only the curricula are stood in for, because the cases worth
testing are ones no shipped curriculum currently expresses — a final test
reusing its own trial, and the same problem claimed by two masters. Building
those as full ``Curriculum`` models would mean authoring stages, secrets,
drills and demonstrations to exercise two tuples of ids.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dsaquest.content.roles import ProblemRole, check_roles, uses_by_problem
from dsaquest.context import build


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _curriculum(master_id: str, trials: list[list[str]], final: list[str]):
    return SimpleNamespace(
        master_id=master_id,
        stages=[SimpleNamespace(trial_problem_ids=tuple(ids)) for ids in trials],
        final_test_problem_ids=tuple(final),
    )


def _two_problems(bank, pattern_id: str) -> list[str]:
    ids = [p.id for p in bank.for_pattern(pattern_id)]
    assert len(ids) >= 2, f"{pattern_id} needs two problems for this test"
    return ids[:2]


@pytest.fixture
def bank(context):
    return context.bank


# ------------------------------------------------------------------ the rule


def test_a_final_test_reusing_its_own_trial_is_reported(context, bank):
    """The serious case: the gate measures memory of a problem, not the pattern."""
    first, second = _two_problems(bank, "sorting-by-key")
    curricula = [_curriculum("master_greed", [[first], [second]], [first])]

    report = check_roles(curricula, bank)

    assert not report.shortfalls, "this pattern has enough problems; reuse is a choice"
    assert len(report.reuses) == 1
    reuse = report.reuses[0]
    assert reuse.problem_id == first
    assert reuse.same_master
    assert report.serious == (reuse,)
    assert not report.ok
    assert {use.role for use in reuse.uses} == {ProblemRole.RECOGNITION, ProblemRole.MASTERY}


def test_two_masters_claiming_one_problem_is_reported_less_gravely(context, bank):
    """Real, but not the same defect: the learner may never have met the other master."""
    first, _ = _two_problems(bank, "sorting-by-key")
    curricula = [
        _curriculum("master_greed", [[first]], []),
        _curriculum("master_arrays", [], [first]),
    ]

    report = check_roles(curricula, bank)

    assert len(report.reuses) == 1
    assert not report.reuses[0].same_master
    assert report.serious == ()
    assert not report.ok


def test_clean_curricula_pass(context, bank):
    first, second = _two_problems(bank, "sorting-by-key")
    report = check_roles([_curriculum("master_greed", [[first]], [second])], bank)
    assert report.ok
    assert report.reuses == ()
    assert report.shortfalls == ()


def test_a_shortfall_says_how_many_problems_are_missing(context, bank):
    """The number an author needs, not a symptom they cannot act on."""
    ids = [p.id for p in bank.for_pattern("exchange-argument")]
    # Demand one more job than there are problems, however they are assigned.
    curricula = [_curriculum("master_greed", [[i] for i in ids], [ids[0]])]

    report = check_roles(curricula, bank)

    assert len(report.shortfalls) == 1
    shortfall = report.shortfalls[0]
    assert shortfall.pattern_id == "exchange-argument"
    assert shortfall.available == len(ids)
    assert shortfall.needed == len(ids) + 1
    assert shortfall.missing == 1
    assert "write 1 more" in str(shortfall)


def test_a_shortfall_suppresses_the_reuse_it_causes(context, bank):
    """One defect must be reported once, at its cause.

    Where a pattern has too few problems, the reuse *is* the shortfall showing
    up downstream. Reporting both would send an author to reassign ids in a
    loop that cannot close.
    """
    ids = [p.id for p in bank.for_pattern("exchange-argument")]
    curricula = [_curriculum("master_greed", [[i] for i in ids], [ids[0]])]

    report = check_roles(curricula, bank)

    assert report.shortfalls, "the pattern is genuinely too thin"
    assert report.reuses == (), "the reuse is the shortfall, and was reported once"
    assert any("write 1 more" in line for line in report.lines())


def test_uses_are_attributed_to_the_right_master_and_role(context, bank):
    first, second = _two_problems(bank, "sorting-by-key")
    curricula = [_curriculum("master_greed", [[first]], [second])]

    uses = uses_by_problem(curricula)

    assert len(uses[first]) == 1
    assert uses[first][0].master_id == "master_greed"
    assert uses[first][0].role is ProblemRole.RECOGNITION
    assert uses[second][0].role is ProblemRole.MASTERY
    assert str(uses[second][0]) == "final test (master_greed)"


# ------------------------------------------------------- the shipped content


def test_the_shipped_content_has_no_fixable_reuse(context):
    """Every collision today traces to a pattern with too few problems."""
    report = check_roles(context.curricula, context.bank)
    assert report.reuses == (), (
        "a curriculum reuses a problem that could have been assigned elsewhere: "
        + "; ".join(str(r) for r in report.reuses)
    )


def test_the_shipped_content_reports_what_it_would_take(context):
    """The rule is only useful if it names the work.

    This is expected to fail today — nothing is held out at all — so it asserts
    the report is honest about it rather than asserting the content is clean.
    """
    report = check_roles(context.curricula, context.bank)
    assert report.shortfalls, "if this passes, the content caught up: enforce --strict"
    assert not report.ok
    missing = sum(s.missing for s in report.shortfalls)
    assert missing > 0
    for shortfall in report.shortfalls:
        assert shortfall.needed > shortfall.available
        assert f"write {shortfall.missing} more" in str(shortfall)


def test_every_reserved_problem_actually_exists(context):
    """A trial or final test pointing at nothing would fail silently at runtime."""
    report = check_roles(context.curricula, context.bank)
    known = {p.id for p in context.bank}
    assert report.reserved <= known
    assert report.reserved | report.unreserved == known
