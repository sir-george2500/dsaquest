"""A master who is getting nowhere goes back a step.

The drill kinds are already a ladder — compute it, name what it reveals, spot
the trap, produce it from memory, apply it — and the ordinary planner walks
*up* it, always offering the hardest kind the student has not yet passed.

That is right until the student is stuck, at which point it is exactly wrong:
it keeps handing them the kind they are currently failing. A student who cannot
say what an idiom reveals is not helped by being asked to write it from memory.
They are helped by computing it once, on real numbers.

These tests drive the real session against a real database, because the whole
behaviour lives in the interaction between what the store remembers and what
the planner does with it.
"""

from __future__ import annotations

import pytest

from dsaquest.context import build
from dsaquest.domain.lesson import DrillKind
from dsaquest.lessons import current_stage, deal
from dsaquest.lessons.plan import (
    SIMPLIFY_AFTER,
    next_drill,
    opening_kind_order,
    simpler_than,
)
from dsaquest.storage import repositories as repo

ARRAYS = "master_arrays"
LADDER = opening_kind_order()


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _stage(context):
    stage = current_stage(context.conn, context.curricula[ARRAYS])
    assert stage is not None
    return stage


def _fail(context, stage, drill, times: int = 1) -> None:
    for _ in range(times):
        repo.record_drill(
            context.conn,
            master_id=ARRAYS,
            secret_id=stage.secret.id,
            drill_id=drill.id,
            kind=drill.kind.value,
            correct=False,
            given="nonsense",
        )
    context.conn.commit()


def _pass(context, stage, drill) -> None:
    repo.record_drill(
        context.conn,
        master_id=ARRAYS,
        secret_id=stage.secret.id,
        drill_id=drill.id,
        kind=drill.kind.value,
        correct=True,
        given=drill.answer,
    )
    context.conn.commit()


# ----------------------------------------------------------------- the ladder


def test_simpler_means_earlier_in_the_order_a_master_teaches_in():
    assert simpler_than(DrillKind.EVALUATE) == frozenset(), "nothing is simpler than computing it"
    assert DrillKind.EVALUATE in simpler_than(DrillKind.RECALL)
    assert DrillKind.RECALL not in simpler_than(DrillKind.EVALUATE)
    assert simpler_than(DrillKind.APPLY) == frozenset(LADDER[:-1]), "apply is the top of the ladder"


# --------------------------------------------------------------- the streak


def test_the_streak_is_what_is_happening_now_not_a_running_total(context):
    stage = _stage(context)
    drill = stage.secret.drills[0]

    assert repo.drill_failure_streak(context.conn, ARRAYS, stage.secret.id) == 0

    _fail(context, stage, drill, times=3)
    assert repo.drill_failure_streak(context.conn, ARRAYS, stage.secret.id) == 3

    # One right answer and the master stops treating them as stuck. A total
    # would keep a bad afternoon on the record and go on simplifying a lesson
    # the student has since got right.
    _pass(context, stage, drill)
    assert repo.drill_failure_streak(context.conn, ARRAYS, stage.secret.id) == 0


# ------------------------------------------------------- the master relents


def test_a_stuck_student_is_handed_something_simpler(context):
    """The substance of it: the next drill steps down the ladder, not up."""
    stage = _stage(context)
    kinds = {d.kind for d in stage.secret.drills}
    if len(kinds) < 2:
        pytest.skip("this secret teaches one kind of drill")

    hardest = max(kinds, key=LADDER.index)
    hard_drills = [d for d in stage.secret.drills if d.kind is hardest]
    _fail(context, stage, hard_drills[0], times=SIMPLIFY_AFTER)

    chosen = deal(context.conn, context.curricula[ARRAYS], stage, seed=1)
    assert chosen is not None
    assert LADDER.index(chosen.kind) < LADDER.index(hardest), (
        f"still pressing at {chosen.kind} after {SIMPLIFY_AFTER} wrong answers"
    )


def test_one_wrong_answer_is_not_an_emergency(context):
    """A master who retreats at the first slip teaches that being wrong is fatal."""
    stage = _stage(context)
    kinds = {d.kind for d in stage.secret.drills}
    if len(kinds) < 2:
        pytest.skip("this secret teaches one kind of drill")

    hardest = max(kinds, key=LADDER.index)
    _fail(context, stage, next(d for d in stage.secret.drills if d.kind is hardest))

    assert repo.drill_failure_streak(context.conn, ARRAYS, stage.secret.id) < SIMPLIFY_AFTER
    chosen = deal(context.conn, context.curricula[ARRAYS], stage, seed=1)
    assert chosen is not None


def test_with_nothing_simpler_left_the_master_carries_on(context):
    """Falling back is a preference, not a requirement — it must not deadlock."""
    stage = _stage(context)
    easiest = min({d.kind for d in stage.secret.drills}, key=LADDER.index)
    only_easy = [d for d in stage.secret.drills if d.kind is easiest]

    _fail(context, stage, only_easy[0], times=SIMPLIFY_AFTER + 2)

    chosen = deal(context.conn, context.curricula[ARRAYS], stage, seed=1)
    assert chosen is not None, "a stuck student on the bottom rung was given nothing at all"


def test_the_master_comes_back_up_the_ladder_once_you_recover(context):
    """Going back a step is a step, not a demotion.

    While the student is still failing, the easier kinds keep winning — that is
    the whole point, and it is why the hardest kind stays out of reach for as
    long as it does. What must not happen is that it stays out of reach *after*
    they get something right: the secret is only finishable by passing every
    kind, so a fallback that never lifted would make it unfinishable.
    """
    curriculum = context.curricula[ARRAYS]
    stage = _stage(context)
    kinds = {d.kind for d in stage.secret.drills}
    if len(kinds) < 2:
        pytest.skip("this secret teaches one kind of drill")
    hardest = max(kinds, key=LADDER.index)

    _fail(
        context,
        stage,
        next(d for d in stage.secret.drills if d.kind is hardest),
        times=SIMPLIFY_AFTER,
    )
    stuck = {deal(context.conn, curriculum, stage, seed=s).kind for s in range(40)}
    assert hardest not in stuck, "kept pressing the kind they were failing"

    # One right answer on the easier drill they were given.
    easier = next(d for d in stage.secret.drills if d.kind is not hardest)
    _pass(context, stage, easier)

    # Recovered, the planner is the planner again — not merely "less strict".
    # Asserted against the unmodified choice rather than against a particular
    # kind, because which kind comes next after recovery is the old planner's
    # business (it prefers unseen material) and not something this change may
    # quietly alter.
    answered = repo.drills_answered(context.conn, ARRAYS, stage.secret.id)
    kinds_passed = repo.drill_kinds_passed(context.conn, ARRAYS, stage.secret.id)
    assert repo.drill_failure_streak(context.conn, ARRAYS, stage.secret.id) == 0

    for seed in range(40):
        untouched = next_drill(
            stage.secret,
            repo.ensure_secret(context.conn, ARRAYS, stage.secret.id),
            answered=answered,
            kinds_passed=kinds_passed,
            seed=seed,
            failure_streak=0,
        )
        assert deal(context.conn, curriculum, stage, seed=seed) == untouched
