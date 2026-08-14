"""Delta-X's journey: the game must always know what happens next.

The product's failure before this existed was not a missing feature. It was
that opening the game presented a menu, so the player had to decide what to do
and had no way to decide well. These tests assert the fix as a property: from
any state, there is exactly one next step, and it is the right one.

The state is derived rather than stored, so the way to move Delta-X along is to
record the same facts the learning system records — a secret tested, a final
test passed, a guardian felled. That is deliberate, and these tests exercise it
the same way, because a test that wrote to a story table would be testing a
second source of truth that does not exist.
"""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Static

from dsaquest.context import build
from dsaquest.journey import Objective, boss_for, chapter_statuses, load_chapters, next_step
from dsaquest.storage import repositories as repo
from dsaquest.tui.app import DsaQuestApp, HomeScreen
from dsaquest.tui.master import MasterScreen
from dsaquest.tui.roster import RosterScreen
from dsaquest.tui.story import StoryScreen


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


def _hold_every_secret(context, master_id: str) -> None:
    curriculum = context.curricula[master_id]
    for stage in curriculum.stages:
        repo.ensure_secret(context.conn, master_id, stage.secret.id)
        repo.set_secret_state(context.conn, master_id, stage.secret.id, "tested")
    context.conn.commit()


def _finish_chapter(context, chapter) -> None:
    _hold_every_secret(context, chapter.master)
    repo.record_final_test(context.conn, chapter.master, score=6, total=6, passed=True)
    boss = boss_for(context, chapter)
    if boss is not None:
        repo.record_boss_fight(
            context.conn,
            boss.id,
            won=True,
            grade="normal",
            duration_ms=1000,
            hp_left=50,
            hints_used=0,
        )
    context.conn.commit()


# ---------------------------------------------------------------- the story


def test_the_road_is_built_from_the_masters_that_exist(context):
    """The story wraps the cast; it does not invent a second one."""
    story = load_chapters()
    assert story.hero == "DELTA-X"
    assert story.chapters, "no chapters"

    for chapter in story.chapters:
        assert chapter.master in context.masters, f"{chapter.id} names an unknown master"
        assert boss_for(context, chapter) is not None, f"{chapter.id} has no guardian"
        assert chapter.arrival and chapter.master_says, f"{chapter.id} has no narrative"

    assert story.final is not None
    assert story.final.boss in context.bosses


def test_every_master_appears_exactly_once_on_the_road(context):
    chapters = load_chapters().chapters
    masters = [c.master for c in chapters]
    assert len(set(masters)) == len(masters), "a master is on the road twice"
    missing = set(context.masters) - set(masters)
    assert not missing, f"masters with no chapter: {sorted(missing)}"


# ----------------------------------------------------------- the next step


def test_a_new_warrior_is_told_who_he_is_first(context):
    step = next_step(context)
    assert step.objective is Objective.PROLOGUE


def test_after_the_prologue_the_first_master_is_named(context):
    repo.set_flag(context.conn, "prologue_read")
    context.conn.commit()
    step = next_step(context)
    assert step.objective is Objective.MEET_MASTER
    assert step.master_id == load_chapters().chapters[0].master
    assert step.is_action


def test_mid_lesson_it_resumes_rather_than_restarting(context):
    repo.set_flag(context.conn, "prologue_read")
    first = load_chapters().chapters[0]
    curriculum = context.curricula[first.master]
    repo.ensure_secret(context.conn, first.master, curriculum.stages[0].secret.id)
    repo.set_secret_state(context.conn, first.master, curriculum.stages[0].secret.id, "tested")
    context.conn.commit()

    step = next_step(context)
    assert step.objective in (Objective.TRAIN, Objective.TRIAL)
    assert step.master_id == first.master
    assert step.chapter is not None and step.chapter.id == first.id


def test_holding_every_secret_offers_the_final_test(context):
    repo.set_flag(context.conn, "prologue_read")
    first = load_chapters().chapters[0]
    _hold_every_secret(context, first.master)

    step = next_step(context)
    assert step.objective is Objective.FINAL_TEST
    assert step.master_id == first.master


def test_passing_the_final_test_points_at_the_guardian(context):
    repo.set_flag(context.conn, "prologue_read")
    first = load_chapters().chapters[0]
    _hold_every_secret(context, first.master)
    repo.record_final_test(context.conn, first.master, score=6, total=6, passed=True)
    context.conn.commit()

    step = next_step(context)
    # The gate reads mastery, not intention, so on a seeded profile it is
    # usually shut — and either way the step is about the guardian.
    assert step.objective in (Objective.BOSS, Objective.GATE_SHUT)
    assert step.boss_id == boss_for(context, first).id
    if step.objective is Objective.GATE_SHUT:
        assert step.blockers, "a shut gate must say what it wants"


def test_felling_a_guardian_moves_to_the_next_chapter(context):
    repo.set_flag(context.conn, "prologue_read")
    chapters = load_chapters().chapters
    _finish_chapter(context, chapters[0])

    step = next_step(context)
    assert step.chapter is not None
    assert step.chapter.id == chapters[1].id, "the road did not advance"


