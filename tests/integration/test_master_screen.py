"""Training under a master, driven headlessly."""

from __future__ import annotations

import asyncio

import pytest

from dsaquest.context import build
from dsaquest.storage import repositories as repo
from dsaquest.tui.app import DsaQuestApp
from dsaquest.tui.master import MasterScreen

MASTER_ID = "master_bits"


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


def _launch(context):
    app = DsaQuestApp(context)
    app.pending_screen = MasterScreen(context.masters[MASTER_ID], context.curricula)
    return app


def _text(screen, selector: str) -> str:
    return str(screen.query_one(selector).visual)


def test_the_master_greets_and_teaches_the_first_secret(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, MasterScreen)

            assert _text(screen, "#say").strip()
            lesson = _text(screen, "#lesson")
            assert "SECRET 1/5" in lesson
            assert "n & 1" in lesson
            assert "DEMONSTRATION" in lesson
            assert "WATCH FOR" in lesson
            assert screen.phase == "teach"

        # Delivering the lesson must be recorded, not merely displayed.
        assert repo.get_secret_progress(context.conn, MASTER_ID, "lowest-bit").is_taught

    _run(scenario())


def test_the_portrait_renders_without_any_image_support(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            assert _text(app.screen, "#portrait").strip()

    _run(scenario())


def test_space_moves_from_the_lesson_into_drills(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()

            screen = app.screen
            assert screen.phase == "drill"
            assert screen.drill is not None
            assert _text(screen, "#drill").strip()

    _run(scenario())


def test_answering_a_drill_correctly_is_recorded_and_explained(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()

            screen = app.screen
            drill = screen.drill
            assert drill is not None

            if drill.options:
                await pilot.press(str(drill.correct_index + 1))
            else:
                screen.answer(drill.answer)
            await pilot.pause()

            verdict = _text(screen, "#verdict")
            assert "Correct" in verdict
            assert drill.explanation[:30] in verdict

        progress = repo.get_secret_progress(context.conn, MASTER_ID, "lowest-bit")
        assert progress.drills_seen == 1
        assert progress.drills_correct == 1

    _run(scenario())


def test_a_wrong_answer_reveals_the_answer_and_still_explains(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()

            screen = app.screen
            drill = screen.drill
            assert drill is not None
            wrong = next(o for o in drill.options if o != drill.answer) if drill.options else "no"
            screen.answer(wrong)
            await pilot.pause()

            verdict = _text(screen, "#verdict")
            assert "No." in verdict
            assert drill.answer in verdict, "a wrong answer must reveal the right one"

        # Failing a drill must never cost respect.
        assert repo.get_respect(context.conn, MASTER_ID) == 0

    _run(scenario())


def test_drilling_a_secret_to_fluency_advances_the_stage(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()

            screen = app.screen
            for _ in range(12):
                drill = screen.drill
                if drill is None:
                    break
                screen.answer(drill.answer)
                await pilot.pause()
                if screen.phase == "fluent":
                    break
                await pilot.press("space")
                await pilot.pause()

            assert screen.phase == "fluent"
            assert "FLUENT" in _text(screen, "#verdict")

            await pilot.press("space")
            await pilot.pause()
            assert screen.stage is not None
            assert screen.stage.order == 1, "should have advanced to the second secret"

        assert repo.get_respect(context.conn, MASTER_ID) > 0

    _run(scenario())


def test_the_track_shows_which_secrets_are_done(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            track = _text(app.screen, "#track")
            assert "n & 1" in track
            assert "respect" in track

    _run(scenario())


def test_escape_leaves_the_master(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, MasterScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, MasterScreen)

    _run(scenario())
