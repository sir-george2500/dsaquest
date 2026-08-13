"""Mode D — Pattern Duel, played against the real content tree.

Every test here loads the shipped pattern library and problem bank rather than
a fixture, because the mode's whole claim is about *this* content: that the
pairs it poses are genuinely confusable, that the statements never give
themselves away, and that the discriminator quoted afterwards is the one the
pattern author wrote.
"""

from __future__ import annotations

import pytest

from dsaquest.content.loader import PatternLibrary, load_library
from dsaquest.content.problems import ProblemBank, load_problems
from dsaquest.domain.enums import GameMode
from dsaquest.game.modes import (
    Duel,
    DuelError,
    build_duel,
    build_duel_for,
    duel_pairs,
    judge_duel,
)
from dsaquest.storage import repositories as repo
from dsaquest.storage.db import connect

SEEDS = range(60)


@pytest.fixture(scope="module")
def library():
    return load_library()


@pytest.fixture(scope="module")
def bank(library):
    return load_problems(library)


@pytest.fixture
def conn():
    connection = connect(":memory:")
    repo.ensure_profile(connection)
    yield connection
    connection.close()


def _mutually_confusable(library: PatternLibrary, a: str, b: str) -> bool:
    return library[a].confusion_with(b) is not None and library[b].confusion_with(a) is not None


def _busiest_pattern(library: PatternLibrary, bank: ProblemBank) -> str:
    """The pattern with the most duellable partners — the best test subject."""
    partners = {
        pattern.id: [
            c.pattern_id
            for c in pattern.confusable_with
            if c.pattern_id in library and bank.for_pattern(c.pattern_id)
        ]
        for pattern in library
        if bank.for_pattern(pattern.id)
    }
    return max(partners, key=lambda pid: (len(partners[pid]), pid))


def _partners(library: PatternLibrary, bank: ProblemBank, pattern_id: str) -> list[str]:
    return sorted(
        c.pattern_id
        for c in library[pattern_id].confusable_with
        if c.pattern_id in library and bank.for_pattern(c.pattern_id)
    )


def _record_confusion(conn, *, pattern_id: str, chosen: str, times: int = 1) -> None:
    """Play out `times` Hunter rounds where the learner picked `chosen` instead."""
    for n in range(times):
        attempt = repo.start_attempt(conn, pattern_id=pattern_id, mode=GameMode.HUNTER, seed=n)
        repo.finish_attempt(conn, attempt, correct=False, chosen_pattern_id=chosen)


# --------------------------------------------------------------------------
# The pairing
# --------------------------------------------------------------------------


def test_the_content_can_actually_stage_duels(library, bank):
    """If no pair qualifies, the mode is unplayable and every later test is vacuous."""
    assert duel_pairs(library, bank), "the shipped content offers no duellable pair"


def test_every_offered_pair_is_mutual_and_has_statements_on_both_sides(library, bank):
    for a, b in duel_pairs(library, bank):
        assert _mutually_confusable(library, a, b), f"{a}/{b} is a one-sided confusion"
        assert bank.for_pattern(a) and bank.for_pattern(b), f"{a}/{b} has an empty side"


def test_a_duel_never_pairs_two_unrelated_patterns(library, bank):
    """Random pairing would make the answer obvious without understanding either."""
    for seed in SEEDS:
        duel = build_duel(library, bank, seed=seed)
        a, b = duel.pattern_ids
        assert a != b
        assert _mutually_confusable(library, a, b), f"seed {seed} paired unrelated {a}/{b}"


def test_pinning_one_side_keeps_it_in_every_duel(library, bank):
    subject = _busiest_pattern(library, bank)
    for seed in SEEDS:
        duel = build_duel(library, bank, seed=seed, pattern_a=subject)
        assert subject in duel.pattern_ids
        opponent = next(pid for pid in duel.pattern_ids if pid != subject)
        assert opponent in _partners(library, bank, subject)


# --------------------------------------------------------------------------
# What the player sees
# --------------------------------------------------------------------------


def test_both_statements_are_shown_and_neither_names_its_pattern(library, bank):
    for seed in SEEDS:
        duel = build_duel(library, bank, seed=seed)
        assert len(duel.problems) == 2
        assert duel.problems[0].id != duel.problems[1].id
        for problem in duel.problems:
            assert problem.statement.strip(), "a duel with a blank side cannot be played"
            assert not problem.names_pattern, f"{problem.id} gives itself away"


def test_the_two_answers_are_offered_by_name(library, bank):
    duel = build_duel(library, bank, seed=7)
    assert {o.pattern_id for o in duel.options} == set(duel.pattern_ids)
    for option in duel.options:
        assert option.name == library[option.pattern_id].name


