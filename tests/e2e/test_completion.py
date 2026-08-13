"""Mode C, end to end: a hole punched in a template, filled through the screen.

Mode C hands the learner a C++ editor and asks for the missing lines, and the
editor is where it broke: ``TextArea(language="cpp")`` raises
``LanguageDoesNotExist`` because Textual ships fifteen tree-sitter grammars and
C++ is not among them. That took down every completion exercise for several
commits and roughly four hundred and sixty passing tests, because **no test had
ever entered one through the UI**. Everything below enters through the UI.

The shape of the file follows ``test_playthrough.py``: real ``build()`` context,
real screens under ``run_test()``, real repositories, no mocks, and assertions
made against rendered text and the database rather than engine state.

Two things are read out of the engine and nothing else is: *which hole was
dealt* (the app picks it from a clock seed, so a test cannot pin it and must
hold for any deal), and *what that hole's reference body is* — which is what a
learner who had done the work would know.

What compiles, and what does not
--------------------------------
Compilation costs seconds, so it is confined to the two tests marked ``slow``
at the bottom of the file — the ones that submit real C++ through ``ctrl+s``
and let the real judge answer. Everything above them, including the regression
that matters, runs without a compiler: where a test needs a verdict it hands
the screen the same ``CompletionReport`` the worker thread would have handed
it, exactly as ``test_playthrough`` hands the arena the bool its worker would
have returned, and says so where it does it.

The two ``slow`` tests want a machine that is not already saturated: the judge
kills a run at five seconds of wall clock, so a submission that is correct on
an idle box can come back Time Limit Exceeded on one running three test suites
at once. The verdict is printed in the failure message when that happens.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime, timedelta

import pytest
from textual.widgets import Button, Static, TextArea

from dsaquest.content.loader import load_library
from dsaquest.content.paths import read_template
from dsaquest.context import build
from dsaquest.domain.enums import Dimension, GameMode, Rating, Verdict
from dsaquest.domain.judging import JudgeReport

# Aliased: pytest tries to collect any imported class whose name begins with Test.
from dsaquest.domain.judging import TestOutcome as Outcome
from dsaquest.game.modes.complete import (
    TODO_MARKER,
    CompletionReport,
    exercise_source,
    find_hole,
)
from dsaquest.learning import apply_review
from dsaquest.storage import repositories as repo
from dsaquest.tui.app import DsaQuestApp, HomeScreen, SessionScreen
from dsaquest.tui.editor import cpp_highlighting_available

#: Every pattern that ships a template. Parametrised so that a template added
#: later is entered through the screen without anyone remembering to add it.
PATTERNS = tuple(pattern.id for pattern in load_library())

#: The template the graded tests use. Its three holes are the three classic
#: mistakes of the pattern, which is what makes a *wrong* filling writable.
TEMPLATE_PATTERN = "hashing-frequency"
TEMPLATE_FILE = "hashing-frequency.cpp"

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

#: Subscripted expressions that appear in the shipped templates. Whichever of
#: these is on screen must reach the player character for character: ``[i]`` is
#: an italic tag, so an unescaped ``a[i] & 1`` renders as ``a & 1`` — a
#: different expression — and everything after it silently turns italic.
SUBSCRIPTS = (
    "a[i]",
    "a[l]",
    "a[r]",
    "a[mid]",
    "d[l]",
    "h[l]",
    "s[i]",
    "cnt[i]",
    "cnt[x]",
    "cnt[ch - 'a']",
    "g[i][j]",
    "pre[i + 1][j + 1]",
)

#: The template used for the byte-for-byte render check: ``++freq[a[r]];``, a
#: subscript inside a subscript, is on screen whichever of its holes is dealt,
#: and a nested subscript is what an escaper that only recognises tag-shaped
#: bracket runs gets wrong.
NESTED_PATTERN = "sliding-window"
NESTED_FILE = "sliding-window.cpp"

#: Wrong fillings for the three holes of ``hashing-frequency.cpp``, each the
#: mistake the hole exists to prevent. All three compile and all three are
#: caught by the sample inputs, so the judge answers Wrong Answer rather than
#: Compile Error — the differential judge is what is under test, not g++.
WRONG_FILLINGS = {
    "complement-order": """    for (int i = 0; i < (int)a.size(); ++i) {
        pos[a[i]] = i;                   // inserted BEFORE the lookup
        auto it = pos.find(target - a[i]);
        if (it != pos.end()) return {it->second, i};
    }""",
    "pair-count": """    long long pairs = 0;
    for (int x : a) {
        ++cnt[x];                        // counted BEFORE the lookup
        auto it = cnt.find(target - x);
        if (it != cnt.end()) pairs += it->second;
    }""",
    "anagram-key": '    string key = "every word is an anagram of every other";',
}


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------
# Reading the screen
# --------------------------------------------------------------------------


def _flat(screen, selector: str) -> str:
    """One panel's rendered text, whitespace collapsed."""
    return " ".join(str(screen.query_one(selector).visual).split())


