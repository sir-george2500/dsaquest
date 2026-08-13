"""The TUI, driven headlessly.

Textual can run without a terminal, so these are real end-to-end tests: boot
the app, walk the screens, press the keys a learner would press, and check that
progress actually moved in the database.
"""

from __future__ import annotations

import asyncio

import pytest

from dsaquest.context import build
from dsaquest.storage import repositories as repo
from dsaquest.tui.app import DsaQuestApp, HomeScreen, SessionScreen


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


def test_the_app_boots_to_a_campaign_map(context):
    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            rendered = str(app.screen.query_one("#map").visual)
            assert "WORLD 1" in rendered
            assert "Sliding Window" in rendered
            banner = str(app.screen.query_one("#banner").visual)
            assert "Level 1" in banner

    _run(scenario())


def test_locked_patterns_are_marked_on_the_map(context):
    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test() as pilot:
            await pilot.pause()
            rendered = str(app.screen.query_one("#map").visual)
            assert "🔒" in rendered, "nothing is shown as locked on a fresh profile"

    _run(scenario())


def test_pressing_p_starts_a_session_with_an_unlabelled_problem(context):
    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()

            assert isinstance(app.screen, SessionScreen)
            statement = str(app.screen.query_one("#statement").visual)
            assert "Which pattern should you use?" in statement
            # The statement must not name the pattern it is testing.
            assert "sliding window" not in statement.lower()

            buttons = app.screen.query("#options Button")
            assert len(buttons) == 4

    _run(scenario())


def test_answering_records_an_attempt_and_moves_progress(context):
    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()

            screen = app.screen
            assert isinstance(screen, SessionScreen)
            correct_index = screen.current.correct_index  # type: ignore[union-attr]

            await pilot.press(str(correct_index + 1))
            await pilot.pause()

            feedback = str(screen.query_one("#feedback").visual)
            assert "Correct" in feedback
            assert "Why:" in feedback

        # Progress must have been persisted, not just displayed.
        assert repo.get_profile(context.conn).xp > 0
        row = context.conn.execute(
            "SELECT correct, chosen_pattern_id FROM attempt WHERE finished_at IS NOT NULL"
        ).fetchone()
        assert row["correct"] == 1
        assert row["chosen_pattern_id"] is not None
        assert context.conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0] == 1

    _run(scenario())


def test_a_wrong_answer_shows_the_discriminator_and_logs_the_confusion(context):
    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()

            screen = app.screen
            assert isinstance(screen, SessionScreen)
            round_ = screen.current
            wrong = (round_.correct_index + 1) % len(round_.options)  # type: ignore[union-attr]

            await pilot.press(str(wrong + 1))
            await pilot.pause()

            feedback = str(screen.query_one("#feedback").visual)
            assert "No." in feedback
            assert "Why:" in feedback

        pairs = repo.confusion_pairs(context.conn)
        assert pairs, "a wrong recognition answer must be recorded as a confusion"

    _run(scenario())


def test_space_advances_to_the_next_exercise(context):
    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()

            screen = app.screen
            assert isinstance(screen, SessionScreen)
            first = screen.index

            await pilot.press("1")
            await pilot.pause()
            assert screen.awaiting_advance

            await pilot.press("space")
            await pilot.pause()
            assert screen.index == first + 1

    _run(scenario())


def test_answers_are_ignored_until_the_next_exercise_is_presented(context):
    """Double-tapping a key must not record two attempts for one question."""

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()

            await pilot.press("1")
            await pilot.pause()
            await pilot.press("2")
            await pilot.pause()

        finished = context.conn.execute(
            "SELECT COUNT(*) FROM attempt WHERE finished_at IS NOT NULL"
        ).fetchone()[0]
        assert finished == 1

    _run(scenario())


def test_escape_returns_to_the_map(context):
    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            assert isinstance(app.screen, SessionScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

    _run(scenario())