def test_the_whole_road_leads_to_the_elite_coder(context):
    repo.set_flag(context.conn, "prologue_read")
    for chapter in load_chapters().chapters:
        _finish_chapter(context, chapter)

    step = next_step(context)
    assert step.boss_id == load_chapters().final.boss
    assert step.objective in (Objective.ELITE_CODER, Objective.GATE_SHUT)


def test_there_is_always_a_next_step(context):
    """The property the whole module exists for: never a dead end."""
    repo.set_flag(context.conn, "prologue_read")
    for chapter in load_chapters().chapters:
        step = next_step(context)
        assert step.title and step.detail, "a step with nothing to say"
        _finish_chapter(context, chapter)
    assert next_step(context).title


# ------------------------------------------------------------------- map


def test_the_map_shows_the_road_in_order(context):
    road = chapter_statuses(context)
    assert len(road) == len(load_chapters().chapters)
    assert road[0].reachable, "the first chapter must be open"
    assert not road[1].reachable, "later chapters start sealed"
    assert all(s.fraction == 0.0 for s in road)

    _hold_every_secret(context, road[0].chapter.master)
    repo.record_final_test(context.conn, road[0].chapter.master, score=6, total=6, passed=True)
    context.conn.commit()

    after = chapter_statuses(context)
    assert after[0].fraction > road[0].fraction
    assert after[0].final_passed


# ---------------------------------------------------------------- screen


def test_the_home_screen_leads_with_the_quest(context):
    async def journey():
        repo.set_flag(context.conn, "prologue_read")
        context.conn.commit()
        app = DsaQuestApp(context)
        async with app.run_test(size=(104, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, HomeScreen)

            quest = str(screen.query_one("#quest", Static).visual)
            assert "CURRENT QUEST" in quest
            assert next_step(context).title in quest

            actions = str(screen.query_one("#actions", Static).visual)
            assert "Continue Journey" in actions

            shown = str(screen.query_one("#banner", Static).visual)
            assert "DELTA-X" in shown

    _run(journey())


def test_continue_journey_goes_where_the_step_says(context):
    async def journey():
        repo.set_flag(context.conn, "prologue_read")
        context.conn.commit()
        app = DsaQuestApp(context)
        async with app.run_test(size=(104, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()
            # The first step is meeting a master, so that is where it lands.
            assert isinstance(app.screen, MasterScreen)

    _run(journey())


def test_a_brand_new_warrior_is_taken_to_the_story(context):
    async def journey():
        app = DsaQuestApp(context)
        async with app.run_test(size=(104, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()
            if isinstance(app.screen, StoryScreen):
                return  # opened by itself, which is the intended behaviour
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, StoryScreen)

    _run(journey())


# ------------------------------------------------------------------- naming


def test_the_warrior_is_named_by_the_player(context, monkeypatch):
    """The hero is whoever the player says. Delta-X is only the default."""
    from textual.widgets import Input

    monkeypatch.setattr(DsaQuestApp, "auto_story", True)

    async def journey():
        app = DsaQuestApp(context)
        async with app.run_test(size=(104, 34)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, StoryScreen)

            while not screen.story.beats[screen.index].ask_name:
                await pilot.press("space")
                await pilot.pause()

            field = screen.query_one("#story-name", Input)
            assert field.display, "the naming beat must show a field"
            assert field.value, "prefilled, so pressing on still leaves you somebody"

            field.value = "KWIZERA"
            # Space belongs to the field here — names contain spaces — so enter
            # is what moves on, and the hint says so.
            assert "enter" in str(screen.query_one("#story-progress", Static).visual)
            await pilot.press("enter")
            await pilot.pause()

        assert repo.warrior_name(context.conn) == "KWIZERA"

    _run(journey())


def test_the_name_reaches_the_home_screen(context):
    repo.set_setting(context.conn, "warrior_name", "KWIZERA")
    repo.set_flag(context.conn, "prologue_read")
    context.conn.commit()

    async def journey():
        app = DsaQuestApp(context)
        async with app.run_test(size=(104, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()
            banner = str(app.screen.query_one("#banner", Static).visual)
            assert "KWIZERA" in banner
            assert "DELTA-X" not in banner

    _run(journey())


def test_an_unnamed_warrior_is_still_somebody(context):
    assert repo.warrior_name(context.conn) == "DELTA-X"


def test_the_home_screen_redraws_when_you_come_back(context):
    """It is mounted once and lives under everything, so it must refresh."""

    async def journey():
        repo.set_flag(context.conn, "prologue_read")
        context.conn.commit()
        app = DsaQuestApp(context)
        async with app.run_test(size=(104, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()
            home = app.screen
            before = str(home.query_one("#quest", Static).visual)

            first = load_chapters().chapters[0]
            _hold_every_secret(context, first.master)

            app.push_screen(RosterScreen())
            await pilot.pause()
            app.pop_screen()
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()

            after = str(app.screen.query_one("#quest", Static).visual)
            assert after != before, "the quest did not advance on return"

    _run(journey())
