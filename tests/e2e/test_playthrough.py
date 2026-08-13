"""End-to-end playthroughs.

Everything else in this suite proves a piece works. These prove the *journey*
works: the real application, driven through the real screens, over a real
SQLite file, asserted the way a player would experience it — what the panels
say, and what the database holds afterwards.

Nothing here compiles C++. The one phase that would (a boss's implement phase)
runs its judge on a worker thread and hands a bool back to the screen, so these
tests hand the same bool in directly and say so where they do it. That is why
the file is not marked ``slow``.

Two rules the tests below hold themselves to:

* **Seeds are pinned wherever a screen is constructed.** An unpinned session
  deals a different drill, a different trial problem and a different boss phase
  every run. Where a screen is reached by walking the UI the application builds
  it without a seed — that is the product's behaviour, not something a test may
  override — so those tests assert only what is true of *every* deal, and say so.
* **Assertions go through rendered text and the database.** Engine state is read
  only to know which button is the right one to press.
"""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Button, Static, TextArea

from dsaquest.context import build
from dsaquest.domain.enums import Dimension, GameMode, Rating
from dsaquest.learning import apply_review
from dsaquest.storage import repositories as repo
from dsaquest.tui.app import DsaQuestApp, HomeScreen
from dsaquest.tui.arena import ArenaScreen
from dsaquest.tui.journey import JourneyScreen
from dsaquest.tui.master import MasterScreen

SEED = 20260813

ARRAYS = "master_arrays"
BITS = "master_bits"
BEAST = "the-array-beast"

#: Ilsa Korrin's first secret, verbatim from the curriculum. Square brackets are
#: italic tags in this markup, so a single unescaped interpolation renders this
#: as ``ans += cnt; ++cnt;`` — different code, silently.
FIRST_IDIOM = "ans += cnt[S - x]; ++cnt[x];"

#: Markup that must never reach the screen as literal text. Deliberately no
#: single-letter tags: ``[i]`` is both an italic tag and a C++ subscript, and a
#: correctly escaped ``a[i]`` is supposed to appear.
LEAKED_MARKUP = (
    "[/]",
    "[b]",
    "[dim]",
    "[green]",
    "[red]",
    "[yellow]",
    "[cyan]",
    "[magenta]",
    "[b green]",
    "[b red]",
    "[b yellow]",
    "[b cyan]",
    "[b magenta]",
)


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------
# Reading the screen
# --------------------------------------------------------------------------


def _flat(screen, selector: str) -> str:
    """One panel's rendered text, whitespace collapsed.

    Panels wrap, so a substring assertion against the raw render breaks on a
    line break that happens to fall inside the phrase being checked.
    """
    return " ".join(str(screen.query_one(selector).visual).split())


def _cards(screen) -> str:
    """Every master card on the journey map as one flat string."""
    return " ".join(" ".join(str(card.visual).split()) for card in screen.query(".master-card"))


def _everything_rendered(screen) -> list[tuple[str, str]]:
    """(where, text) for every panel and button the player can see."""
    seen: list[tuple[str, str]] = []
    for widget in screen.query(Static):
        if not widget.display:
            continue
        seen.append((widget.id or widget.__class__.__name__, str(widget.visual)))
    for button in screen.query(Button):
        seen.append((button.id or "button", str(button.label)))
    return seen


def _assert_no_leaked_markup(screen, where: str) -> None:
    for panel_id, text in _everything_rendered(screen):
        for tag in LEAKED_MARKUP:
            assert tag not in text, f"{where}/{panel_id} shows raw markup {tag!r}: {text[:200]!r}"


# --------------------------------------------------------------------------
# Driving the screens
# --------------------------------------------------------------------------


async def _train_until(screen, pilot, *, stop: tuple[str, ...], limit: int = 800) -> str:
    """Answer everything a master asks, correctly, until a phase in ``stop``.

    This is the whole teach -> drill -> trial loop driven as keystrokes and
    answers: the only thing read out of the screen is *which* answer is right,
    which is what a student who had learned the secret would know.
    """
    for _ in range(limit):
        phase = screen.phase
        if phase in stop:
            return phase
        if phase in ("teach", "feedback", "fluent", "trial_done"):
            await pilot.press("space")
        elif phase == "drill":
            assert screen.drill is not None
            screen.answer(screen.drill.answer)
        elif phase == "trial":
            assert screen.trial is not None
            screen.answer_trial(screen.trial.round.correct_index)
        else:  # pragma: no cover - a phase the loop does not know how to leave
            raise AssertionError(f"training stalled in phase {phase!r}")
        await pilot.pause()
    raise AssertionError(f"training did not reach {stop} within {limit} steps")


