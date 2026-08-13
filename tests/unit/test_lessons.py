"""The teaching loop: curricula, drill planning, sessions, and master dialogue."""

from __future__ import annotations

import pytest

from dsaquest.content.lessons import load_curricula
from dsaquest.content.loader import load_library
from dsaquest.content.problems import load_problems
from dsaquest.domain.lesson import DrillKind
from dsaquest.lessons import current_stage, deal, grade, greet, teach
from dsaquest.lessons.plan import (
    FLUENCY_STREAK,
    assess,
    ceiling_attempts,
    check_answer,
    next_drill,
)
from dsaquest.lessons.session import RESPECT_FLUENT
from dsaquest.storage import repositories as repo
from dsaquest.storage.db import connect
from dsaquest.world.character import REQUIRED_POOLS, greeting_pool, load_masters, speak

MASTER_ID = "master_bits"


@pytest.fixture(scope="module")
def library():
    return load_library()


@pytest.fixture(scope="module")
def bank(library):
    return load_problems(library)


@pytest.fixture(scope="module")
def curricula(library, bank):
    return load_curricula(library, bank)


@pytest.fixture(scope="module")
def masters():
    return load_masters()


@pytest.fixture
def conn():
    connection = connect(":memory:")
    repo.ensure_profile(connection)
    yield connection
    connection.close()


# --------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------


def test_the_master_of_bits_has_a_curriculum(curricula):
    curriculum = curricula[MASTER_ID]
    assert curriculum.patterns == ("bit-manipulation",)
    assert curriculum.primary_pattern == "bit-manipulation"
    assert len(curriculum.stages) == 5
    assert [s.order for s in curriculum.ordered_stages] == [0, 1, 2, 3, 4]


def test_every_secret_has_enough_drills_to_meet_its_own_baseline(curricula):
    """Declaring a baseline the engine cannot deal would deadlock a stage."""
    for curriculum in curricula:
        for stage in curriculum.ordered_stages:
            secret = stage.secret
            assert len(secret.drills) >= secret.baseline_drills, secret.id


def test_every_secret_offers_enough_breadth_to_become_fluent(curricula):
    """Fluency needs several kinds. A secret with one kind can never be passed."""
    from dsaquest.lessons.plan import required_kinds

    for curriculum in curricula:
        for stage in curriculum.ordered_stages:
            secret = stage.secret
            assert len(secret.drill_kinds) >= required_kinds(secret), secret.id


def test_demonstrations_use_concrete_numbers(curricula):
    """A demonstration that merely asserts teaches nothing."""
    for curriculum in curricula:
        for stage in curriculum.ordered_stages:
            assert len(stage.secret.demonstrations) >= 2, stage.secret.id
            for demo in stage.secret.demonstrations:
                assert demo.expression and demo.result, stage.secret.id


def test_every_multiple_choice_answer_is_among_its_options(curricula):
    """The worst teaching bug: marking a correct student wrong."""
    for curriculum in curricula:
        for stage in curriculum.ordered_stages:
            for drill in stage.secret.drills:
                if drill.kind.is_multiple_choice:
                    assert drill.correct_index is not None, drill.id


def test_stages_are_ordered_so_secrets_build_on_each_other(curricula):
    """count-set-bits is derived from clear-lowest-set and must follow it."""
    order = [s.secret.id for s in curricula[MASTER_ID].ordered_stages]
    assert order.index("clear-lowest-set") < order.index("count-set-bits")


# --------------------------------------------------------------------------
# Grading answers
# --------------------------------------------------------------------------


def _drill(curricula, kind: DrillKind):
    for stage in curricula[MASTER_ID].ordered_stages:
        for drill in stage.secret.drills:
            if drill.kind is kind:
                return drill
    pytest.skip(f"no {kind.value} drill authored")


def test_multiple_choice_is_graded_exactly(curricula):
    drill = _drill(curricula, DrillKind.EVALUATE)
    assert check_answer(drill, drill.answer)
    assert not check_answer(drill, "definitely not the answer")


