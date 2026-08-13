"""End-to-end coverage of the understanding check.

The check exists to catch one thing: correct code produced with no model of why
it is correct. So the assertions that matter are not "does the panel appear" but
these three:

* the answers are captured **before** the code is judged, and cannot be revised
  after — otherwise they are evidence about the verdict, not about the learner;
* a failed check **costs nothing** — no health, no failed phase — because a
  lexical matcher is not entitled to punish anyone;
* correct code with unsound reasoning is stored as *exactly that*, and is
  countable afterwards.

No C++ is compiled here. The implement phase runs its judge on a worker thread
and hands a bool back to the screen, so these tests hand the same bool in
directly, exactly as ``test_playthrough.py`` does.
"""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Input, Static

from dsaquest.context import build
from dsaquest.domain.boss import PhaseKind
from dsaquest.domain.enums import Dimension, GameMode, Rating
from dsaquest.game.understanding import (
    QUESTIONS,
    Answer,
    big_o_terms,
    grade_understanding,
)
from dsaquest.learning import apply_review
from dsaquest.storage import repositories as repo
from dsaquest.tui.app import DsaQuestApp
from dsaquest.tui.arena import ArenaScreen
from dsaquest.tui.understanding import UnderstandingPanel

SEED = 11
BEAST = "the-array-beast"


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


def _open_the_gate(context, boss) -> None:
    """Everything the beast asks for, so a fight can actually start."""
    for pattern in boss.patterns:
        for dimension in Dimension:
            for _ in range(12):
                apply_review(
                    context.conn,
                    repo.get_card(context.conn, pattern, dimension),
                    Rating.EASY,
                    scheduler=context.scheduler,
                    mode=GameMode.SOLVE,
                )
    repo.record_final_test(context.conn, boss.master_id, score=6, total=6, passed=True)


async def _walk_to_implement(pilot, screen) -> None:
    while screen.fight.current is not None and screen.fight.current.kind is not PhaseKind.IMPLEMENT:
        challenge = screen.fight.current
        screen.answer(challenge.hunter.correct_index if challenge.hunter else True)
        await pilot.pause()
        screen.action_advance()
        await pilot.pause()


def _fill(panel, key_idea: str, complexity: str, invariant: str) -> None:
    fields = {field.name: field for field in panel.query(Input)}
    fields["key_idea"].value = key_idea
    fields["complexity"].value = complexity
    fields["invariant"].value = invariant


async def _fight_to_the_check(context, pilot_holder, app):
    """Reach the implement phase and open the check. Returns the screen."""
    screen = app.screen
    await _walk_to_implement(pilot_holder, screen)
    await pilot_holder.press("ctrl+s")
    await pilot_holder.pause()
    return screen


# ------------------------------------------------------------------ engine


def test_the_three_questions_are_the_spec_s_three():
    assert [q.key for q in QUESTIONS] == ["key_idea", "complexity", "invariant"]
    assert QUESTIONS[0].prompt == "What is the key idea?"
    assert QUESTIONS[1].prompt == "What is the expected complexity?"
    assert QUESTIONS[2].prompt == "What invariant are you maintaining?"


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("O(n)", {"n"}),
        ("o(N)", {"n"}),
        ("O(n log n)", {"nlogn"}),
        ("O(n*logn)", {"nlogn"}),
        ("O(n lg n)", {"nlogn"}),
        ("O(n**2)", {"n^2"}),
        ("O(n^2)", {"n^2"}),
        ("linear", {"n"}),
        ("quadratic", {"n^2"}),
        ("constant", {"1"}),
    ],
)
def test_the_forms_people_write_a_complexity_in_all_compare_equal(written, expected):
    assert big_o_terms(written) == expected


def test_a_prose_complexity_yields_every_claim_it_contains():
    """Authored complexities are prose. Insisting on one canonical form is wrong."""
    prose = "O(n) after sorting, so O(n log n) if you must sort; O(n^2) for the other form"
    assert big_o_terms(prose) == {"n", "nlogn", "n^2"}


def test_a_right_answer_in_the_learner_s_own_words_is_accepted(context):
    verdict = grade_understanding(
        context.library["sliding-window"],
        Answer(
            key_idea="keep a window and shrink it while it is invalid",
            complexity="O(n)",
            invariant="the longest window ending at r that satisfies the constraint",
        ),
    )
    assert verdict.sound
    assert verdict.score == 1.0
    assert verdict.answered == 3


