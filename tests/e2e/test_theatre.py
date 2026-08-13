"""The theatre: watching a concept before being tested on it.

The engine's job is that a frame cannot contradict the one before it. Authors
write *steps*, not pictures, and the frames are folded from them — so a sliding
window whose left pointer jumps backwards is not something an author can write
by accident. Most of these tests are about that, and about the errors an author
gets when they do write something impossible, because a script is a hundred
lines of YAML and an unhelpful error is what makes people stop writing them.
"""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Static

from dsaquest.anim.scene import ArrayScene, Mark
from dsaquest.anim.script import ScriptError, build_animation
from dsaquest.content.animations import animation_for, load_animations
from dsaquest.context import build
from dsaquest.tui.app import DsaQuestApp
from dsaquest.tui.theatre import TheatreScreen

LEAKED_MARKUP = ("[/]", "[b]", "[dim]", "[green]", "[red]", "[b green]", "[#d9a441]")


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


def _script(**over):
    base = {
        "id": "t",
        "kind": "array",
        "data": [1, 2, 3],
        "steps": [
            {"say": "start", "point": {"l": 0}},
            {"say": "move", "move": {"l": 1}},
        ],
    }
    base.update(over)
    return base


# ------------------------------------------------------------------ engine


def test_a_step_changes_only_what_it_names():
    """The fold: everything not mentioned carries forward untouched."""
    animation = build_animation(
        _script(
            steps=[
                {"say": "one", "point": {"l": 0}, "mark": {0: "in"}, "note": "n = 1"},
                {"say": "two", "point": {"r": 2}},
            ]
        )
    )
    first, second = animation.frames
    assert isinstance(second.scene, ArrayScene)
    assert second.scene.marks[0] is Mark.IN, "the mark from step one survived"
    assert second.scene.note == "n = 1", "the note survived"
    assert dict(second.scene.pointers) == {"l": 0, "r": 2}
    assert dict(first.scene.pointers) == {"l": 0}


def test_a_pointer_cannot_leave_the_array():
    with pytest.raises(ScriptError) as excinfo:
        build_animation(_script(steps=[{"say": "off", "point": {"l": 9}}]))
    assert "step 1" in str(excinfo.value)
    assert "outside the array" in str(excinfo.value)


def test_a_pointer_cannot_be_moved_before_it_is_placed():
    with pytest.raises(ScriptError) as excinfo:
        build_animation(_script(steps=[{"say": "drift", "move": {"l": 1}}]))
    assert "never placed" in str(excinfo.value)


def test_a_span_cannot_run_backwards():
    with pytest.raises(ScriptError) as excinfo:
        build_animation(_script(steps=[{"say": "bad", "span": [2, 0]}]))
    assert "backwards" in str(excinfo.value)


def test_a_frame_with_nothing_to_say_is_refused():
    """A picture with no explanation teaches nothing."""
    with pytest.raises(ScriptError) as excinfo:
        build_animation(_script(steps=[{"point": {"l": 0}}]))
    assert "no 'say'" in str(excinfo.value)


def test_an_unknown_key_is_refused_rather_than_ignored():
    """Silently dropping a misspelled key would lose the author's intent."""
    with pytest.raises(ScriptError) as excinfo:
        build_animation(_script(steps=[{"say": "x", "poimt": {"l": 0}}]))
    assert "poimt" in str(excinfo.value)


def test_every_problem_is_reported_at_once():
    """One error per run makes fixing a long script a hundred round trips."""
    with pytest.raises(ScriptError) as excinfo:
        build_animation(
            _script(
                steps=[
                    {"say": "a", "point": {"l": 9}},
                    {"say": "b", "span": [5, 6]},
                    {"mark": {0: "nonsense"}},
                ]
            )
        )
    assert len(excinfo.value.problems) >= 3


# ----------------------------------------------------------------- content


def test_the_shipped_animations_all_build():
    animations = load_animations()
    assert animations, "no animations shipped"
    for animation in animations.values():
        assert len(animation) >= 3, f"{animation.id} is too short to be worth watching"
        assert all(f.caption for f in animation.frames)