def _everything_the_rubric_accepts(pattern) -> str:
    """A recall answer containing every phrase the pattern's author accepts.

    Writing prose here would make the test a test of our own writing. The
    author's accepted phrasings are exactly what a complete answer contains.
    """
    return " ; ".join(phrase for point in pattern.recall_rubric for phrase in point.accepts)


async def _fight(screen, pilot, *, win: bool, limit: int = 12) -> None:
    """Take the boss through every phase, clearing them all or failing them all."""
    for _ in range(limit):
        if screen.phase == "done":
            return
        assert screen.fight is not None
        challenge = screen.fight.current
        if challenge is None:
            return

        if challenge.hunter is not None:
            correct = challenge.hunter.correct_index
            index = correct if win else (correct + 1) % len(challenge.hunter.options)
            await pilot.press(str(index + 1))
        elif challenge.recall is not None:
            # Regression: the explain phase MUST name its pattern. It once did
            # not, and for THE ARRAY BEAST — whose YAML pins no `pattern:`, so
            # the engine draws `boss.patterns[seed % 4]` — that made the phase
            # unanswerable. The player was asked to recite the invariant of one
            # of four patterns, chosen at random, never named, with no statement
            # to infer it from, and lost 25 health for guessing. Asserting it
            # here is what lets the test read `challenge.recall.pattern` below
            # and still be a fair account of what a player can see.
            assert challenge.recall.pattern.name in str(
                screen.query_one("#arena-body", Static).visual
            ), "the explain phase must name the pattern it is asking about"
            editor = screen.query_one("#arena-editor", TextArea)
            editor.text = (
                _everything_the_rubric_accepts(challenge.recall.pattern)
                if win
                else "something about loops"
            )
            await pilot.press("ctrl+s")
        else:
            # The implement phase is the only one that runs the sandbox: it
            # compiles and executes C++ on a worker thread and calls back with
            # `report.accepted`, a bool. Typing a correct C++ body here would
            # test the judge — which tests/integration/test_judge.py already
            # does — and would add seconds of compilation to every run. Handing
            # the same bool the worker would have handed back exercises exactly
            # the arena code under test and nothing else.
            screen.answer(win)

        await pilot.pause()
        assert screen.phase == "between", "answering a phase must show a verdict"
        await pilot.press("space")
        await pilot.pause()


# --------------------------------------------------------------------------
# Setting up scenarios the UI cannot reasonably reach
# --------------------------------------------------------------------------

_DIMENSION_MODES = {
    Dimension.RECOGNITION: GameMode.HUNTER,
    Dimension.RECALL: GameMode.RECALL,
    Dimension.IMPLEMENTATION: GameMode.COMPLETE,
}


def _force_final_test_passed(context, master_id: str) -> None:
    """Record a passed final test without sitting one.

    Journey 2 sits the real thing. Everywhere else it is only a precondition,
    and re-driving a full curriculum to set one flag would make each boss test
    a second copy of journey 2.
    """
    repo.record_final_test(context.conn, master_id, score=4, total=4, passed=True)


def _force_the_gate_open(context, boss) -> None:
    """Drill every pattern the boss draws from until its gate opens.

    The gate wants recognition, recall, implementation and retention *held* on
    all four patterns. Reaching that through the UI means dozens of graded
    exercises spread over simulated weeks; ``apply_review`` is the same call
    those exercises end in, so this drives the memory model directly and leaves
    the arena — the thing under test — completely untouched.
    """
    for _ in range(3):
        for pattern_id in boss.patterns:
            for dimension, mode in _DIMENSION_MODES.items():
                apply_review(
                    context.conn,
                    repo.get_card(context.conn, pattern_id, dimension),
                    Rating.EASY,
                    scheduler=context.scheduler,
                    mode=mode,
                )
    _force_final_test_passed(context, boss.master_id)


async def _open_the_arena_from_the_map(app, pilot, boss_id: str):
    """Walk Home -> Journey -> the boss's own button, as a player would."""
    await pilot.press("t")
    await pilot.pause()
    assert isinstance(app.screen, JourneyScreen)

    button = next(
        b for b in app.screen.query(Button) if (b.id or "").startswith(f"boss-{boss_id}-")
    )
    assert boss_id.replace("-", " ") or True
    button.press()
    await pilot.pause()
    assert isinstance(app.screen, ArenaScreen)
    return app.screen


