"""End-to-end coverage of Mode B — Pattern Recall — through the real screen.

The thing worth guarding here is the panel shown *after* the learner commits:
the canonical answer, which is what a master would have said. Every cue in the
content carries an authored ``note`` giving the reason the cue means what it
means — "No contiguity means no window." All 126 of them were written, and
``dsa pattern`` printed them, but this panel dropped every one and showed the
bare cue.

That is worth a test rather than a code comment, because it is invisible: the
panel looked complete, the tests passed, and the only symptom was that the
moment a learner most needs an explanation they were handed a list to memorise.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from textual.widgets import Static

from dsaquest.context import build
from dsaquest.domain.enums import Dimension, GameMode, Rating
from dsaquest.game.modes.recall import RecallRound, canonical_answer
from dsaquest.learning import apply_review
from dsaquest.storage import repositories as repo
from dsaquest.tui.app import DsaQuestApp, SessionScreen

RECALL_PATTERN = "sliding-window"


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


def _put_one_recall_on_the_review_pile(context, pattern_id: str) -> None:
    """Make exactly one Mode B exercise due.

    ``apply_review`` is the call a graded exercise ends in, so this drives the
    memory model directly and leaves the session runner — the thing under test
    — untouched. Reviewing it forty days ago is what makes it overdue now.
    """
    repo.unlock_pattern(context.conn, pattern_id)
    apply_review(
        context.conn,
        repo.get_card(context.conn, pattern_id, Dimension.RECALL),
        Rating.GOOD,
        scheduler=context.scheduler,
        mode=GameMode.RECALL,
        now=datetime.now(UTC) - timedelta(days=40),
    )


async def _open_a_recall_exercise(app, pilot) -> SessionScreen | None:
    """Press ``r`` and land where a player would, or None if none was dealt."""
    await pilot.press("r")
    await pilot.pause()
    await asyncio.sleep(0.2)
    await pilot.pause()
    screen = app.screen
    if not isinstance(screen, SessionScreen):
        return None
    return screen if isinstance(screen.current, RecallRound) else None


def _text(screen, selector: str) -> str:
    return str(screen.query_one(selector, Static).visual)


# ------------------------------------------------------------------ engine


def test_the_canonical_answer_gives_the_reason_for_every_cue(context):
    """A cue without its reason is a fact to memorise."""
    missing: list[str] = []
    for pattern in context.library:
        rendered = canonical_answer(pattern, library=context.library)
        for signal in pattern.signals:
            if signal.note.strip() and signal.note.strip() not in rendered:
                missing.append(f"{pattern.id}: signal {signal.cue[:40]!r}")
        for anti in pattern.anti_signals:
            if anti.note.strip() and anti.note.strip() not in rendered:
                missing.append(f"{pattern.id}: anti-signal {anti.cue[:40]!r}")
    assert not missing, f"{len(missing)} authored notes never reach the learner: {missing[:5]}"


def test_an_anti_signal_names_the_pattern_it_points_at(context):
    """A raw slug in the middle of prose reads as debris."""
    pattern = context.library[RECALL_PATTERN]
    assert pattern.anti_signals, f"{RECALL_PATTERN} has no anti-signals to check"

    with_library = canonical_answer(pattern, library=context.library)
    for anti in pattern.anti_signals:
        assert context.library[anti.instead].name in with_library

    # And without a library it degrades to the id rather than raising: a
    # missing library must not cost the learner the explanation.
    without = canonical_answer(pattern)
    assert pattern.anti_signals[0].instead in without
    assert pattern.anti_signals[0].note.strip() in without


def test_every_pattern_s_canonical_answer_still_carries_its_structure(context):
    for pattern in context.library:
        rendered = canonical_answer(pattern, library=context.library)
        assert "SIGNALS" in rendered
        assert "INVARIANT" in rendered
        assert "COMPLEXITY" in rendered
        assert pattern.invariant.strip()[:40] in rendered


# ------------------------------------------------------------------- screen


def test_the_reasons_reach_the_player_through_the_real_screen(context):
    """The panel a learner reads, at the moment they have just failed to recall."""

    def journey():
        async def scenario():
            _put_one_recall_on_the_review_pile(context, RECALL_PATTERN)
            app = DsaQuestApp(context)
            async with app.run_test(size=(110, 50)) as pilot:
                await pilot.pause()
                screen = await _open_a_recall_exercise(app, pilot)
                if screen is None:
                    pytest.skip("the planner dealt no recall exercise this run")

                pattern = screen.current.pattern
                # Mode B names the pattern and hides everything else — that is
                # what distinguishes it from Mode A, where naming it would be
                # giving away the answer.
                before = "\n".join(str(s.visual) for s in screen.query(Static))
                assert pattern.name in before
                assert pattern.invariant.strip()[:40] not in before, (
                    "the answer was on screen before the learner committed"
                )

                # Commit an answer, however poor, then read what the master says.
                screen.submit_recall()
                await pilot.pause()
                await asyncio.sleep(0.2)
                await pilot.pause()

                shown = "\n".join(str(s.visual) for s in screen.query(Static))
                noted = [s for s in pattern.signals if s.note.strip()]
                assert noted, f"{pattern.id} has no signal notes to show"
                for signal in noted:
                    assert signal.note.strip() in shown, (
                        f"the reason for {signal.cue[:40]!r} never reached the screen"
                    )
                for anti in pattern.anti_signals:
                    if anti.note.strip():
                        assert anti.note.strip() in shown
                        assert context.library[anti.instead].name in shown

        _run(scenario())

    journey()
