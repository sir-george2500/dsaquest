"""The arena's room, and the prologue that starts the game.

The stage is painted to whatever size the widget happens to be, which is the
part worth testing: it looked right at a hundred columns and marched pillars
straight across the boss at fifty, because nothing reserved the middle. So
these assert the *properties* that must hold at every size, not one rendering.
"""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Static

from dsaquest.art.sprite import load_sprite
from dsaquest.context import build
from dsaquest.domain.enums import Dimension, GameMode, Rating
from dsaquest.learning import apply_review
from dsaquest.storage import repositories as repo
from dsaquest.tui.app import DsaQuestApp, HomeScreen
from dsaquest.tui.arena import ArenaScreen
from dsaquest.tui.roster import sprite_for
from dsaquest.tui.stage import stage_text
from dsaquest.tui.story import StoryScreen, load_story

BEAST = "the-array-beast"


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


def _lines(text) -> list[str]:
    return text.plain.split("\n")


# ------------------------------------------------------------------- stage


@pytest.mark.parametrize("width", [40, 50, 64, 80, 104, 160])
def test_the_stage_fills_exactly_the_size_it_is_given(width):
    sprite = load_sprite(sprite_for(BEAST))
    text = stage_text(sprite, width=width, height=20)
    lines = _lines(text)
    assert len(lines) == 20
    assert {len(line) for line in lines} == {max(40, width)}


@pytest.mark.parametrize("width", [40, 50, 64, 80, 104, 160])
def test_the_middle_of_the_room_is_kept_clear_for_the_boss(width):
    """Pillars belong at the edges. They once marched across the boss.

    Rendered with no sprite, the central fifth of the wall must contain no
    pillar glyph at any width — otherwise a narrow terminal draws stone
    through the thing you are fighting.
    """
    text = stage_text(None, width=width, height=20)
    lines = _lines(text)
    low, high = int(width * 0.4), int(width * 0.6)
    for row in lines[:6]:
        middle = row[low:high]
        assert "█" not in middle, f"a pillar crosses the middle at width {width}"


def test_the_boss_stands_in_the_room_rather_than_over_it():
    """Some of the room must survive around the sprite."""
    sprite = load_sprite(sprite_for(BEAST))
    with_boss = stage_text(sprite, width=100, height=24).plain
    without = stage_text(None, width=100, height=24).plain
    assert with_boss != without, "the sprite was never painted"
    assert len(with_boss.split("\n")) == len(without.split("\n"))


def test_a_missing_sprite_still_draws_a_room():
    text = stage_text(None, width=80, height=20)
    assert len(_lines(text)) == 20


def test_the_torches_go_out_when_the_boss_is_beaten():
    lit = stage_text(None, width=100, height=20, lit=True).plain
    dark = stage_text(None, width=100, height=20, lit=False).plain
    assert lit != dark
    assert len(lit) == len(dark), "the room stays, only the light changes"


# ------------------------------------------------------------------- arena


def test_the_arena_shows_the_room_and_both_panels(context):
    async def journey():
        boss = context.bosses[BEAST]
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

        app = DsaQuestApp(context)
        app.pending_screen = ArenaScreen(boss, seed=11)
        async with app.run_test(size=(110, 44)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.3)
            await pilot.pause()
            screen = app.screen

            assert "THE TRIAL" in str(screen.query_one("#trial-panel", Static).visual)
            blows = str(screen.query_one("#blows-panel", Static).visual)
            assert "SCROLL OF BLOWS" in blows
            assert "no blow has landed" in blows, "nothing has happened yet"

            stage = str(screen.query_one("#arena-stage", Static).visual)
            assert stage.strip(), "the room was never painted"

            # Health reads as a count of blows, not a second bar.
            bars = str(screen.query_one("#bars", Static).visual)
            expected = -(-boss.player_hp // boss.damage_taken)
            assert bars.count("▬▬▬") == expected

    _run(journey())


# ------------------------------------------------------------------- story


def test_the_prologue_loads_and_says_what_this_is():
    story = load_story()
    assert story is not None, "no prologue shipped"
    assert len(story) >= 4
    joined = " ".join(beat.text for beat in story.beats)
    # The premise the whole product rests on must actually be stated.
    assert "recognise" in joined
    for beat in story.beats:
        assert beat.title.strip()
        assert len(beat.text) > 80, f"{beat.id} is too thin to be worth a screen"


def test_the_story_opens_by_itself_on_a_profile_that_has_never_played(context, monkeypatch):
    monkeypatch.setattr(DsaQuestApp, "auto_story", True)

    async def journey():
        app = DsaQuestApp(context)
        async with app.run_test(size=(104, 32)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.3)
            await pilot.pause()
            assert isinstance(app.screen, StoryScreen), (
                "a first-time player should be told what this is"
            )

    _run(journey())


def test_the_story_stays_out_of_the_way_once_you_have_played(context, monkeypatch):
    monkeypatch.setattr(DsaQuestApp, "auto_story", True)
    repo.start_attempt(context.conn, pattern_id="sliding-window", mode=GameMode.HUNTER, seed=1)
    context.conn.commit()

    async def journey():
        app = DsaQuestApp(context)
        async with app.run_test(size=(104, 32)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.3)
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

            # Still reachable, for the person who came back after a month.
            await pilot.press("s")
            await pilot.pause()
            assert isinstance(app.screen, StoryScreen)

    _run(journey())


def test_reading_the_story_forwards_and_back(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = StoryScreen(load_story())
        async with app.run_test(size=(104, 32)) as pilot:
            await pilot.pause()
            screen = app.screen
            first = str(screen.query_one("#story-title", Static).visual)

            await pilot.press("space")
            await pilot.pause()
            assert screen.index == 1
            assert str(screen.query_one("#story-title", Static).visual) != first

            await pilot.press("left")
            await pilot.pause()
            assert screen.index == 0
            assert str(screen.query_one("#story-title", Static).visual) == first

            # Every panel is on screen, not scrolled off the top.
            for selector in ("#story-chapter", "#story-title", "#story-progress"):
                widget = screen.query_one(selector, Static)
                assert widget.size.height >= 1
                assert str(widget.visual).strip()

    _run(journey())


def test_the_last_beat_leaves_the_story(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = StoryScreen(load_story())
        async with app.run_test(size=(104, 32)) as pilot:
            await pilot.pause()
            screen = app.screen
            for _ in range(len(screen.story)):
                await pilot.press("space")
                await pilot.pause()
            assert not isinstance(app.screen, StoryScreen), "the prologue must end"

    _run(journey())