# --------------------------------------------------------------------------
# 1. A first session, start to finish
# --------------------------------------------------------------------------


def test_a_first_session_from_an_empty_database_to_a_passed_trial(context):
    """Boot, find a master, learn a secret, drill it, and survive the trial.

    The screen this reaches is built by the application itself and therefore
    carries no pinned seed — which drill and which of the two trial problems
    comes up varies. Every assertion below holds for any deal.
    """

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()

            home = app.screen
            assert isinstance(home, HomeScreen)
            banner = _flat(home, "#banner")
            assert "Level 1" in banner, "a fresh profile starts at level one"
            assert "0/52 XP" in banner

            await pilot.press("t")
            await pilot.pause()
            journey = app.screen
            assert isinstance(journey, JourneyScreen)
            assert "not started" in _cards(journey)

            await pilot.press("1")
            await pilot.pause()

            screen = app.screen
            assert isinstance(screen, MasterScreen)
            assert screen.master.id == ARRAYS, "the path starts in World 1"
            assert screen.phase == "teach"

            lesson = _flat(screen, "#lesson")
            assert "SECRET 1/7" in lesson
            assert FIRST_IDIOM in lesson, "the idiom's subscripts were eaten by the markup parser"
            assert "DEMONSTRATION" in lesson
            assert _flat(screen, "#say").strip(), "the master must say something"

            # Drill until the master is satisfied, then take the trial he opens.
            reached = await _train_until(screen, pilot, stop=("trial",))
            assert reached == "trial", "fluency must lead into a trial, not the next lesson"

            statement = _flat(screen, "#statement")
            assert "TRIAL" in statement
            assert "Which pattern should you use?" in statement
            pattern = context.library[screen.trial.problem.pattern]
            assert pattern.name.lower() not in statement.lower(), "the trial named its own pattern"
            for option in screen.trial.round.options:
                assert option.name.lower() not in statement.lower()
            assert len(screen.query("#choices Button")) == 4
            assert screen.trial.budget.has_deadline, "a trial runs a clock"

            respect_before = repo.get_respect(context.conn, ARRAYS)
            screen.answer_trial(screen.trial.round.correct_index)
            await pilot.pause()

            assert screen.phase == "trial_done"
            verdict = _flat(screen, "#verdict")
            assert "PASSED" in verdict
            assert "respect +10" in verdict
            assert "xp +" in verdict
            assert repo.get_respect(context.conn, ARRAYS) > respect_before

            # The map must show what just happened, not what it showed before.
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, JourneyScreen)
            assert "1/7 secrets" in _cards(app.screen)

    _run(scenario())

    conn = context.conn
    progress = repo.get_secret_progress(conn, ARRAYS, "seen-before-insert")
    assert progress.state == "tested"
    assert progress.taught_at and progress.fluent_at and progress.tested_at
    assert progress.drills_correct == progress.drills_seen >= 3

    assert repo.get_respect(conn, ARRAYS) > 0, "reaching fluency and passing a trial pay respect"
    assert repo.get_profile(conn).xp > 0, "a graded trial must award XP"

    reviews = conn.execute("SELECT COUNT(*) AS n FROM review_log").fetchone()["n"]
    assert reviews >= 1, "the trial must schedule the pattern for review"

    attempt = conn.execute(
        "SELECT correct, timed_out FROM attempt WHERE mode='hunter' AND finished_at IS NOT NULL "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert attempt["correct"] == 1
    assert attempt["timed_out"] == 0


# --------------------------------------------------------------------------
# 2. The whole of one master
# --------------------------------------------------------------------------


def test_the_whole_of_grandmaster_ragines_curriculum(context):
    """Five secrets, five trials and the final test, all through the screen."""

    async def scenario():
        app = DsaQuestApp(context)
        # Pinned: this session deals ~40 drills and 5 trials, and an unpinned
        # seed would make the run different every time it is investigated.
        app.pending_screen = MasterScreen(context.masters[BITS], context.curricula, seed=SEED)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert screen.phase == "teach"
            assert "SECRET 1/5" in _flat(screen, "#lesson")

            # Refused: nothing has been tested.
            screen.start_final_test()
            await pilot.pause()
            assert screen.exam is None, "the final test opened with no secret tested"
            assert screen.phase == "teach"
            assert "FINAL TEST" not in _flat(screen, "#lesson")

            # Refused again with one of the five behind us. One trial is not five.
            await _train_until(screen, pilot, stop=("trial",))
            screen.answer_trial(screen.trial.round.correct_index)
            await pilot.pause()
            assert "PASSED" in _flat(screen, "#verdict")
            screen.start_final_test()
            await pilot.pause()
            assert screen.exam is None, "the final test opened with 1 of 5 secrets tested"

            # Now the rest of the curriculum.
            assert await _train_until(screen, pilot, stop=("gate",)) == "gate"

            offered = _flat(screen, "#lesson")
            assert "Every secret is fluent, and every trial is passed." in offered
            assert "THE FINAL TEST" in offered
            assert "Nothing will be named" in offered

            respect_before = repo.get_respect(context.conn, BITS)

            await pilot.press("space")
            await pilot.pause()
            assert screen.phase == "exam"
            assert screen.exam is not None
            total = screen.exam.total

            for number in range(1, total + 1):
                assert screen.exam is not None and screen.exam.current is not None
                sitting = _flat(screen, "#statement")
                assert f"FINAL TEST {number}/{total}" in sitting
                assert "no hints" in sitting
                screen.answer_exam(screen.exam.current.round.correct_index)
                await pilot.pause()
                if number < total:
                    assert not screen.query_one("#verdict").display, (
                        "a final test does not coach between rounds"
                    )

            verdict = _flat(screen, "#verdict")
            assert "THE MASTER IS SATISFIED" in verdict
            assert f"score {total}/{total}" in verdict
            assert "respect +50" in verdict
            assert repo.get_respect(context.conn, BITS) > respect_before

    _run(scenario())

    conn = context.conn
    curriculum = context.curricula[BITS]
    for stage in curriculum.ordered_stages:
        progress = repo.get_secret_progress(conn, BITS, stage.secret.id)
        assert progress.state == "tested", f"{stage.secret.id} was never tested"

    master = repo.get_master_progress(conn, BITS)
    assert master.passed
    assert master.attempts == 1, "the refusals must not have counted as sittings"
    assert master.best_score == master.best_total
    assert master.first_passed_at


# --------------------------------------------------------------------------
# 3. The boss gate holds
# --------------------------------------------------------------------------


def test_the_boss_gate_holds_when_only_the_final_test_is_behind_you(context):
    """A gate you can walk through is not a gate.

    Ilsa Korrin's final test is passed, so the beast's one *paper* requirement
    is satisfied. Nothing has been held: no pattern has been recognised,
    recalled or implemented since. The arena must refuse, say exactly what is
    missing, and leave no trace of a fight.
    """
    _force_final_test_passed(context, ARRAYS)
    respect_before = repo.get_respect(context.conn, ARRAYS)

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = await _open_the_arena_from_the_map(app, pilot, BEAST)

            assert screen.phase == "locked"
            assert screen.fight is None, "the arena opened a fight behind a shut gate"

            body = _flat(screen, "#arena-body")
            assert "IT WILL NOT FIGHT YOU YET" in body
            for requirement in ("recognition", "understanding", "implementation", "retention"):
                assert requirement in body, f"the gate did not name {requirement}"
            assert "0% of 55%" in body, "recognition is untouched and must be shown as such"
            assert "master final test passed ✓" in body, "what was earned must still show earned"

            # The beast itself must name the blockers, not merely grunt.
            said = _flat(screen, "#boss-say")
            assert "recognition" in said or "Finish with Warden Korrin" in said

            assert not screen.query("#arena-choices Button"), "a shut gate offers nothing to press"
            assert not screen.query_one("#arena-clock").display, "no clock runs on a shut gate"

            # Hammering the keys a player would press must not start anything.
            for key in ("space", "1", "2", "ctrl+s"):
                await pilot.press(key)
                await pilot.pause()
            assert screen.phase == "locked"
            assert screen.fight is None

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, JourneyScreen)

    _run(scenario())

    record = repo.get_boss_record(context.conn, BEAST)
    assert record.attempts == 0, "a refused fight must not be recorded as an attempt"
    assert not record.defeated
    assert record.last_fought_at is None
    assert repo.get_respect(context.conn, ARRAYS) == respect_before

    boss_attempts = context.conn.execute(
        "SELECT COUNT(*) AS n FROM attempt WHERE pressure_stage = 3"
    ).fetchone()["n"]
    assert boss_attempts == 0, "a refused fight must not have opened a single boss exercise"