def test_the_window_animation_only_ever_moves_its_left_pointer_right():
    """The property the whole pattern rests on, asserted against the picture.

    If the animation contradicted the algorithm here, a student would watch a
    window that cannot exist and believe it. This is the check that an authored
    sequence of whole frames could not have given us.
    """
    animation = animation_for("window-invariant")
    assert animation is not None

    lefts = [dict(f.scene.pointers).get("l") for f in animation.frames]
    seen = [x for x in lefts if x is not None]
    assert seen == sorted(seen), f"l moved backwards: {seen}"

    rights = [dict(f.scene.pointers).get("r") for f in animation.frames]
    seen_r = [x for x in rights if x is not None]
    assert seen_r == sorted(seen_r), f"r moved backwards: {seen_r}"


# ------------------------------------------------------------------ screen


def test_the_theatre_opens_paused_on_the_first_frame(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = TheatreScreen(animation_for("window-invariant"))
        async with app.run_test(size=(96, 34)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert screen.index == 0
            assert not screen.playing, "it must not start running before you have read it"
            assert "frame 1 of" in str(screen.query_one("#theatre-progress", Static).visual)

    _run(journey())


def test_stepping_forwards_and_back(context):
    """Going back is the point — you sit on the frame you did not follow."""

    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = TheatreScreen(animation_for("window-invariant"))
        async with app.run_test(size=(96, 34)) as pilot:
            await pilot.pause()
            screen = app.screen
            for _ in range(3):
                await pilot.press("right")
                await pilot.pause()
            assert screen.index == 3
            await pilot.press("left")
            await pilot.pause()
            assert screen.index == 2
            # And it clamps rather than wrapping.
            for _ in range(10):
                await pilot.press("left")
                await pilot.pause()
            assert screen.index == 0

    _run(journey())


def test_playing_stops_at_the_end_rather_than_looping(context):
    """Autoplay runs out rather than going round. A loop invites watching.

    Pressing play *at* the last frame is a different thing and deliberately
    restarts, so that the key never looks dead — both are asserted here,
    because the two nearly-identical behaviours are easy to conflate.
    """

    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = TheatreScreen(animation_for("window-invariant"))
        async with app.run_test(size=(96, 34)) as pilot:
            await pilot.pause()
            screen = app.screen
            last = len(screen.animation) - 1

            # Autoplay arriving at the end: it stops there.
            screen.index = last - 1
            screen.play()
            assert screen.playing
            screen.tick()
            await pilot.pause()
            assert screen.index == last
            screen.tick()
            await pilot.pause()
            assert screen.index == last, "it went round"
            assert not screen.playing, "autoplay must run out at the end"

            # Pressing play while sitting on the last frame: start again.
            screen.play()
            await pilot.pause()
            assert screen.index == 0
            assert screen.playing
            screen.pause()

    _run(journey())


def test_the_caption_and_the_picture_move_together(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = TheatreScreen(animation_for("window-invariant"))
        async with app.run_test(size=(96, 34)) as pilot:
            await pilot.pause()
            screen = app.screen
            first = str(screen.query_one("#theatre-caption", Static).visual)
            await pilot.press("right")
            await pilot.pause()
            second = str(screen.query_one("#theatre-caption", Static).visual)
            assert first != second
            assert screen.animation.frame(1).caption[:30] in second

    _run(journey())


def test_no_markup_leaks_into_the_theatre(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = TheatreScreen(animation_for("window-invariant"))
        async with app.run_test(size=(96, 34)) as pilot:
            await pilot.pause()
            screen = app.screen
            shown = "\n".join(str(s.visual) for s in screen.query(Static))
            for _ in range(4):
                await pilot.press("right")
                await pilot.pause()
                shown += "\n" + "\n".join(str(s.visual) for s in screen.query(Static))
            for tag in LEAKED_MARKUP:
                assert tag not in shown, f"{tag} leaked into the theatre as text"
            # The idiom is C++ and full of subscripts.
            assert "freq[a[l]]" in shown

    _run(journey())
