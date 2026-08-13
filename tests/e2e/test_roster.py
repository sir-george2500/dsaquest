"""End-to-end coverage of the roster and its pixel art.

Two things are worth testing here and the rest is decoration.

**The numbers on a card are the player's own.** A card that shows invented
flavour is wallpaper; a card that shows your record is worth opening. So these
tests change the save file and assert the card changes with it.

**Missing art must not take the screen down.** Sprites are authored separately
from code and will always be partly absent. A card with no sprite keeps its
frame and its layout, so the roster does not reflow when art lands.
"""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Static

from dsaquest.art.sprite import SpriteError, load_sprite, parse_sprite, sprite_segments
from dsaquest.context import build
from dsaquest.storage import repositories as repo
from dsaquest.tui.app import DsaQuestApp, HomeScreen
from dsaquest.tui.card import WardenCard, clip, letterspace
from dsaquest.tui.roster import RosterScreen, sprite_for, sprites_dir

LEAKED_MARKUP = ("[/]", "[b]", "[dim]", "[green]", "[red]", "[b green]", "[#8a7f6d]")


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


def _all_text(screen) -> str:
    return "\n".join(str(s.visual) for s in screen.query(Static))


def _squashed(screen) -> str:
    """Text with spaces removed — the rank line is letterspaced on purpose."""
    return _all_text(screen).replace(" ", "")


# ------------------------------------------------------------------ sprites


def test_two_pixels_share_one_terminal_cell():
    """The half-block trick: 24 pixel rows render as 12 cell rows."""
    sprite = parse_sprite(
        "# name: T\n# palette: k #112233  w #ffffff\n" + "\n".join(["kw" * 12] * 24)
    )
    assert (sprite.width, sprite.height) == (24, 24)
    assert sprite.cell_height == 12
    assert len(sprite_segments(sprite)) == 12


def test_a_transparent_pixel_paints_nothing():
    """Transparency is real, so a sprite sits on the card behind it."""
    sprite = parse_sprite("# name: T\n# palette: k #112233\n..\nkk")
    rows = sprite_segments(sprite)
    assert len(rows) == 1
    # Top row transparent, bottom solid -> lower half block, no background.
    for segment in rows[0]:
        assert segment.text == "▄"
        assert segment.style is not None and segment.style.bgcolor is None


def test_an_unpalletted_character_is_refused_not_guessed():
    with pytest.raises(SpriteError) as excinfo:
        parse_sprite("# name: T\n# palette: k #112233\nkkzz")
    assert "z" in str(excinfo.value)


def test_every_shipped_sprite_parses_and_is_canonical():
    files = sorted(sprites_dir().glob("*.px"))
    assert files, "no sprites shipped"
    for path in files:
        sprite = load_sprite(path)
        assert (sprite.width, sprite.height) == (24, 24), f"{path.name} is not 24x24"
        assert sprite.name, f"{path.name} has no name"
        colours = {px for row in sprite.rows for px in row if px}
        assert len(colours) >= 3, f"{path.name} is too flat to read"


# -------------------------------------------------------------------- text


def test_letterspacing_gives_way_rather_than_wrapping():
    # "A B C" is five columns, so five is exactly enough and four is not.
    assert letterspace("ABC", 5) == "A B C"
    assert letterspace("ABC", 4) == "ABC", "should not letterspace when it cannot fit"
    assert letterspace("ABC", 20) == "A B C"


def test_clip_never_exceeds_its_width():
    assert clip("a much longer line than fits", 10) == "a much lo…"
    assert len(clip("a much longer line than fits", 10)) == 10
    assert clip("short", 10) == "short"


# ------------------------------------------------------------------- screen