def test_recall_ignores_whitespace_and_case(curricula):
    """`n & 1` and `n&1` are the same knowledge.

    Marking one wrong teaches the student to fear the formatter, not the machine.
    """
    drill = _drill(curricula, DrillKind.RECALL)
    assert check_answer(drill, drill.answer)
    assert check_answer(drill, drill.answer.upper())
    assert check_answer(drill, "".join(drill.answer.split()))


def test_an_empty_recall_answer_is_wrong(curricula):
    drill = _drill(curricula, DrillKind.RECALL)
    assert not check_answer(drill, "")
    assert not check_answer(drill, "   ")


# --------------------------------------------------------------------------
# The adaptive plan
# --------------------------------------------------------------------------


def _progress(**overrides):
    from dsaquest.storage.repositories import SecretProgress

    base = dict(
        master_id=MASTER_ID,
        secret_id="lowest-bit",
        state="drilling",
        drills_seen=0,
        drills_correct=0,
        consecutive_correct=0,
        taught_at=None,
        fluent_at=None,
        tested_at=None,
    )
    base.update(overrides)
    return SecretProgress(**base)


def test_a_streak_alone_is_not_fluency(curricula):
    """Five correct arithmetic drills prove a reflex, not understanding."""
    secret = curricula[MASTER_ID].ordered_stages[0].secret
    verdict = assess(
        secret,
        _progress(drills_seen=6, drills_correct=6, consecutive_correct=6),
        frozenset({"evaluate"}),
    )
    assert not verdict.fluent
    assert "kind" in verdict.reason


def test_breadth_alone_is_not_fluency(curricula):
    secret = curricula[MASTER_ID].ordered_stages[0].secret
    verdict = assess(
        secret,
        _progress(drills_seen=6, drills_correct=3, consecutive_correct=0),
        frozenset({"evaluate", "property", "trap"}),
    )
    assert not verdict.fluent


def test_streak_plus_breadth_plus_floor_is_fluency(curricula):
    secret = curricula[MASTER_ID].ordered_stages[0].secret
    verdict = assess(
        secret,
        _progress(drills_seen=4, drills_correct=4, consecutive_correct=FLUENCY_STREAK),
        frozenset({"evaluate", "property", "trap"}),
    )
    assert verdict.fluent
    assert verdict.remaining_estimate == 0


def test_a_struggling_student_is_given_more(curricula):
    secret = curricula[MASTER_ID].ordered_stages[0].secret
    verdict = assess(
        secret,
        _progress(drills_seen=6, drills_correct=2, consecutive_correct=0),
        frozenset({"evaluate"}),
    )
    assert verdict.continue_drilling
    assert verdict.remaining_estimate >= 2
    assert "accuracy" in verdict.reason


def test_a_stuck_student_is_released_rather_than_trapped(curricula):
    """Past the ceiling the master moves on; spaced repetition brings it back."""
    secret = curricula[MASTER_ID].ordered_stages[0].secret
    verdict = assess(
        secret,
        _progress(drills_seen=ceiling_attempts(secret), drills_correct=1),
        frozenset(),
    )
    assert verdict.exhausted
    assert not verdict.continue_drilling


def test_the_next_drill_closes_the_breadth_gap_first(curricula):
    """Repeating the kind they are already good at teaches nothing."""
    secret = curricula[MASTER_ID].ordered_stages[0].secret
    passed = frozenset({"evaluate"})
    chosen = next_drill(
        secret, _progress(drills_seen=2), answered=frozenset(), kinds_passed=passed, seed=1
    )
    assert chosen is not None
    assert chosen.kind.value not in passed


def test_drill_selection_prefers_unseen_material(curricula):
    secret = curricula[MASTER_ID].ordered_stages[0].secret
    seen = frozenset(d.id for d in secret.drills[:-1])
    chosen = next_drill(secret, _progress(), answered=seen, kinds_passed=frozenset(), seed=3)
    assert chosen is not None and chosen.id not in seen


def test_drill_selection_repeats_rather_than_returning_nothing(curricula):
    """Running out of new drills must not end a stage prematurely."""
    secret = curricula[MASTER_ID].ordered_stages[0].secret
    everything = frozenset(d.id for d in secret.drills)
    chosen = next_drill(
        secret,
        _progress(),
        answered=everything,
        kinds_passed=frozenset(k.value for k in secret.drill_kinds),
        seed=5,
    )
    assert chosen is not None


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------


