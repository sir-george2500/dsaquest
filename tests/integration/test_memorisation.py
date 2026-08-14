"""Memorisation detection against a real database, seeded through the real path.

Three learners, three databases, three verdicts that must not be confusable:

* one who aces every problem he has met before and falls apart on new ones;
* one who is genuinely fluent, and must never be accused;
* one with barely any history, whose numbers *look* like the first learner's
  and about whom nothing may be said at all.

Every attempt below goes through ``begin_exercise``/``complete_exercise``, so
these are real rows written by the code the game actually runs — FSRS cards,
XP, unlocks and all — not fixtures shaped to suit the query.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from dsaquest.analytics import memorisation as mem
from dsaquest.context import build
from dsaquest.domain.enums import GameMode
from dsaquest.game.session import ExerciseResult, begin_exercise, complete_exercise
from dsaquest.storage import repositories as repo

#: The three patterns with the widest fresh sample the shipped content can
#: offer. See the report note on content thinness.
PATTERNS = ("hashing-frequency", "prefix-sum", "two-pointers")

DECOY = "binary-search"


@dataclass(frozen=True, slots=True)
class Profile:
    """How one learner plays one pattern, independent of the bank's size.

    A learner's defining trait decides which way round to count.

    ``fresh_correct`` suits the learner **new problems defeat**: a memoriser
    gets one right whether the pattern has four problems or nine, so the count
    of successes is the constant and their accuracy properly falls as the
    sample widens.

    ``fresh_missed`` suits the **fluent** learner, whose trait is the opposite:
    they drop about one new problem regardless. Writing fluency as an absolute
    three successes made the fluent learner's fresh accuracy fall from 75% to
    60% the moment a fifth hashing problem was authored — and the detector then
    quite correctly refused to clear them, which is the detector working and
    the fixture lying.
    """

    repeat_wrong: int
    fresh_correct: int | None = None
    fresh_missed: int | None = None

    def correct_from(self, count: int) -> int:
        if self.fresh_missed is not None:
            return max(0, count - self.fresh_missed)
        return min(self.fresh_correct or 0, count)


#: Nothing new solved and nothing repeated missed is the caricature; the other
#: two are the ordinary shape of the same failure.
MEMORISER = {
    "hashing-frequency": Profile(repeat_wrong=0, fresh_correct=0),
    "prefix-sum": Profile(repeat_wrong=1, fresh_correct=1),
    "two-pointers": Profile(repeat_wrong=2, fresh_correct=1),
}
FLUENT = dict.fromkeys(PATTERNS, Profile(repeat_wrong=1, fresh_missed=1))


@dataclass(frozen=True, slots=True)
class Sample:
    """What a profile produces once the bank decides how many problems there are.

    Derived rather than written out. The totals used to be literals — 24 seen,
    12 fresh, 8 correct on hashing — which silently assumed four problems per
    pattern; authoring a fifth broke three tests that have nothing to do with
    content, and we are still deliberately writing more.
    """

    fresh_correct: int
    fresh_total: int
    seen_correct: int
    seen_total: int

    def __add__(self, other: Sample) -> Sample:
        return Sample(
            self.fresh_correct + other.fresh_correct,
            self.fresh_total + other.fresh_total,
            self.seen_correct + other.seen_correct,
            self.seen_total + other.seen_total,
        )


def sample_for(context, pattern: str, profiles: dict[str, Profile]) -> Sample:
    """The exact tally ``_run`` will produce for one pattern under ``profiles``."""
    profile = profiles[pattern]
    count = len(context.bank.for_pattern(pattern))
    seen_total = 2 * count
    return Sample(
        fresh_correct=profile.correct_from(count),
        fresh_total=count,
        seen_correct=seen_total - min(profile.repeat_wrong, seen_total),
        seen_total=seen_total,
    )


def whole_sample(context, profiles: dict[str, Profile]) -> Sample:
    total = Sample(0, 0, 0, 0)
    for pattern in profiles:
        total = total + sample_for(context, pattern, profiles)
    return total


def play_through(context, profiles: dict[str, Profile]) -> None:
    for pattern, profile in profiles.items():
        _run(
            context,
            pattern,
            fresh_correct=profile.correct_from(len(context.bank.for_pattern(pattern))),
            repeat_wrong=profile.repeat_wrong,
        )


def _play(context, problem, *, correct: bool, mode: GameMode = GameMode.HUNTER) -> int:
    attempt_id = begin_exercise(
        context.conn,
        pattern_id=problem.pattern,
        mode=mode,
        seed=1,
        difficulty=problem.difficulty,
        problem_id=problem.id,
    )
    complete_exercise(
        context.conn,
        attempt_id,
        ExerciseResult(
            correct=correct,
            duration_ms=90_000,
            chosen_pattern_id=problem.pattern if correct else DECOY,
        ),
        library=context.library,
        scheduler=context.scheduler,
        pattern_id=problem.pattern,
        mode=mode,
        difficulty=problem.difficulty,
    )
    return attempt_id


def _run(context, pattern: str, *, fresh_correct: int, repeat_wrong: int) -> None:
    """Meet every problem of a pattern once, then meet each of them twice more.

    ``fresh_correct`` of the first encounters land; ``repeat_wrong`` of the
    repeats do not. Everything else follows from the order, which is the only
    thing the detector reads.
    """
    problems = context.bank.for_pattern(pattern)
    for index, problem in enumerate(problems):
        _play(context, problem, correct=index < fresh_correct)

    wrong_left = repeat_wrong
    for problem in problems:
        for _ in range(2):
            _play(context, problem, correct=wrong_left <= 0)
            wrong_left -= 1


def _memoriser(context) -> None:
    """Remembers problems, not patterns.

    Hashing is the caricature — nothing new solved, nothing repeated missed.
    The other two are the ordinary shape of the same failure: a lucky first
    encounter, a slip on a repeat.
    """
    play_through(context, MEMORISER)


def _fluent(context) -> None:
    """Knows the technique. New problems cost a little, as they should."""
    play_through(context, FLUENT)


def _barely_started(context) -> None:
    """The memoriser's shape exactly, on two problems. Says nothing."""
    problems = context.bank.for_pattern("hashing-frequency")[:2]
    for problem in problems:
        _play(context, problem, correct=False)
    for problem in problems:
        for _ in range(2):
            _play(context, problem, correct=True)