def test_the_option_order_does_not_leak_the_answer(library, bank):
    """Options stay canonical while the statements move, so positional
    matching cannot win. If the options followed the statements, "first option
    goes with the first statement" would score 100%."""
    subject = _busiest_pattern(library, bank)
    naive_wins = 0
    played = 0
    for seed in SEEDS:
        duel = build_duel(library, bank, seed=seed, pattern_a=subject)
        assert duel.pair == tuple(sorted(duel.pair)), "options are not in canonical order"
        played += 1
        naive = {0: duel.options[0].pattern_id, 1: duel.options[1].pattern_id}
        if judge_duel(library, duel, naive).correct:
            naive_wins += 1
    assert 0 < naive_wins < played, f"positional matching scored {naive_wins}/{played}"


def test_the_labels_a_and_b_follow_the_presentation_order(library, bank):
    duel = build_duel(library, bank, seed=3)
    assert duel.labelled() == (("A", duel.problems[0]), ("B", duel.problems[1]))
    assert duel.position_of(duel.pattern_ids[1]) == 1
    assert duel.name_of(duel.pattern_ids[0]) == library[duel.pattern_ids[0]].name


# --------------------------------------------------------------------------
# Judging
# --------------------------------------------------------------------------


def test_getting_both_sides_right_is_the_only_way_to_win(library, bank):
    for seed in SEEDS:
        duel = build_duel(library, bank, seed=seed)
        feedback = judge_duel(library, duel, duel.correct_assignment)
        assert feedback.correct
        assert feedback.wrong_positions == ()
        assert not feedback.swapped
        assert not feedback.collapsed


def test_swapping_the_two_is_wrong_on_both_sides(library, bank):
    for seed in SEEDS:
        duel = build_duel(library, bank, seed=seed)
        actual = duel.pattern_ids
        feedback = judge_duel(library, duel, {0: actual[1], 1: actual[0]})
        assert not feedback.correct
        assert feedback.wrong_positions == (0, 1)
        assert feedback.swapped


def test_naming_the_same_pattern_twice_is_wrong(library, bank):
    duel = build_duel(library, bank, seed=11)
    for pattern_id in duel.pair:
        feedback = judge_duel(library, duel, {0: pattern_id, 1: pattern_id})
        assert not feedback.correct
        assert feedback.collapsed
        assert len(feedback.wrong_positions) == 1


def test_feedback_reports_which_side_was_wrong(library, bank):
    duel = build_duel(library, bank, seed=5)
    actual = duel.pattern_ids
    feedback = judge_duel(library, duel, {0: actual[1], 1: actual[1]})
    assert feedback.wrong_positions == (0,)
    assert feedback.assignment == (actual[1], actual[1])
    assert feedback.actual == actual


def test_feedback_explains_both_statements(library, bank):
    duel = build_duel(library, bank, seed=13)
    feedback = judge_duel(library, duel, duel.correct_assignment)
    assert feedback.whys == (duel.problems[0].why, duel.problems[1].why)
    assert feedback.why(0).strip() and feedback.why(1).strip()


def test_an_answer_for_only_one_side_is_rejected(library, bank):
    duel = build_duel(library, bank, seed=1)
    with pytest.raises(ValueError, match="positions"):
        judge_duel(library, duel, {0: duel.pattern_ids[0]})


def test_a_pattern_that_was_never_offered_is_rejected(library, bank):
    duel = build_duel(library, bank, seed=1)
    outsider = next(p.id for p in library if p.id not in duel.pair)
    with pytest.raises(ValueError, match="not among the duelling patterns"):
        judge_duel(library, duel, {0: outsider, 1: duel.pattern_ids[1]})


# --------------------------------------------------------------------------
# The discriminator comes from the library, never from the mode
# --------------------------------------------------------------------------


def test_every_duel_carries_the_authors_tell_in_both_directions(library, bank):
    for seed in SEEDS:
        duel = build_duel(library, bank, seed=seed)
        left, right = duel.pattern_ids
        assert duel.tell == library[left].confusion_with(right).tell
        assert duel.reverse_tell == library[right].confusion_with(left).tell
        assert duel.tell.strip() and duel.reverse_tell.strip()


def test_a_wrong_side_quotes_the_tell_for_that_exact_mistake(library, bank):
    """ "You said X, it was Y" must show the library's tell for picking X on a Y."""
    for seed in SEEDS:
        duel = build_duel(library, bank, seed=seed)
        left, right = duel.pattern_ids

        # Both called the right-hand pattern: position 0 is the mistake.
        feedback = judge_duel(library, duel, {0: right, 1: right})
        assert feedback.tell == library[left].confusion_with(right).tell == duel.tell
        assert feedback.has_tell

        # Both called the left-hand pattern: now position 1 is the mistake, and
        # the discriminator must be read the other way round.
        feedback = judge_duel(library, duel, {0: left, 1: left})
        assert feedback.tell == library[right].confusion_with(left).tell == duel.reverse_tell