def test_memorised_code_has_nothing_to_say(context):
    verdict = grade_understanding(
        context.library["sliding-window"],
        Answer(key_idea="two loops", complexity="fast", invariant="it works"),
    )
    assert not verdict.sound
    assert verdict.score == 0.0
    # Answered but wrong is a different state from not answered at all.
    assert verdict.answered == 3
    assert not verdict.skipped


def test_a_blank_check_is_skipped_not_wrong(context):
    verdict = grade_understanding(
        context.library["sliding-window"], Answer(key_idea="", complexity="", invariant="")
    )
    assert verdict.skipped
    assert verdict.answered == 0
    assert not verdict.sound


def test_another_pattern_s_invariant_is_not_accepted(context):
    """The prose fallback must not credit a fluent description of the wrong thing."""
    misses = 0
    for pattern in context.library:
        for other in context.library:
            if other.id == pattern.id:
                continue
            verdict = grade_understanding(
                pattern,
                Answer(key_idea="x", complexity="O(n)", invariant=other.invariant),
            )
            if not verdict.part("invariant").sound:
                misses += 1
    assert misses > 0, "no cross-pattern invariant was rejected — the threshold is too loose"


# --------------------------------------------------------------------- UI


def test_the_check_is_asked_before_the_code_is_judged(context):
    async def journey():
        boss = context.bosses[BEAST]
        _open_the_gate(context, boss)
        app = DsaQuestApp(context)
        app.pending_screen = ArenaScreen(boss, seed=SEED)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = await _fight_to_the_check(context, pilot, app)
            # Reaching the implement phase means the earlier phases were
            # cleared, so the bars have already moved. What must not have moved
            # is anything *since* the check opened.
            boss_hp = screen.fight.boss_hp
            player_hp = screen.fight.player_hp

            panel = screen.query_one(UnderstandingPanel)
            shown = "\n".join(str(s.visual) for s in panel.query(Static))
            assert "BEFORE SUBMISSION" in shown
            for question in QUESTIONS:
                assert question.prompt in shown
            assert [f.name for f in panel.query(Input)] == [q.key for q in QUESTIONS]

            # Nothing has been judged yet: the phase is unresolved and no
            # verdict panel is showing.
            assert screen.fight.current is not None
            assert screen.fight.boss_hp == boss_hp
            assert screen.fight.player_hp == player_hp
            assert repo.understanding_history(context.conn) == ()

    _run(journey())


def test_a_sound_check_is_recorded_and_the_master_says_so(context):
    async def journey():
        boss = context.bosses[BEAST]
        _open_the_gate(context, boss)
        app = DsaQuestApp(context)
        app.pending_screen = ArenaScreen(boss, seed=SEED)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = await _fight_to_the_check(context, pilot, app)
            pattern = context.library[screen.fight.current.pattern_id]

            panel = screen.query_one(UnderstandingPanel)
            canonical = pattern.essential_rubric[0]
            _fill(
                panel,
                canonical.accepts[0] if canonical.accepts else pattern.tagline,
                pattern.complexity.time,
                pattern.invariant,
            )
            panel.commit()
            await pilot.pause()
            screen.answer(True)
            await pilot.pause()

            verdict = str(screen.query_one("#arena-verdict", Static).visual)
            assert "you were right" in verdict

        rows = repo.understanding_history(context.conn)
        assert len(rows) == 1
        assert rows[0].sound
        assert rows[0].code_correct is True
        assert not rows[0].hollow
        assert repo.hollow_solves(context.conn) == 0

    _run(journey())


def test_correct_code_with_no_reasoning_is_recorded_as_hollow(context):
    """The failure the check exists for."""

    async def journey():
        boss = context.bosses[BEAST]
        _open_the_gate(context, boss)
        app = DsaQuestApp(context)
        app.pending_screen = ArenaScreen(boss, seed=SEED)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = await _fight_to_the_check(context, pilot, app)

            _fill(screen.query_one(UnderstandingPanel), "two loops", "fast", "it works")
            screen.query_one(UnderstandingPanel).commit()
            await pilot.pause()
            screen.answer(True)
            await pilot.pause()

            verdict = str(screen.query_one("#arena-verdict", Static).visual)
            assert "memorised, not understood" in verdict

        rows = repo.understanding_history(context.conn)
        assert len(rows) == 1
        assert rows[0].code_correct is True
        assert not rows[0].sound
        assert rows[0].hollow
        assert repo.hollow_solves(context.conn) == 1
        assert repo.hollow_solves(context.conn, rows[0].pattern_id) == 1

    _run(journey())