@pytest.fixture
def learner(tmp_path):
    """Builds a real database per learner and seeds it through the real path."""
    contexts = []

    def make(name: str, seed):
        context = build(tmp_path / f"{name}.db", fuzz=False)
        seed(context)
        contexts.append(context)
        return context

    yield make

    for context in contexts:
        context.close()


@pytest.fixture
def memoriser(learner):
    return learner("memoriser", _memoriser)


@pytest.fixture
def fluent(learner):
    return learner("fluent", _fluent)


@pytest.fixture
def novice(learner):
    return learner("novice", _barely_started)


# --------------------------------------------------------------------------
# The three verdicts
# --------------------------------------------------------------------------


def test_the_memoriser_is_caught(memoriser):
    report = mem.assess_all(memoriser.conn)
    overall = report.overall

    expected = whole_sample(memoriser, MEMORISER)
    assert overall.seen_total == expected.seen_total
    assert overall.fresh_total == expected.fresh_total
    assert overall.seen_accuracy == pytest.approx(expected.seen_correct / expected.seen_total)
    assert overall.fresh_accuracy == pytest.approx(expected.fresh_correct / expected.fresh_total)
    assert overall.gap == pytest.approx(
        expected.seen_correct / expected.seen_total - expected.fresh_correct / expected.fresh_total
    )

    assert overall.finding is mem.Finding.MEMORISING
    assert overall.memorising
    assert overall.confident_gap is not None and overall.confident_gap > 0


def test_the_fluent_learner_is_never_accused(fluent):
    report = mem.assess_all(fluent.conn)
    overall = report.overall

    expected = whole_sample(fluent, FLUENT)
    assert overall.seen_total == expected.seen_total
    assert overall.fresh_total == expected.fresh_total
    assert overall.gap == pytest.approx(
        expected.seen_correct / expected.seen_total - expected.fresh_correct / expected.fresh_total
    )

    assert overall.finding is mem.Finding.PATTERN_HOLDS
    assert not overall.memorising
    assert not report.any_memorising
    assert report.memorised == ()

    for verdict in report.patterns:
        assert verdict.finding is mem.Finding.PATTERN_HOLDS, verdict.scope


def test_too_little_data_is_a_verdict_of_its_own(novice):
    """The numbers scream memorisation. Two of them is not evidence of anything."""
    verdict = mem.assess(novice.conn, "hashing-frequency")

    assert verdict.seen_total == 4
    assert verdict.fresh_total == 2
    assert verdict.gap == pytest.approx(1.0), "the gap is real and must still be shown"

    assert verdict.finding is mem.Finding.NOT_ENOUGH_EVIDENCE
    assert not verdict.decided
    assert not verdict.memorising
    assert "too few" in verdict.detail

    # Worth pinning down: two against four separates cleanly enough that the
    # interval test on its own would have called it. The hard floor on sample
    # size is the only thing keeping the master quiet here, which is exactly
    # the case it exists for.
    assert verdict.confident_gap is not None and verdict.confident_gap > 0
    assert not verdict.enough_attempts


