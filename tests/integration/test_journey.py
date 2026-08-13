"""The journey map."""

from __future__ import annotations

import asyncio

import pytest

from dsaquest.context import build
from dsaquest.storage import repositories as repo
from dsaquest.tui.app import DsaQuestApp, HomeScreen
from dsaquest.tui.journey import JourneyScreen
from dsaquest.tui.master import MasterScreen


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


def _flat(screen, selector: str) -> str:
    return " ".join(str(screen.query_one(selector).visual).split())


def _cards(screen) -> str:
    """All master cards as one flat string.

    #masters is a container, not a Static, so its text lives in the child cards.
    """
    return " ".join(" ".join(str(card.visual).split()) for card in screen.query(".master-card"))


def _teaching(context) -> list[str]:
    return [m.id for m in context.masters.values() if m.id in context.curricula]


def test_only_masters_with_a_curriculum_are_offered(context):
    """A character with nothing to teach is a door onto an empty room."""

    async def scenario():
        app = DsaQuestApp(context)
        app.pending_screen = JourneyScreen()
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            offered = {m.id for m in app.screen.masters}
            assert offered == set(_teaching(context))
            for master_id in offered:
                assert master_id in context.curricula

    _run(scenario())


def test_masters_are_listed_in_campaign_order(context):
    """Earliest world first, so the path reads top to bottom."""

    async def scenario():
        app = DsaQuestApp(context)
        app.pending_screen = JourneyScreen()
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            screen = app.screen
            positions = [screen._campaign_position(m) for m in screen.masters]
            assert positions == sorted(positions)

    _run(scenario())


def test_a_card_states_progress_in_terms_the_student_can_act_on(context):
    async def scenario():
        app = DsaQuestApp(context)
        app.pending_screen = JourneyScreen()
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            rendered = _cards(app.screen)
            assert "secrets" in rendered
            assert "respect" in rendered
            assert "not started" in rendered or "secret(s) left" in rendered

    _run(scenario())


def test_choosing_a_master_enters_training(context):
    async def scenario():
        app = DsaQuestApp(context)
        app.pending_screen = JourneyScreen()
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            await pilot.press("1")
            await pilot.pause()
            assert isinstance(app.screen, MasterScreen)

    _run(scenario())


def test_returning_from_a_master_shows_the_new_progress(context):
    """A stale map is worse than none — it lies about what remains."""

    async def scenario():
        app = DsaQuestApp(context)
        app.pending_screen = JourneyScreen()
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            journey = app.screen
            before = _cards(journey)

            master_id = journey.masters[0].id
            repo.add_respect(context.conn, master_id, 42)

            await pilot.press("1")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            assert isinstance(app.screen, JourneyScreen)
            after = _cards(app.screen)
            assert after != before
            assert "respect 42" in after

    _run(scenario())


def test_the_map_is_skipped_when_there_is_only_one_master(context):
    """One master is not a choice."""

    async def scenario():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            await pilot.press("t")
            await pilot.pause()

            expected = MasterScreen if len(_teaching(context)) == 1 else JourneyScreen
            assert isinstance(app.screen, expected)

    _run(scenario())


def test_escape_returns_to_the_map_not_out_of_the_app(context):
    async def scenario():
        app = DsaQuestApp(context)
        app.pending_screen = JourneyScreen()
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

    _run(scenario())