def test_failing_the_check_costs_no_health_and_does_not_fail_the_phase(context):
    """A lexical matcher may report. It may not punish."""

    async def one_fight(reasoning: Answer) -> tuple[int, int]:
        boss = context.bosses[BEAST]
        app = DsaQuestApp(context)
        app.pending_screen = ArenaScreen(boss, seed=SEED)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = await _fight_to_the_check(context, pilot, app)
            panel = screen.query_one(UnderstandingPanel)
            _fill(panel, reasoning.key_idea, reasoning.complexity, reasoning.invariant)
            panel.commit()
            await pilot.pause()
            before = screen.fight.player_hp
            screen.answer(True)
            await pilot.pause()
            return before, screen.fight.player_hp

    async def journey():
        boss = context.bosses[BEAST]
        _open_the_gate(context, boss)
        pattern_hp = await one_fight(Answer("two loops", "fast", "it works"))
        assert pattern_hp[0] == pattern_hp[1], (
            "an unsound understanding check took health off the player"
        )

        # And the phase itself still cleared: the beast took its damage.
        app = DsaQuestApp(context)
        app.pending_screen = ArenaScreen(boss, seed=SEED)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = await _fight_to_the_check(context, pilot, app)
            hp_before = screen.fight.boss_hp
            panel = screen.query_one(UnderstandingPanel)
            _fill(panel, "nonsense", "nonsense", "nonsense")
            panel.commit()
            await pilot.pause()
            screen.answer(True)
            await pilot.pause()
            assert screen.fight.boss_hp < hp_before

    _run(journey())


def test_the_check_cannot_be_revised_once_the_verdict_is_in(context):
    """Editable answers would be evidence about the judge, not the learner."""

    async def journey():
        boss = context.bosses[BEAST]
        _open_the_gate(context, boss)
        app = DsaQuestApp(context)
        app.pending_screen = ArenaScreen(boss, seed=SEED)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = await _fight_to_the_check(context, pilot, app)
            panel = screen.query_one(UnderstandingPanel)
            _fill(panel, "two loops", "fast", "it works")
            panel.commit()
            await pilot.pause()
            screen.answer(True)
            await pilot.pause()

            # The panel is gone, and pressing submit again re-opens nothing.
            assert not screen.query(UnderstandingPanel)
            assert not screen.checking
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert not screen.query(UnderstandingPanel)

        rows = repo.understanding_history(context.conn)
        assert len(rows) == 1, "the check was stored more than once"
        assert not rows[0].sound

    _run(journey())


def test_the_check_is_recorded_when_the_code_fails_too(context):
    """Kept regardless of the code — the pair is the evidence."""

    async def journey():
        boss = context.bosses[BEAST]
        _open_the_gate(context, boss)
        app = DsaQuestApp(context)
        app.pending_screen = ArenaScreen(boss, seed=SEED)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = await _fight_to_the_check(context, pilot, app)
            pattern = context.library[screen.fight.current.pattern_id]
            panel = screen.query_one(UnderstandingPanel)
            canonical = pattern.essential_rubric[0]
            _fill(
                panel,
                canonical.accepts[0] if canonical.accepts else pattern.tagline,
                pattern.complexity.time,
                pattern.invariant,
            )
            panel.commit()
            await pilot.pause()
            screen.answer(False)
            await pilot.pause()

            verdict = str(screen.query_one("#arena-verdict", Static).visual)
            assert "reasoning was sound" in verdict

        rows = repo.understanding_history(context.conn)
        assert len(rows) == 1
        assert rows[0].sound
        assert rows[0].code_correct is False
        assert not rows[0].hollow, "sound reasoning is never hollow, whatever the code did"
        assert repo.hollow_solves(context.conn) == 0

    _run(journey())


def test_the_check_links_to_the_attempt_it_was_made_in(context):
    async def journey():
        boss = context.bosses[BEAST]
        _open_the_gate(context, boss)
        app = DsaQuestApp(context)
        app.pending_screen = ArenaScreen(boss, seed=SEED)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = await _fight_to_the_check(context, pilot, app)
            attempt_id = screen.fight.current.attempt_id
            panel = screen.query_one(UnderstandingPanel)
            _fill(panel, "x", "O(n)", "y")
            panel.commit()
            await pilot.pause()
            screen.answer(True)
            await pilot.pause()

        stored = context.conn.execute("SELECT attempt_id, mode FROM understanding_check").fetchone()
        assert stored["attempt_id"] == attempt_id
        assert stored["mode"] == GameMode.BOSS.value

    _run(journey())