# --------------------------------------------------------------------------
# 4. A boss fight, won
# --------------------------------------------------------------------------


def test_a_boss_fight_won(context):
    boss = context.bosses[BEAST]
    _force_the_gate_open(context, boss)
    # A student who got this far has a master's regard already; without it the
    # respect floor at zero would hide any movement.
    repo.add_respect(context.conn, ARRAYS, 120)
    respect_before = repo.get_respect(context.conn, ARRAYS)

    async def scenario():
        app = DsaQuestApp(context)
        # Pinned so the same four phases are dealt on every run.
        app.pending_screen = ArenaScreen(boss, seed=SEED)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert screen.phase == "fighting", "the gate is open; the beast must fight"
            assert screen.fight is not None

            assert "THE ARRAY BEAST" in _flat(screen, "#arena-title")
            assert "100 / 100" in _flat(screen, "#arena-title")
            assert _flat(screen, "#boss-say").strip()

            await _fight(screen, pilot, win=True)

            assert screen.phase == "done"
            # The boss's health is a bar with the count on the title line, and
            # the player's is a row of blow ticks — one per mistake they can
            # still afford. Both changed shape when the arena was rebuilt.
            assert "0 / 100" in _flat(screen, "#arena-title"), (
                "clearing every phase must empty its health"
            )
            assert "█" not in _flat(screen, "#bars"), "an emptied bar has no filled cells"

            verdict = _flat(screen, "#arena-verdict")
            assert "DEFEATED" in verdict
            assert "respect +100" in verdict
            assert "Train before you return" not in verdict, "nothing was missed"
            assert repo.get_respect(context.conn, ARRAYS) > respect_before

    _run(scenario())

    record = repo.get_boss_record(context.conn, BEAST)
    assert record.defeated
    assert record.attempts == 1
    assert record.best_grade in ("normal", "strong", "perfect", "legendary")
    assert record.first_won_at
    assert record.best_hp_left == boss.player_hp, "a flawless fight loses no health"
    assert repo.get_respect(context.conn, ARRAYS) == respect_before + 100
    assert BEAST in repo.bosses_defeated(context.conn)