def test_a_correct_duel_still_shows_the_discriminator(library, bank):
    duel = build_duel(library, bank, seed=21)
    feedback = judge_duel(library, duel, duel.correct_assignment)
    assert feedback.tell == duel.tell
    assert feedback.has_tell


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def _screen(duel: Duel) -> tuple:
    return (
        tuple(p.id for p in duel.problems),
        tuple(o.pattern_id for o in duel.options),
        duel.tell,
    )


def test_the_same_seed_reproduces_the_same_screen(library, bank):
    for seed in SEEDS:
        assert _screen(build_duel(library, bank, seed=seed)) == _screen(
            build_duel(library, bank, seed=seed)
        )


def test_different_seeds_move_the_statements(library, bank):
    subject = _busiest_pattern(library, bank)
    sides = {
        build_duel(library, bank, seed=seed, pattern_a=subject).position_of(subject)
        for seed in SEEDS
    }
    assert sides == {0, 1}, "the pinned pattern always appeared on the same side"


def test_different_seeds_choose_different_pairs(library, bank):
    pairs = {build_duel(library, bank, seed=seed).pair for seed in SEEDS}
    assert len(pairs) > 1, "every seed staged the same duel"


# --------------------------------------------------------------------------
# Adapting to the learner
# --------------------------------------------------------------------------


def test_history_pulls_the_duel_toward_a_confusion_the_learner_has_made(library, bank):
    subject = _busiest_pattern(library, bank)
    partners = _partners(library, bank, subject)
    assert len(partners) > 1, "need a pattern with a choice of opponents to test the bias"

    for target in partners:
        history = {target: 5}
        opponents = set()
        for seed in SEEDS:
            duel = build_duel(library, bank, seed=seed, pattern_a=subject, history=history)
            opponents.update(pid for pid in duel.pattern_ids if pid != subject)
        assert opponents == {target}, f"history for {target} was ignored: got {opponents}"


def test_without_history_every_partner_eventually_appears(library, bank):
    subject = _busiest_pattern(library, bank)
    opponents = {
        next(
            pid
            for pid in build_duel(library, bank, seed=seed, pattern_a=subject).pattern_ids
            if pid != subject
        )
        for seed in SEEDS
    }
    assert opponents == set(_partners(library, bank, subject))


def test_the_learners_recorded_mistakes_pick_the_opponent(conn, library, bank):
    """End to end: wrong answers in Mode A steer which duel Mode D poses."""
    subject = _busiest_pattern(library, bank)
    partners = _partners(library, bank, subject)
    target = partners[-1]
    _record_confusion(conn, pattern_id=subject, chosen=target, times=3)

    opponents = {
        next(
            pid
            for pid in build_duel_for(conn, library, bank, subject, seed=seed).pattern_ids
            if pid != subject
        )
        for seed in SEEDS
    }
    assert opponents == {target}


def test_a_clean_record_still_produces_a_duel(conn, library, bank):
    subject = _busiest_pattern(library, bank)
    duel = build_duel_for(conn, library, bank, subject, seed=2)
    assert subject in duel.pattern_ids
    assert judge_duel(library, duel, duel.correct_assignment).correct


# --------------------------------------------------------------------------
# Refusing to stage a degenerate duel
# --------------------------------------------------------------------------


def test_a_pattern_whose_partners_have_no_problems_raises(library, bank):
    """Rather than pairing it with something unrelated to fill the screen."""
    subject = _busiest_pattern(library, bank)
    lonely = ProblemBank(problems={p.id: p for p in bank if p.pattern == subject})

    assert duel_pairs(library, lonely) == ()
    with pytest.raises(DuelError, match="mutually-confusable partner"):
        build_duel(library, lonely, seed=0, pattern_a=subject)
    with pytest.raises(DuelError):
        build_duel(library, lonely, seed=0)


def test_a_pattern_with_no_partner_in_the_library_raises(library, bank):
    subject = _busiest_pattern(library, bank)
    alone = PatternLibrary(patterns={subject: library[subject]})

    assert duel_pairs(alone, bank) == ()
    with pytest.raises(DuelError, match="a duel needs a genuine confusion"):
        build_duel(alone, bank, seed=0, pattern_a=subject)


def test_a_one_sided_confusion_is_not_duelled(library, bank):
    """Reciprocity is what guarantees a discriminator exists in both directions."""
    a, b = duel_pairs(library, bank)[0]
    stripped = library[b].model_copy(
        update={
            "confusable_with": tuple(c for c in library[b].confusable_with if c.pattern_id != a)
        }
    )
    half = PatternLibrary(patterns={**library.patterns, b: stripped})

    assert all({a, b} != set(pair) for pair in duel_pairs(half, bank))


def test_an_unknown_pattern_is_reported_as_unknown(library, bank):
    with pytest.raises(KeyError, match="unknown pattern"):
        build_duel(library, bank, seed=0, pattern_a="no-such-pattern")