def test_the_roster_shows_a_card_for_every_character(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = RosterScreen("all")
        async with app.run_test(size=(172, 40)) as pilot:
            await pilot.pause()
            screen = app.screen
            cards = list(screen.query(WardenCard))
            expected = len(context.masters) + len(list(context.bosses))
            assert len(cards) == expected

            shown = _all_text(screen)
            for boss in context.bosses:
                assert boss.name in shown

    _run(journey())


def test_a_card_carries_the_boss_s_real_numbers(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = RosterScreen("wardens")
        async with app.run_test(size=(172, 40)) as pilot:
            await pilot.pause()
            shown = _all_text(app.screen)
            for boss in context.bosses:
                assert str(boss.boss_hp) in shown
                assert str(len(boss.phases)) in shown
            # Never fought, so no grade is claimed.
            assert "never" in shown

    _run(journey())


def test_the_card_changes_when_the_record_does(context):
    """The point of the stat block: it is a mirror, not decoration."""

    async def before():
        app = DsaQuestApp(context)
        app.pending_screen = RosterScreen("wardens")
        async with app.run_test(size=(172, 40)) as pilot:
            await pilot.pause()
            return _squashed(app.screen)

    async def after():
        app = DsaQuestApp(context)
        app.pending_screen = RosterScreen("wardens")
        async with app.run_test(size=(172, 40)) as pilot:
            await pilot.pause()
            return _squashed(app.screen)

    first = _run(before())
    assert "never" in first
    assert "SEALED" in first

    boss = next(iter(context.bosses))
    repo.record_boss_fight(
        context.conn, boss.id, won=True, grade="perfect", duration_ms=1000, hp_left=80, hints_used=0
    )
    context.conn.commit()

    second = _run(after())
    assert "PERFECT" in second, "a won fight must show its grade"
    assert "FELLED" in second, "a defeated boss must not still read as sealed"


def test_a_missing_sprite_keeps_the_frame(context):
    """Art lands over time; the layout must not move when it does."""
    absent = [b for b in context.bosses if not sprite_for(b.id).is_file()]
    if not absent:
        pytest.skip("every boss has art, so there is no missing case to test")

    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = RosterScreen("wardens")
        async with app.run_test(size=(172, 40)) as pilot:
            await pilot.pause()
            screen = app.screen
            heights = {c.data.identifier: c.size.height for c in screen.query(WardenCard)}
            assert len(set(heights.values())) == 1, (
                f"cards differ in height depending on whether art exists: {heights}"
            )

    _run(journey())


def test_the_home_screen_reaches_the_roster(context):
    async def journey():
        app = DsaQuestApp(context)
        async with app.run_test(size=(172, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            await pilot.press("c")
            await pilot.pause()
            assert isinstance(app.screen, RosterScreen)
            assert list(app.screen.query(WardenCard))
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

    _run(journey())


def test_the_roster_filters(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = RosterScreen("all")
        async with app.run_test(size=(172, 40)) as pilot:
            await pilot.pause()
            screen = app.screen

            await pilot.press("w")
            await pilot.pause()
            assert len(list(screen.query(WardenCard))) == len(list(context.bosses))

            await pilot.press("m")
            await pilot.pause()
            assert len(list(screen.query(WardenCard))) == len(context.masters)

    _run(journey())


def test_a_narrow_terminal_stacks_the_cards(context):
    async def one(width: int) -> int:
        app = DsaQuestApp(context)
        app.pending_screen = RosterScreen("wardens")
        async with app.run_test(size=(width, 40)) as pilot:
            await pilot.pause()
            return max(c.size.width for c in app.screen.query(WardenCard))

    narrow = _run(one(110))
    wide = _run(one(172))
    assert narrow > wide, "a single column should take the extra room, not waste it"


def test_no_markup_leaks_into_the_roster(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = RosterScreen("all")
        async with app.run_test(size=(172, 40)) as pilot:
            await pilot.pause()
            shown = _all_text(app.screen)
            for tag in LEAKED_MARKUP:
                assert tag not in shown, f"{tag} leaked into the roster as text"

    _run(journey())