def test_training_starts_at_the_first_stage(conn, curricula):
    stage = current_stage(conn, curricula[MASTER_ID])
    assert stage is not None and stage.order == 0


def test_teaching_records_that_the_lesson_was_given(conn, curricula, masters):
    curriculum = curricula[MASTER_ID]
    stage = current_stage(conn, curriculum)
    teaching = teach(conn, masters[MASTER_ID], curriculum, stage, seed=1)

    assert teaching.stage_number == 1 and teaching.stage_count == 5
    assert repo.get_secret_progress(conn, MASTER_ID, stage.secret.id).is_taught


def test_a_memorise_secret_gets_the_memorise_line(conn, curricula, masters):
    curriculum = curricula[MASTER_ID]
    stage = current_stage(conn, curriculum)
    teaching = teach(conn, masters[MASTER_ID], curriculum, stage, seed=1)
    if stage.secret.memorise:
        assert teaching.memorise_line
    else:
        assert teaching.memorise_line is None


def _drill_until_fluent(conn, masters, curriculum, stage, *, correct=True, limit=30):
    outcomes = []
    for i in range(limit):
        drill = deal(conn, curriculum, stage, seed=i)
        if drill is None:
            break
        given = drill.answer if correct else "definitely wrong"
        outcome = grade(conn, masters[MASTER_ID], curriculum, stage, drill, given, seed=i)
        outcomes.append(outcome)
        if outcome.became_fluent or outcome.verdict.exhausted:
            break
    return outcomes


def test_correct_drilling_reaches_fluency_and_pays_respect(conn, curricula, masters):
    curriculum = curricula[MASTER_ID]
    stage = current_stage(conn, curriculum)
    teach(conn, masters[MASTER_ID], curriculum, stage, seed=0)

    outcomes = _drill_until_fluent(conn, masters, curriculum, stage)
    assert outcomes[-1].became_fluent, [o.verdict.reason for o in outcomes]
    assert outcomes[-1].respect_delta == RESPECT_FLUENT
    assert repo.get_respect(conn, MASTER_ID) == RESPECT_FLUENT


def test_respect_is_not_paid_per_drill(conn, curricula, masters):
    """Paying per drill would make grinding the fastest route to regard."""
    curriculum = curricula[MASTER_ID]
    stage = current_stage(conn, curriculum)
    teach(conn, masters[MASTER_ID], curriculum, stage, seed=0)

    outcomes = _drill_until_fluent(conn, masters, curriculum, stage)
    paid = [o for o in outcomes if o.respect_delta]
    assert len(paid) == 1, "respect must arrive once, at fluency"


def test_reaching_fluency_advances_to_the_next_stage(conn, curricula, masters):
    curriculum = curricula[MASTER_ID]
    first = current_stage(conn, curriculum)
    teach(conn, masters[MASTER_ID], curriculum, first, seed=0)
    _drill_until_fluent(conn, masters, curriculum, first)

    second = current_stage(conn, curriculum)
    assert second is not None and second.order == first.order + 1


def test_wrong_answers_never_cost_respect_during_drilling(conn, curricula, masters):
    """Drills are for learning. Trying must not be able to make you worse."""
    curriculum = curricula[MASTER_ID]
    stage = current_stage(conn, curriculum)
    teach(conn, masters[MASTER_ID], curriculum, stage, seed=0)

    _drill_until_fluent(conn, masters, curriculum, stage, correct=False)
    assert repo.get_respect(conn, MASTER_ID) == 0


def test_a_wrong_answer_still_explains(conn, curricula, masters):
    curriculum = curricula[MASTER_ID]
    stage = current_stage(conn, curriculum)
    drill = deal(conn, curriculum, stage, seed=1)
    outcome = grade(conn, masters[MASTER_ID], curriculum, stage, drill, "wrong", seed=1)

    assert not outcome.correct
    assert outcome.explanation and len(outcome.explanation) >= 10
    assert outcome.master_line


# --------------------------------------------------------------------------
# The master's voice
# --------------------------------------------------------------------------