def _rendered(screen, selector: str) -> str:
    """One panel's rendered text, verbatim.

    Line breaks and indentation are load-bearing here: the panel is showing a
    C++ program, and the whole question is whether it survived the markup
    parser unchanged.
    """
    return str(screen.query_one(selector).visual)


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


def _segment_colour(editor: TextArea, row: int, needle: str):
    """The colour the editor paints the first rendered segment containing ``needle``."""
    for segment in editor.render_line(row):
        if needle in segment.text and segment.style is not None:
            return segment.style.color
    return None


def _line_colours(editor: TextArea, row: int) -> set:
    """Every distinct colour painted on a rendered line.

    Counting colours rather than probing one token: the better the highlight
    query, the more finely a line is split into segments, so any assertion that
    a particular substring survives as one contiguous segment gets *more*
    fragile as highlighting improves. Distinct-colour count moves the right way.
    """
    return {
        segment.style.color
        for segment in editor.render_line(row)
        if segment.style is not None and segment.style.color is not None and segment.text.strip()
    }


# --------------------------------------------------------------------------
# Driving the screens
# --------------------------------------------------------------------------


def _put_one_completion_on_the_review_pile(context, pattern_id: str) -> None:
    """Make exactly one Mode C exercise due, and nothing else.

    The planner offers a completion when an implementation card falls due.
    Reaching that through the UI means grading an implementation and then
    waiting days for it to come back round; ``apply_review`` is the same call
    a graded exercise ends in, so this drives the memory model directly and
    leaves the session runner — the thing under test — untouched. Reviewing it
    forty days ago is what makes it overdue now.

    ``unlock_pattern`` is the same record ``refresh_unlocks`` writes, and is
    needed only for the patterns that sit behind a prerequisite.
    """
    repo.unlock_pattern(context.conn, pattern_id)
    apply_review(
        context.conn,
        repo.get_card(context.conn, pattern_id, Dimension.IMPLEMENTATION),
        Rating.GOOD,
        scheduler=context.scheduler,
        mode=GameMode.COMPLETE,
        now=datetime.now(UTC) - timedelta(days=40),
    )


async def _settle(pilot, seconds: float = 0.25) -> None:
    """Give the screen's own ``set_timer`` callbacks time to fire.

    The editor focuses itself a tenth of a second after it is mounted, so that
    it does not steal focus from a screen transition still in flight.
    """
    await pilot.pause()
    await asyncio.sleep(seconds)
    await pilot.pause()


async def _open_a_completion_exercise(app, pilot) -> SessionScreen:
    """Press ``r`` on the home screen and land in the exercise a player would.

    Nothing is constructed by hand: the app builds its own plan, deals its own
    hole from its own clock seed, and mounts its own editor.
    """
    await pilot.press("r")
    await _settle(pilot)
    screen = app.screen
    assert isinstance(screen, SessionScreen)
    assert isinstance(screen.current, tuple), (
        f"the review pile opened {type(screen.current).__name__}, not a completion exercise"
    )
    return screen


def _dealt(screen):
    """(template source, the hole the app chose) for the exercise on screen."""
    template_file, hole_id = screen.current
    source = read_template(template_file)
    return source, find_hole(source, hole_id)