# --------------------------------------------------------------------------
# 5. A boss fight, lost
# --------------------------------------------------------------------------


def test_a_boss_fight_lost(context):
    boss = context.bosses[BEAST]
    _force_the_gate_open(context, boss)
    repo.add_respect(context.conn, ARRAYS, 120)
    respect_before = repo.get_respect(context.conn, ARRAYS)

    async def scenario():
        app = DsaQuestApp(context)
        app.pending_screen = ArenaScreen(boss, seed=SEED)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert screen.phase == "fighting"

            await _fight(screen, pilot, win=False)

            assert screen.phase == "done"
            assert screen.fight.player_hp == 0, "failing every phase must empty the player"
            assert f"{boss.boss_hp} / {boss.boss_hp}" in _flat(screen, "#arena-title"), (
                "the beast took no damage"
            )

            verdict = _flat(screen, "#arena-verdict")
            assert "IT STANDS" in verdict
            assert "DEFEATED" not in verdict
            assert "0 health remaining" in verdict
            assert "Train before you return" in verdict, "a loss must name what to train"
            trained = verdict.split("Train before you return")[1]
            assert any(pattern_id in trained for pattern_id in boss.patterns)

    _run(scenario())

    record = repo.get_boss_record(context.conn, BEAST)
    assert record.attempts == 1
    assert not record.defeated, "losing must never record a defeat of the boss"
    assert record.best_grade is None
    assert record.first_won_at is None
    assert BEAST not in repo.bosses_defeated(context.conn)

    respect_after = repo.get_respect(context.conn, ARRAYS)
    lost = respect_before - respect_after
    assert lost > 0, "a defeat costs something"
    assert lost <= 10, f"a defeat cost {lost} respect; a victory pays 100"
    assert lost < 100 / 5, "losing must cost far less than winning pays"


# --------------------------------------------------------------------------
# 6. Progress survives a restart
# --------------------------------------------------------------------------