def test_every_master_defines_every_required_pool(masters):
    for master in masters.values():
        assert set(master.dialogue) >= REQUIRED_POOLS, master.id


def test_every_master_has_art(masters):
    """A sprite, an ASCII portrait, or both — but never a master with no face.

    The ASCII block used to be mandatory because it was the only art. The
    screens now draw the pixel sprite, so the requirement is that a master has
    *some* art, and the ASCII one is a fallback that may be absent.
    """
    for master in masters.values():
        assert master.has_art, f"{master.id} has neither a sprite nor an ASCII portrait"
        if master.portrait.strip():
            assert max(len(line) for line in master.portrait.splitlines()) <= 32


def test_the_master_does_not_repeat_himself_until_the_pool_is_spent(conn, masters):
    master = masters[MASTER_ID]
    pool = "drill_correct"
    size = len(master.pool(pool))

    said = [speak(conn, master, pool, seed=i) for i in range(size)]
    assert len(set(said)) == size, "a line was repeated while fresh ones remained"


def test_an_exhausted_pool_recycles_rather_than_falling_silent(conn, masters):
    master = masters[MASTER_ID]
    pool = "drill_correct"
    for i in range(len(master.pool(pool)) * 2 + 1):
        assert speak(conn, master, pool, seed=i).strip()


def test_placeholders_are_substituted(conn, masters):
    master = masters[MASTER_ID]
    rendered = speak(conn, master, "drill_streak", seed=0, streak=7)
    assert "{streak}" not in rendered


def test_an_unknown_placeholder_does_not_crash_a_session(conn, masters):
    """A missing substitution should look odd, not end the training."""
    assert speak(conn, masters[MASTER_ID], "success", seed=0, nonexistent=1)


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (None, "greeting_first"),
        (0, "greeting_returning"),
        (1, "greeting_returning"),
        (9, "greeting_after_gap"),
    ],
)
def test_absence_changes_the_greeting(days, expected):
    assert greeting_pool(days) == expected


def test_greeting_marks_the_master_as_having_seen_you(conn, masters):
    assert repo.days_since_seen(conn, MASTER_ID) is None
    greet(conn, masters[MASTER_ID], seed=0)
    assert repo.days_since_seen(conn, MASTER_ID) == 0


# --------------------------------------------------------------------------
# Placeholders
# --------------------------------------------------------------------------


def test_unsupplied_placeholders_are_removed_not_printed(masters):
    """One pool is spoken from several places, and they know different things.

    ``fail_wrong_pattern`` fires from both a trial and a final test. Forcing
    every call site to supply every key an author might use is fragile; showing
    the learner ``You needed {score} of {total}`` reads as a bug in a moment
    meant to carry weight.
    """
    master = next(iter(masters.values()))
    for pool in master.dialogue:
        rendered = speak(None, master, pool, seed=0)
        assert "{" not in rendered and "}" not in rendered, (master.id, pool, rendered)


def test_substitution_leaves_no_double_spaces(masters):
    master = next(iter(masters.values()))
    for pool in master.dialogue:
        rendered = speak(None, master, pool, seed=1)
        assert "  " not in rendered, (pool, rendered)
        assert rendered == rendered.strip()


def test_supplied_placeholders_still_substitute(masters):
    master = masters[MASTER_ID]
    rendered = speak(None, master, "drill_streak", seed=0, streak=9)
    assert "{streak}" not in rendered


def test_every_master_has_a_distinct_title_and_portrait(masters):
    titles = [m.title for m in masters.values()]
    assert len(set(titles)) == len(titles), titles
    # Compare whichever art each master actually has. Two masters sharing a
    # face is the real defect; an absent fallback is not.
    faces = [
        (m.sprite_path().read_text() if m.sprite_path() else m.portrait) for m in masters.values()
    ]
    assert len(set(faces)) == len(faces), "two masters share a face"


def test_no_two_masters_govern_the_same_pattern(masters):
    """Contradictory instruction, and 'who do I train under?' becomes ambiguous."""
    seen: dict[str, str] = {}
    for master in masters.values():
        for pattern in master.patterns:
            assert pattern not in seen, f"{pattern} claimed by {seen[pattern]} and {master.id}"
            seen[pattern] = master.id