def _editor(screen) -> TextArea:
    return screen.query_one("#editor", TextArea)


async def _wait_for_the_judge(screen, pilot, *, timeout: float = 300.0) -> None:
    """Block until the worker thread's verdict has been rendered.

    ``ctrl+s`` starts a thread that compiles and runs C++ and calls back into
    the screen when it is done, so there is nothing to await — only a screen
    state to wait for.
    """
    deadline = time.monotonic() + timeout
    while not screen.awaiting_advance:
        if time.monotonic() > deadline:
            raise AssertionError(f"the judge did not answer within {timeout:.0f}s")
        await pilot.pause()
        await asyncio.sleep(0.05)


def _a_verdict_from_the_worker(verdict: Verdict, *, diff_hint: str = "", log: str = ""):
    """The report the judge thread would have handed back, built without g++.

    Compiling costs seconds. The screen code under test — persistence, XP,
    scheduling and every line of the feedback panel — never sees a compiler,
    only this object, so handing it over directly exercises exactly the code
    the fast suite needs to cover and nothing else. The two ``slow`` tests at
    the bottom of the file do the same journey with the real thing.
    """
    if verdict is Verdict.COMPILE_ERROR:
        return CompletionReport(report=JudgeReport.compile_error(log))
    outcomes = tuple(
        Outcome(
            name=f"sample-{index + 1}",
            verdict=verdict if index == 0 else Verdict.ACCEPTED,
            cpu_ms=12,
            wall_ms=14,
            memory_kb=4096,
            diff_hint=diff_hint if index == 0 else "",
        )
        for index in range(3)
    )
    return CompletionReport(report=JudgeReport(verdict=verdict, outcomes=outcomes))


# --------------------------------------------------------------------------
# 1. The regression: entering the exercise mounts an editor that works
# --------------------------------------------------------------------------