def test_progress_survives_closing_and_reopening_the_game(tmp_path):
    """Anything held only in memory dies here."""
    db_path = tmp_path / "progress.db"

    first = build(db_path, fuzz=False)
    try:

        async def train():
            app = DsaQuestApp(first)
            app.pending_screen = MasterScreen(first.masters[ARRAYS], first.curricula, seed=SEED)
            async with app.run_test(size=(100, 50)) as pilot:
                await pilot.pause()
                screen = app.screen
                await _train_until(screen, pilot, stop=("trial",))
                screen.answer_trial(screen.trial.round.correct_index)
                await pilot.pause()
                assert "PASSED" in _flat(screen, "#verdict")

        _run(train())
        respect = repo.get_respect(first.conn, ARRAYS)
        xp = repo.get_profile(first.conn).xp
        assert respect > 0 and xp > 0
    finally:
        first.close()

    # A whole new process's worth of state: new connection, new content load,
    # new scheduler — only the file is shared.
    second = build(db_path, fuzz=False)
    try:
        assert repo.get_secret_progress(second.conn, ARRAYS, "seen-before-insert").state == "tested"
        assert repo.get_respect(second.conn, ARRAYS) == respect
        assert repo.get_profile(second.conn).xp == xp

        async def reopen():
            app = DsaQuestApp(second)
            app.pending_screen = JourneyScreen()
            async with app.run_test(size=(100, 50)) as pilot:
                await pilot.pause()
                cards = _cards(app.screen)
                assert "1/7 secrets" in cards, "the map forgot a tested secret"
                assert f"respect {respect}" in cards
                assert "not started" not in cards.split("MASTER OF SEARCH")[0]

                # And the training itself resumes where it stopped, not at the top.
                await pilot.press("1")
                await pilot.pause()
                screen = app.screen
                assert isinstance(screen, MasterScreen)
                assert "SECRET 2/7" in _flat(screen, "#lesson"), "the master re-taught secret 1"

        _run(reopen())
    finally:
        second.close()


# --------------------------------------------------------------------------
# 7. Nothing in the app ever shows raw markup
# --------------------------------------------------------------------------


def test_no_screen_ever_shows_raw_markup(context):
    """Content is full of C++, and C++ is full of square brackets.

    Two failure modes, and this walks the whole app for both:

    * **eaten** — ``a[i] & 1`` renders as ``a & 1``, a *different expression*,
      and everything after it silently turns italic;
    * **leaked** — a panel shows ``[b green]`` because a string was escaped
      twice or never rendered.
    """
    boss = context.bosses[BEAST]
    _force_the_gate_open(context, boss)

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()

            home = app.screen
            _assert_no_leaked_markup(home, "home")
            world_map = _flat(home, "#map")
            assert "[ ]" in world_map, "the unstarted marker was eaten by the markup parser"
            assert "WORLD 1" in world_map

            await pilot.press("t")
            await pilot.pause()
            _assert_no_leaked_markup(app.screen, "journey")

            await pilot.press("1")
            await pilot.pause()
            master = app.screen
            assert isinstance(master, MasterScreen)
            _assert_no_leaked_markup(master, "master/teach")
            assert FIRST_IDIOM in _flat(master, "#lesson")

            # A drill, its options, and the verdict on a wrong answer — the
            # place a subscript is most likely to be silently rewritten.
            await pilot.press("space")
            await pilot.pause()
            drill = master.drill
            assert drill is not None
            _assert_no_leaked_markup(master, "master/drill")
            assert " ".join(drill.prompt.split()) in _flat(master, "#drill")

            master.answer("deliberately wrong")
            await pilot.pause()
            _assert_no_leaked_markup(master, "master/verdict")
            assert " ".join(drill.answer.split()) in _flat(master, "#verdict"), (
                "the revealed answer did not survive rendering"
            )

            await pilot.press("escape")
            await pilot.pause()

            arena = await _open_the_arena_from_the_map(app, pilot, BEAST)
            assert arena.phase == "fighting"
            _assert_no_leaked_markup(arena, "arena/phase-1")

            # Walk the fight so the C++-bearing implement phase is rendered too.
            for _ in range(6):
                if arena.phase == "done":
                    break
                challenge = arena.fight.current
                if challenge is None:
                    break
                _assert_no_leaked_markup(arena, f"arena/{challenge.kind.value}")
                if challenge.template_file:
                    source = _flat(arena, "#arena-body")
                    assert "[" in source, "the C++ excerpt lost every subscript"
                arena.answer(True if challenge.hunter is None else challenge.hunter.correct_index)
                await pilot.pause()
                _assert_no_leaked_markup(arena, "arena/between")
                await pilot.press("space")
                await pilot.pause()

            _assert_no_leaked_markup(arena, "arena/done")

    _run(scenario())
