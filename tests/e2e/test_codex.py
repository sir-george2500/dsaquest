"""The Codex, and the diagnosis that makes a master worth listening to.

Two things are tested here and they are not the same thing.

The **Codex** is optional reward: lore that opens because you trained, were
tested and felled a guardian, never because you walked past. The property that
matters is that it cannot be read early and cannot disagree with the road.

The **diagnosis** is the educational core. A master who says "you are weak" is
worthless. The engine already records three independently-scheduled dimensions
per pattern, so it can say *which* — and, just as importantly, refuse to say
anything when the evidence is too thin, because a confident wrong diagnosis in
an authoritative voice does more damage than silence.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from textual.widgets import Static

from dsaquest.codex import (
    FALLBACK,
    MIN_EVIDENCE,
    Depth,
    Weakness,
    depth_reached,
    diagnose,
    diagnosis_line,
    load_lore,
    read_student,
)
from dsaquest.context import build
from dsaquest.domain.enums import Difficulty, GameMode, Rating
from dsaquest.game.session import ExerciseResult, complete_exercise
from dsaquest.journey import boss_for, load_chapters
from dsaquest.storage import repositories as repo
from dsaquest.tui.app import DsaQuestApp, HomeScreen
from dsaquest.tui.codex import CodexScreen

ARRAYS = "master_arrays"


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------- the diagnosis


@dataclass
class _Dim:
    score: float
    seen: bool = True
    retrievability: float = 0.9


@dataclass
class _Mastery:
    pattern_id: str
    recognition: _Dim
    recall: _Dim
    implementation: _Dim
    retention: float = 0.9


def _reading(recognition, understanding, implementation, retention=0.9, attempts=20):
    return diagnose(
        _Mastery(
            "sliding-window",
            _Dim(recognition),
            _Dim(understanding),
            _Dim(implementation),
            retention,
        ),
        attempts=attempts,
    )


def test_it_names_the_dimension_that_is_behind():
    """Can write it, cannot spot it — the commonest and most discouraging shape."""
    assert _reading(0.30, 0.80, 0.85).weakness is Weakness.RECOGNITION
    assert _reading(0.85, 0.30, 0.80).weakness is Weakness.UNDERSTANDING
    assert _reading(0.85, 0.80, 0.30).weakness is Weakness.IMPLEMENTATION


def test_decay_is_read_before_skill():
    """A student whose recall has lapsed does not have a skill problem.

    Telling them to drill implementation when what they need is review would
    send them the wrong way with the master's authority behind it.
    """
    reading = _reading(0.80, 0.78, 0.75, retention=0.20)
    assert reading.weakness is Weakness.RETENTION


def test_it_refuses_to_guess_from_thin_evidence():
    """A confident wrong diagnosis is worse than silence."""
    reading = _reading(0.20, 0.90, 0.90, attempts=MIN_EVIDENCE - 1)
    assert reading.weakness is Weakness.NONE
    assert not reading.confident


def test_dimensions_close_together_are_not_a_weakness():
    """Picking one of three near-equal scores would be noise dressed as insight."""
    assert _reading(0.70, 0.74, 0.78).weakness is Weakness.NONE


def test_one_trained_dimension_says_nothing_about_the_others():
    reading = diagnose(
        _Mastery(
            "sliding-window",
            _Dim(0.9),
            _Dim(0.0, seen=False),
            _Dim(0.0, seen=False),
            0.9,
        ),
        attempts=30,
    )
    assert reading.weakness is Weakness.NONE


def test_the_gap_is_reported_with_the_verdict():
    reading = _reading(0.25, 0.85, 0.80)
    assert reading.confident
    assert reading.gap == pytest.approx(0.60, abs=0.01)
    assert reading.evidence == 20


# ----------------------------------------------------------- master's voice


def test_a_master_diagnoses_in_their_own_words():
    line = diagnosis_line(ARRAYS, "recognition")
    assert line
    assert "weak" not in line.lower() or "not" in line.lower(), "a bare insult is not a diagnosis"


def test_a_master_with_no_lore_still_tells_the_truth():
    """The diagnosis is the useful part; silence would waste it."""
    line = diagnosis_line("master_with_no_lore_written", "implementation")
    assert line
    assert "hands" in line


def test_every_authored_master_can_speak_to_every_weakness():
    for master_id, lore in load_lore().items():
        for weakness in ("recognition", "understanding", "implementation", "retention"):
            assert diagnosis_line(master_id, weakness), f"{master_id} silent on {weakness}"
            assert lore.diagnosis.get(weakness), (
                f"{master_id} falls back rather than speaking in its own voice about {weakness}"
            )


# ------------------------------------------- the master reading the student


def _drill(context, pattern_id: str, mode: GameMode, *, times: int, correct: bool) -> None:
    """Put real attempts through the real engine, not a fabricated mastery.

    Recall carries a self-grade because the recall screen collects one. Leaving
    it out is not neutral: recognition and implementation rate a fast correct
    answer EASY, recall defaults to GOOD, and eight of those grow far less
    stability — so a student drilled evenly on all three would be diagnosed as
    weak on understanding by an artefact of the test rather than by anything
    they did.
    """
    repo.ensure_cards(context.conn, pattern_id)
    for _ in range(times):
        attempt_id = repo.start_attempt(
            context.conn,
            pattern_id=pattern_id,
            mode=mode,
            seed=1,
            problem_id=None,
            difficulty=Difficulty.MEDIUM.value,
        )
        complete_exercise(
            context.conn,
            attempt_id,
            ExerciseResult(
                correct=correct,
                duration_ms=4000,
                self_grade=Rating.EASY if mode is GameMode.RECALL and correct else None,
            ),
            library=context.library,
            scheduler=context.scheduler,
            pattern_id=pattern_id,
            mode=mode,
            difficulty=Difficulty.MEDIUM,
        )
    context.conn.commit()


def test_a_master_says_nothing_before_they_have_seen_you_work(context):
    assert read_student(context, ARRAYS) is None


def test_a_master_names_the_gap_and_says_it_in_their_own_voice(context):
    """The student can write it and cannot spot it — the shape this game exists for."""
    pattern_id = context.curricula[ARRAYS].patterns[0]
    _drill(context, pattern_id, GameMode.COMPLETE, times=8, correct=True)
    _drill(context, pattern_id, GameMode.RECALL, times=6, correct=True)
    _drill(context, pattern_id, GameMode.HUNTER, times=8, correct=False)

    reading = read_student(context, ARRAYS)
    assert reading is not None
    assert reading.weakness is Weakness.RECOGNITION
    assert reading.diagnosis.pattern_id == pattern_id
    assert reading.line == diagnosis_line(ARRAYS, "recognition")
    assert reading.line not in FALLBACK.values(), "spoke in the plain voice, not their own"


def test_a_master_speaks_about_one_thing_only(context):
    """Two weak patterns, one verdict: the clearest, not a list."""
    patterns = context.curricula[ARRAYS].patterns[:2]
    if len(patterns) < 2:
        pytest.skip("this master teaches one pattern")

    for pattern_id in patterns:
        _drill(context, pattern_id, GameMode.COMPLETE, times=8, correct=True)
        _drill(context, pattern_id, GameMode.RECALL, times=6, correct=True)
    _drill(context, patterns[0], GameMode.HUNTER, times=8, correct=False)
    _drill(context, patterns[1], GameMode.HUNTER, times=4, correct=False)
    _drill(context, patterns[1], GameMode.HUNTER, times=4, correct=True)

    reading = read_student(context, ARRAYS)
    assert reading is not None
    assert reading.diagnosis.pattern_id == patterns[0], "did not pick the clearer gap"


def test_a_student_who_is_strong_everywhere_is_told_nothing(context):
    """Praise only when earned, and no invented fault to fill the silence."""
    pattern_id = context.curricula[ARRAYS].patterns[0]
    for mode in (GameMode.HUNTER, GameMode.RECALL, GameMode.COMPLETE):
        _drill(context, pattern_id, mode, times=8, correct=True)
    assert read_student(context, ARRAYS) is None


# ------------------------------------------------------------------- lore


def test_lore_is_earned_not_visited(context):
    lore = load_lore()[ARRAYS]
    assert depth_reached(context, ARRAYS) is Depth.MET

    early = lore.visible_entries(Depth.MET)
    assert len(early) < len(lore.entries), "everything was readable before anything was earned"
    assert lore.locked_entries(Depth.MET), "nothing was held back"


def test_each_step_of_the_road_opens_more(context):
    lore = load_lore()[ARRAYS]
    counts = [len(lore.visible_entries(d)) for d in Depth]
    assert counts == sorted(counts), "depth did not open monotonically"
    assert counts[0] >= 1, "a master you have met must have something to read"
    assert counts[-1] == len(lore.entries), "perfect must open everything"


def test_the_codex_agrees_with_the_road(context):
    """Depth is derived from the same records the journey reads."""
    curriculum = context.curricula[ARRAYS]
    for stage in curriculum.stages:
        repo.ensure_secret(context.conn, ARRAYS, stage.secret.id)
        repo.set_secret_state(context.conn, ARRAYS, stage.secret.id, "tested")
    context.conn.commit()
    assert depth_reached(context, ARRAYS) is Depth.TRAINED

    repo.record_final_test(context.conn, ARRAYS, score=6, total=6, passed=True)
    context.conn.commit()
    assert depth_reached(context, ARRAYS) is Depth.TESTED

    chapter = load_chapters().chapter_for(ARRAYS)
    boss = boss_for(context, chapter)
    repo.record_boss_fight(
        context.conn,
        boss.id,
        won=True,
        grade="normal",
        duration_ms=1000,
        hp_left=10,
        hints_used=0,
    )
    context.conn.commit()
    assert depth_reached(context, ARRAYS) is Depth.FELLED

    repo.record_boss_fight(
        context.conn,
        boss.id,
        won=True,
        grade="perfect",
        duration_ms=900,
        hp_left=100,
        hints_used=0,
    )
    context.conn.commit()
    assert depth_reached(context, ARRAYS) is Depth.PERFECT


def test_every_lore_file_names_a_master_that_exists(context):
    for master_id, lore in load_lore().items():
        assert master_id in context.masters, f"lore for unknown master {master_id}"
        assert lore.creed and lore.epithet, f"{master_id} has no creed or epithet"
        for relationship in lore.relationships:
            assert relationship.master in context.masters, (
                f"{master_id} speaks about unknown master {relationship.master}"
            )


# ----------------------------------------------------------------- screen


def test_the_codex_shows_what_is_earned_and_names_what_is_not(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = CodexScreen(ARRAYS)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()
            screen = app.screen

            def shown() -> str:
                return "\n".join(str(s.visual) for s in screen.query(Static))

            page = shown()
            lore = load_lore()[ARRAYS]
            assert lore.epithet in page
            assert lore.creed[:30] in page

            # Every chapter is named in the index, earned or not: a locked
            # chapter you can see is a reason to go back to the road. Long
            # titles are clipped to the column, so only the opening survives.
            locked = lore.locked_entries(Depth.MET)
            assert locked
            for entry in locked:
                assert entry.title[:14] in page
                assert entry.text[:40] not in page

            # Opening one says what it costs rather than showing its text, and
            # the full title is spelled out where there is room for it.
            deepest = max(locked, key=lambda e: e.depth)
            for _ in range(lore.entries.index(deepest)):
                await pilot.press("right")
            await pilot.pause()
            page = shown()
            assert deepest.title in page
            assert deepest.text[:40] not in page
            assert "Sealed" in page
            assert "guardian" in page or "final test" in page or "secrets" in page

    _run(journey())


def test_the_codex_page_carries_the_masters_verdict(context):
    """A story nobody acts on is decoration. The diagnosis has to be visible."""
    pattern_id = context.curricula[ARRAYS].patterns[0]
    _drill(context, pattern_id, GameMode.COMPLETE, times=8, correct=True)
    _drill(context, pattern_id, GameMode.RECALL, times=6, correct=True)
    _drill(context, pattern_id, GameMode.HUNTER, times=8, correct=False)
    reading = read_student(context, ARRAYS)
    assert reading is not None

    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = CodexScreen(ARRAYS)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()
            screen = app.screen
            verdict = screen.query_one("#codex-verdict", Static)
            assert verdict.display
            shown = str(verdict.visual)
            assert reading.line[:40] in shown
            assert pattern_id in shown

            # A master who has not watched you work says nothing, and says it
            # without leaving an empty panel behind.
            screen.action_move(1)
            await pilot.pause()
            assert not screen.query_one("#codex-verdict", Static).display

    _run(journey())


def test_the_home_screen_reaches_the_codex(context):
    async def journey():
        repo.set_flag(context.conn, "prologue_read")
        context.conn.commit()
        app = DsaQuestApp(context)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            await pilot.press("7")
            await pilot.pause()
            assert isinstance(app.screen, CodexScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

    _run(journey())


def test_moving_between_masters_changes_the_page(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = CodexScreen()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            screen = app.screen
            if len(screen.masters()) < 2:
                pytest.skip("only one master has lore so far")
            first = str(screen.query_one("#codex-name", Static).visual)
            await pilot.press("down")
            await pilot.pause()
            assert str(screen.query_one("#codex-name", Static).visual) != first

    _run(journey())


# ------------------------------------------------ the master says it out loud


def test_the_master_speaks_the_diagnosis_when_they_have_one(context):
    """The engine is only worth having if the person teaching you says it."""
    from dsaquest.tui.master import MasterScreen

    pattern_id = context.curricula[ARRAYS].patterns[0]
    _drill(context, pattern_id, GameMode.COMPLETE, times=8, correct=True)
    _drill(context, pattern_id, GameMode.RECALL, times=6, correct=True)
    _drill(context, pattern_id, GameMode.HUNTER, times=8, correct=False)
    reading = read_student(context, ARRAYS)
    assert reading is not None

    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = MasterScreen(context.masters[ARRAYS], context.curricula, seed=7)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()
            said = str(app.screen.query_one("#say", Static).visual)
            assert reading.line[:40] in said, "the master kept the diagnosis to themselves"

    _run(journey())


def test_a_master_with_nothing_to_say_does_not_invent_something(context):
    """Silence is the honest answer, and it is what makes the remark land."""
    from dsaquest.tui.master import MasterScreen

    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = MasterScreen(context.masters[ARRAYS], context.curricula, seed=7)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()
            said = str(app.screen.query_one("#say", Static).visual)
            for line in load_lore()[ARRAYS].diagnosis.get("recognition", ()):
                assert line[:40] not in said

    _run(journey())