def test_entering_a_completion_exercise_mounts_an_editor_that_takes_typing(context):
    """The bug that survived ~460 tests: this screen would not open at all.

    ``code_editor`` builds a ``TextArea`` and asks it for C++ highlighting, and
    for several commits that raised ``LanguageDoesNotExist`` and took the whole
    exercise down with it. So the assertions are the crude ones: the exercise
    opened, the editor is on screen, it has focus, and a keystroke lands in it.
    """
    _put_one_completion_on_the_review_pile(context, TEMPLATE_PATTERN)

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

            screen = await _open_a_completion_exercise(app, pilot)
            _, hole = _dealt(screen)
            assert screen.current[0] == TEMPLATE_FILE

            editor = _editor(screen)
            assert editor.text == "", "the buffer must start empty — the hole is theirs to fill"
            assert editor.has_focus, "the player must be able to type without reaching for a mouse"

            # The prompt is the whole instruction: which hole, and how to submit.
            prompt = _flat(screen, "#prompt")
            assert f"TODO: {' '.join(hole.prompt.split())}" in prompt
            assert "ctrl+s submit" in prompt

            await pilot.press("i", "n", "t")
            await pilot.pause()
            assert editor.text == "int", "keystrokes did not reach the editor"

            # And the exercise really was opened against the database.
            row = context.conn.execute(
                "SELECT pattern_id, mode, finished_at FROM attempt ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert row["mode"] == GameMode.COMPLETE.value
            assert row["pattern_id"] == TEMPLATE_PATTERN
            assert row["finished_at"] is None, "an unsubmitted exercise is not a finished attempt"

    _run(scenario())


def test_the_editor_highlights_cpp_when_the_grammar_is_available(context):
    """Colour is a nicety, and losing it must never cost the exercise.

    So this asserts both halves of that contract: where the grammar is
    installed the editor really is parsing C++ and really is painting it, and
    where it is not the editor still exists and still takes text.

    The line under test is ordinary C++ — a type, a keyword, an identifier, a
    literal and a comment — not the exotic corners. ``tree-sitter-cpp`` ships
    only the C++ *delta* over the C grammar's queries, so for a long time
    ``int``, ``for``, ``return``, literals and comments were captured by
    nothing at all and a hole filled with C-shaped code came out monochrome
    while the editor still reported itself syntax-aware. Loading the C base
    alongside the delta is what fixed that, and this line is what proves it.
    """
    _put_one_completion_on_the_review_pile(context, TEMPLATE_PATTERN)

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = await _open_a_completion_exercise(app, pilot)
            editor = _editor(screen)

            editor.text = (
                "int best = 0;  // ordinary C++, not the exotic corners\n"
                "auto it = pos.find(need);\n"
            )
            # Park the cursor off the line under inspection: the cursor splits
            # the segment it sits on, and would split the word being measured.
            editor.move_cursor((2, 0))
            await pilot.pause()

            if not cpp_highlighting_available():
                assert editor.language is None, "no grammar means no language, not a crash"
                assert editor.text.startswith("auto"), "the editor must work without colour"
                return

            assert editor.language == "cpp"
            assert editor.is_syntax_aware, "the editor is not parsing what the player types"

            colours = _line_colours(editor, 0)
            assert len(colours) >= 3, (
                "an ordinary line of C++ came out in "
                f"{len(colours)} colour(s) — the editor says it is syntax-aware "
                "but is painting almost nothing"
            )
            assert _segment_colour(editor, 1, "auto") is not None

    _run(scenario())


# --------------------------------------------------------------------------
# 2. The cloze holes: what is removed must stay removed
# --------------------------------------------------------------------------


@pytest.mark.parametrize("pattern_id", PATTERNS)
def test_every_shipped_template_opens_with_its_hole_hidden(context, pattern_id):
    """Open one exercise per template and check the cloze is really a cloze.

    Which hole the app deals comes from a clock seed and cannot be pinned from
    outside, so every assertion here holds for any of a template's holes.
    """
    if pattern_id not in context.bank.patterns_with_problems():
        # The planner will not deal a pattern it cannot also set recognition
        # exercises for, so a template whose problems are not written yet
        # cannot be reached through the session runner at all. That is the
        # planner's rule, not a fact about Mode C.
        pytest.skip(f"{pattern_id} has no problems authored, so no session can deal it")
    _put_one_completion_on_the_review_pile(context, pattern_id)

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = await _open_a_completion_exercise(app, pilot)
            source, hole = _dealt(screen)

            _editor(screen)  # every template must reach a mounted editor
            statement = _rendered(screen, "#statement")

            # The marker syntax is an authoring detail. The player is shown a
            # program with a TODO in it, and never the machinery.
            for panel_id, text in _everything_rendered(screen):
                assert "HOLE" not in text, f"{panel_id} leaked the marker syntax: {text[:200]!r}"
                # The marker is `>>> HOLE` / `<<< HOLE`, not a bare arrow run.
                # C++ produces `>>>` all by itself the moment templates nest:
                # `priority_queue<..., greater<pair<long long, int>>>` ends in
                # three of them, and so would every `vector<vector<int>>`.
                assert ">>> HOLE" not in text, f"{panel_id} leaked an opening marker"
                assert "<<< HOLE" not in text, f"{panel_id} leaked a closing marker"

            assert TODO_MARKER in statement, "the hole is not marked in the program shown"
            assert hole.prompt in statement, "the player is not told what to write"

            # And the removed code is gone, as a contiguous block. Individual
            # lines legitimately recur — these templates teach three variants
            # of one technique — but the body itself must be nowhere on screen.
            body = _normalise(hole.body)
            for panel_id, text in _everything_rendered(screen):
                assert body not in _normalise(text), (
                    f"{pattern_id}:{hole.id} — {panel_id} shows the answer"
                )
            assert _editor(screen).text == "", "the answer must not be pre-filled"

            # Nothing was swallowed on the way to the screen. Every line of the
            # program arrived, and so did every bracket — the character the
            # markup parser eats, and the one C++ cannot spare.
            exercise = exercise_source(source, hole.id)
            assert len(statement.splitlines()) == len(exercise.splitlines())
            assert statement.count("[") == exercise.count("["), "subscripts were eaten"
            assert statement.count("]") == exercise.count("]")

    _run(scenario())


# --------------------------------------------------------------------------
# 3. A markup walk over C++
# --------------------------------------------------------------------------


def test_a_markup_walk_across_a_completion_exercise(context):
    """C++ is full of square brackets, and square brackets are Textual markup.

    Two failure modes, both silent, both fatal to a code exercise:

    * **eaten** — ``a[i] & 1`` renders as ``a & 1``, which is a *different
      expression*, and the rest of the line turns italic;
    * **leaked** — a panel shows ``[b green]`` because something was escaped
      twice or never rendered.

    The walk covers the exercise as presented and the feedback panel after it
    is graded, which is the other place content is interpolated into markup.
    """
    _put_one_completion_on_the_review_pile(context, TEMPLATE_PATTERN)

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = await _open_a_completion_exercise(app, pilot)
            source, hole = _dealt(screen)

            _assert_no_leaked_markup(screen, "completion/presented")

            statement = _rendered(screen, "#statement")
            exercise = exercise_source(source, hole.id)
            expected = [token for token in SUBSCRIPTS if token in exercise]
            assert len(expected) >= 3, (
                f"{TEMPLATE_FILE} showed only {expected} — this walk is no longer walking anything"
            )
            for token in expected:
                assert token in statement, f"the markup parser ate {token!r}"
            assert statement.count("[") == exercise.count("["), "brackets went missing"

            # Grading is where content meets markup a second time. The verdict
            # is handed in rather than compiled, for the reason given above.
            _editor(screen).text = hole.body
            screen.finish_code(
                _a_verdict_from_the_worker(
                    Verdict.WRONG_ANSWER, diff_hint="token 3: expected 1, got 0"
                ),
                hole.body,
            )
            await pilot.pause()

            _assert_no_leaked_markup(screen, "completion/feedback")

    _run(scenario())


def test_the_program_on_screen_is_the_program_the_exercise_builder_produced(context):
    """Byte for byte. A trainer whose C++ is not quite the C++ is teaching a typo.

    ``sliding-window.cpp`` is used because every one of its three holes leaves
    ``++freq[a[r]];`` on screen, so this holds whichever hole is dealt.
    """
    _put_one_completion_on_the_review_pile(context, NESTED_PATTERN)

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = await _open_a_completion_exercise(app, pilot)
            source, hole = _dealt(screen)
            assert screen.current[0] == NESTED_FILE

            statement = _rendered(screen, "#statement")
            assert "freq[a[r]]" in statement, "a nested subscript did not survive rendering"
            assert exercise_source(source, hole.id) in statement

    _run(scenario())


def test_what_the_learner_types_reaches_the_database_unchanged(context):
    """Their code passes through a widget, a worker and a repository. It must arrive.

    Subscripts and post-increments are exactly what a markup layer or an over
    eager escaper would quietly rewrite, and a stored submission that does not
    match what was typed makes every later review of it a lie.
    """
    _put_one_completion_on_the_review_pile(context, TEMPLATE_PATTERN)
    typed = "    if (a[i] & 1) dp[i][j] = 1;\n    cnt[x]++;\n"

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = await _open_a_completion_exercise(app, pilot)

            editor = _editor(screen)
            editor.text = typed
            await pilot.pause()
            assert editor.text == typed, "the editor rewrote the player's code"

            screen.finish_code(
                _a_verdict_from_the_worker(Verdict.WRONG_ANSWER, diff_hint="token 1"),
                editor.text,
            )
            await pilot.pause()

    _run(scenario())

    stored = context.conn.execute(
        "SELECT source, verdict FROM submission ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert stored["source"] == typed
    assert stored["verdict"] == Verdict.WRONG_ANSWER.value


# --------------------------------------------------------------------------
# 4. The feedback panel, without a compiler
# --------------------------------------------------------------------------


def test_a_rejected_filling_is_told_so_and_charged_to_the_learner(context):
    """The whole grading path, minus g++: verdict, feedback, and six tables moved."""
    _put_one_completion_on_the_review_pile(context, TEMPLATE_PATTERN)

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = await _open_a_completion_exercise(app, pilot)
            _, hole = _dealt(screen)

            screen.finish_code(
                _a_verdict_from_the_worker(
                    Verdict.WRONG_ANSWER, diff_hint="token 3: expected 1, got 0"
                ),
                "    // I do not remember",
            )
            await pilot.pause()

            feedback = _flat(screen, "#feedback")
            assert "Wrong Answer" in feedback
            assert "Accepted" not in feedback, "a rejection must not read like a pass"
            assert "token 3: expected 1, got 0" in feedback, "a verdict with no diagnostic teaches"
            assert "space — next" in feedback
            assert screen.awaiting_advance

            # Pinned deliberately. Mode C reveals the reference answer *after*
            # grading, as Mode A reveals the pattern and Mode B the canonical
            # answer; that is coaching, not a leak. What must never happen —
            # asserted in the cloze tests above — is the answer being visible
            # before the player has committed.
            assert "Reference answer" in feedback

            # The failed exercise still ends the session cleanly.
            await pilot.press("space")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen), "the last item did not close the session"

    _run(scenario())

    conn = context.conn
    attempt = conn.execute(
        "SELECT * FROM attempt WHERE mode = 'complete' AND finished_at IS NOT NULL"
    ).fetchone()
    assert attempt["correct"] == 0
    assert attempt["verdict"] == Verdict.WRONG_ANSWER.value
    assert attempt["duration_ms"] is not None

    review = conn.execute("SELECT * FROM review_log ORDER BY id DESC LIMIT 1").fetchone()
    assert review["mode"] == GameMode.COMPLETE.value
    assert review["rating"] == Rating.AGAIN.value, "a rejected implementation is not a pass"
    assert repo.implementations_passed(conn) == 0


def test_the_revealed_reference_answer_survives_the_markup_parser(context):
    """If the answer is going to be shown, it has to be the *actual* answer.

    Every hole in ``hashing-frequency.cpp`` subscripts something, so whichever
    one is dealt this is a real check.
    """
    _put_one_completion_on_the_review_pile(context, TEMPLATE_PATTERN)

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = await _open_a_completion_exercise(app, pilot)
            _, hole = _dealt(screen)

            screen.finish_code(
                _a_verdict_from_the_worker(Verdict.WRONG_ANSWER, diff_hint="token 1"), ""
            )
            await pilot.pause()

            feedback = _rendered(screen, "#feedback")
            assert _normalise(hole.body) in _normalise(feedback), (
                "the revealed answer is not the code the template contains"
            )

    _run(scenario())


def test_the_compiler_s_own_words_reach_the_player_unedited(context):
    """A compile error the player cannot match to their code is not a diagnostic.

    The log below is verbatim from g++ on a real broken filling of this
    template's ``pair-count`` hole.
    """
    _put_one_completion_on_the_review_pile(context, TEMPLATE_PATTERN)
    log = (
        "solution.cpp:87:28: error: 'undefined_thing' was not declared in this scope\n"
        "   87 | for (int q : a) { pairs += undefined_thing[q]; }\n"
        "      |                            ^~~~~~~~~~~~~~~\n"
    )

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = await _open_a_completion_exercise(app, pilot)

            screen.finish_code(_a_verdict_from_the_worker(Verdict.COMPILE_ERROR, log=log), "junk")
            await pilot.pause()

            feedback = _rendered(screen, "#feedback")
            assert Verdict.COMPILE_ERROR.label in feedback
            assert "undefined_thing[q]" in feedback, "the offending subscript was edited out"

    _run(scenario())


# --------------------------------------------------------------------------
# 5. The real thing: g++, the sandbox, and the differential judge
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_a_correct_filling_is_accepted_scored_and_persisted(context):
    """Type the template's own code back into the hole and press ctrl+s.

    One of the two tests here that compile: the intact template is built and
    run as the oracle, then the player's spliced version is built and run
    against its output. It is the property the whole mode rests on — put back
    what was removed, and you are told you are right.
    """
    _put_one_completion_on_the_review_pile(context, TEMPLATE_PATTERN)

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = await _open_a_completion_exercise(app, pilot)
            _, hole = _dealt(screen)

            # Assigned rather than typed: an auto-indenting editor would add
            # its own leading whitespace to code that already carries its own.
            _editor(screen).text = hole.body
            await pilot.press("ctrl+s")
            assert "Compiling and running" in _flat(screen, "#prompt")

            await _wait_for_the_judge(screen, pilot)

            feedback = _flat(screen, "#feedback")
            assert "Accepted" in feedback, feedback
            assert "tests" in feedback, "the player is not told how much of the sample set ran"
            assert "base" in feedback and "= " in feedback, "a pass must show what it paid"
            _assert_no_leaked_markup(screen, "completion/accepted")

            await pilot.press("space")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

    _run(scenario())

    conn = context.conn
    attempt = conn.execute(
        "SELECT * FROM attempt WHERE mode = 'complete' AND finished_at IS NOT NULL"
    ).fetchone()
    assert attempt["correct"] == 1
    assert attempt["verdict"] == Verdict.ACCEPTED.value
    assert attempt["xp_awarded"] > 0
    assert attempt["pattern_id"] == TEMPLATE_PATTERN

    submission = conn.execute("SELECT * FROM submission ORDER BY id DESC LIMIT 1").fetchone()
    assert submission["attempt_id"] == attempt["id"]
    assert submission["verdict"] == Verdict.ACCEPTED.value
    assert submission["tests_total"] >= 3, "the differential judge ran no sample inputs"
    assert submission["tests_passed"] == submission["tests_total"]
    assert submission["source"].strip(), "the answer was graded but never stored"

    assert repo.get_profile(conn).xp > 0
    assert repo.implementations_passed(conn) == 1

    card = repo.get_card(conn, TEMPLATE_PATTERN, Dimension.IMPLEMENTATION)
    assert card.reps == 2, "the review that set this test up, plus the one just earned"
    assert card.due_at > datetime.now(UTC).isoformat(timespec="seconds"), (
        "a passed implementation must be scheduled forward, not left due"
    )
    review = conn.execute("SELECT * FROM review_log ORDER BY id DESC LIMIT 1").fetchone()
    assert review["card_id"] == card.id
    assert review["attempt_id"] == attempt["id"]
    assert review["rating"] != Rating.AGAIN.value


@pytest.mark.slow
def test_a_wrong_filling_is_judged_wrong_by_the_template_itself(context):
    """The classic mistake for whichever hole was dealt, compiled and run.

    Each filling below compiles cleanly and is wrong only in what it computes,
    so nothing here is caught by g++ — it is caught by the intact template
    disagreeing with the player's version on a sample input. That is the
    differential judge doing the one job it exists for.
    """
    _put_one_completion_on_the_review_pile(context, TEMPLATE_PATTERN)

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = await _open_a_completion_exercise(app, pilot)
            _, hole = _dealt(screen)
            wrong = WRONG_FILLINGS.get(hole.id)
            assert wrong is not None, f"no wrong filling is written for hole {hole.id!r}"
            assert _normalise(wrong) != _normalise(hole.body)

            _editor(screen).text = wrong
            await pilot.press("ctrl+s")
            await _wait_for_the_judge(screen, pilot)

            feedback = _flat(screen, "#feedback")
            assert "Wrong Answer" in feedback, feedback
            assert "Accepted" not in feedback
            _assert_no_leaked_markup(screen, "completion/rejected")

    _run(scenario())

    conn = context.conn
    attempt = conn.execute(
        "SELECT * FROM attempt WHERE mode = 'complete' AND finished_at IS NOT NULL"
    ).fetchone()
    assert attempt["correct"] == 0
    assert attempt["verdict"] == Verdict.WRONG_ANSWER.value

    submission = conn.execute("SELECT * FROM submission ORDER BY id DESC LIMIT 1").fetchone()
    assert submission["verdict"] == Verdict.WRONG_ANSWER.value
    assert submission["tests_passed"] < submission["tests_total"]
    assert repo.implementations_passed(conn) == 0