def test_the_three_learners_are_told_three_different_things(memoriser, fluent, novice):
    findings = [
        mem.assess_all(memoriser.conn).overall.finding,
        mem.assess_all(fluent.conn).overall.finding,
        mem.assess_all(novice.conn).overall.finding,
    ]
    assert findings == [
        mem.Finding.MEMORISING,
        mem.Finding.PATTERN_HOLDS,
        mem.Finding.NOT_ENOUGH_EVIDENCE,
    ]
    assert len(set(findings)) == 3


# --------------------------------------------------------------------------
# Honesty about the sample
# --------------------------------------------------------------------------


def test_a_gap_the_sample_cannot_support_is_not_an_accusation(memoriser):
    """Four fresh problems only prove total separation, and prefix-sum is not that.

    1 of 4 new against 7 of 8 repeated is a 62-point gap and still inside what
    eight coin flips produce. The pattern the learner is genuinely worst on is
    the one where the master must keep quiet.
    """
    report = mem.assess_all(memoriser.conn)

    caricature = sample_for(memoriser, "hashing-frequency", MEMORISER)
    hashing = report["hashing-frequency"]
    assert (hashing.fresh_correct, hashing.seen_correct) == (
        caricature.fresh_correct,
        caricature.seen_correct,
    )
    assert hashing.finding is mem.Finding.MEMORISING

    prefix = report["prefix-sum"]
    assert prefix.gap is not None and prefix.gap > mem.MEMORISATION_GAP
    assert prefix.confident_gap is not None and prefix.confident_gap < 0
    assert prefix.finding is mem.Finding.NOT_ENOUGH_EVIDENCE
    assert "cannot support" in prefix.detail


def test_a_pattern_never_played_reports_no_evidence_rather_than_zero(fluent):
    verdict = mem.assess(fluent.conn, "binary-search")

    assert verdict.seen_total == 0
    assert verdict.fresh_total == 0
    assert verdict.gap is None, "0.0 would read as a clean bill of health"
    assert verdict.seen_accuracy is None
    assert verdict.finding is mem.Finding.NOT_ENOUGH_EVIDENCE


def test_the_called_patterns_lead_with_the_best_supported_case(memoriser):
    called = mem.assess_all(memoriser.conn).memorised
    assert [v.scope for v in called] == ["hashing-frequency"]
    gaps = [v.confident_gap or 0.0 for v in called]
    assert gaps == sorted(gaps, reverse=True)


# --------------------------------------------------------------------------
# What counts as an encounter
# --------------------------------------------------------------------------


def test_attempts_without_a_problem_cannot_be_fresh_or_seen(novice):
    """Recall drills name no problem, so there is nothing to have met before."""
    before = repo.problem_exposure(novice.conn)

    for _ in range(6):
        attempt_id = begin_exercise(
            novice.conn, pattern_id="hashing-frequency", mode=GameMode.RECALL, seed=7
        )
        complete_exercise(
            novice.conn,
            attempt_id,
            ExerciseResult(correct=True, duration_ms=30_000),
            library=novice.library,
            scheduler=novice.scheduler,
            pattern_id="hashing-frequency",
            mode=GameMode.RECALL,
        )

    assert repo.problem_exposure(novice.conn) == before


def test_an_abandoned_attempt_is_not_a_wrong_answer(novice):
    problem = novice.bank.for_pattern("hashing-frequency")[0]
    before = mem.assess(novice.conn, "hashing-frequency")

    begin_exercise(
        novice.conn,
        pattern_id=problem.pattern,
        mode=GameMode.HUNTER,
        seed=3,
        problem_id=problem.id,
    )  # opened, never finished

    assert mem.assess(novice.conn, "hashing-frequency") == before


def test_the_second_sitting_of_a_problem_is_the_one_that_counts_as_seen(novice):
    """Encounter order, not the clock: the first row for a problem is the fresh one."""
    problem = novice.bank.for_pattern("prefix-sum")[0]

    _play(novice, problem, correct=True)
    first = mem.assess(novice.conn, "prefix-sum")
    assert (first.fresh_total, first.seen_total) == (1, 0)

    _play(novice, problem, correct=True)
    _play(novice, problem, correct=True)
    second = mem.assess(novice.conn, "prefix-sum")
    assert (second.fresh_total, second.seen_total) == (1, 2)


def test_the_overall_verdict_is_the_arithmetic_of_its_parts(memoriser):
    report = mem.assess_all(memoriser.conn)

    assert report.overall.seen_total == sum(v.seen_total for v in report.patterns)
    assert report.overall.fresh_total == sum(v.fresh_total for v in report.patterns)
    assert report.overall.seen_correct == sum(v.seen_correct for v in report.patterns)
    assert report.overall.fresh_correct == sum(v.fresh_correct for v in report.patterns)
    assert report.overall.scope == mem.OVERALL
