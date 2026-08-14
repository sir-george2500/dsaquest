"""The theatre — where a concept is watched before it is tested.

The student drives. It opens paused on frame one, and stepping backwards costs
nothing: the whole point is to sit on the frame you did not follow and go back
over it, which an animation that only plays forwards will not let you do.

Autoplay exists because sometimes you want the rhythm rather than the detail —
a sliding window *breathing* is a different thing from six still pictures of a
window — but it stops at the end rather than looping. A loop invites watching
instead of thinking.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..anim.render import render
from ..anim.scene import Animation
from .card import BACK, BODY, FRAME, GOLD, INK, MEASURE, MUTE, gauge
from .master import safe

THEATRE_CSS = f"""
TheatreScreen {{ background: {BACK}; }}
#theatre-title {{ padding: 1 2 0 2; text-style: bold; }}
#theatre-progress {{ padding: 0 2 1 2; }}
#theatre-stage {{
    padding: 1 2; margin: 0 2; border: round {FRAME}; height: auto; min-height: 12;
    max-width: {MEASURE + 6};
}}
#theatre-scroll {{ height: 1fr; scrollbar-gutter: stable; }}
/* The idiom and the caption are one block behind one accent bar. They are two
   statements about the same frame and they were set as two widgets on two left
   edges — the idiom at column two, outside the bar, and the caption at column
   five inside it. */
#theatre-caption {{
    padding: 1 2; margin: 1 2; border-left: outer {GOLD}; height: auto;
    max-width: {MEASURE + 6};
}}
"""

#: Seconds per frame at each speed. Slow first: the default should be a pace you
#: can read at, not one that looks impressive.
SPEEDS = (1.6, 1.0, 0.6, 0.35)
DEFAULT_SPEED = 1


class TheatreScreen(Screen):
    """Play, step and scrub one concept animation."""

    BINDINGS = [
        Binding("space", "toggle", "Play/pause"),
        Binding("right", "step(1)", "Next"),
        Binding("left", "step(-1)", "Back"),
        Binding("home", "first", "First", show=False),
        Binding("end", "last", "Last", show=False),
        Binding("r", "first", "Restart"),
        Binding("plus,equals_sign,equal", "faster", "Faster", show=False),
        Binding("minus", "slower", "Slower", show=False),
        Binding("escape", "leave", "Back"),
    ]

    def __init__(self, animation: Animation) -> None:
        super().__init__()
        self.animation = animation
        self.index = 0
        self.playing = False
        self.speed = DEFAULT_SPEED
        self._ticker = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="theatre-title")
        yield Static(id="theatre-progress")
        # The caption scrolls with the picture it captions. Outside the scroll
        # it was pushed to the bottom of the terminal, so at forty rows there
        # were seven blank rows between the frame and the sentence explaining
        # it, and the two stopped reading as one thing.
        yield VerticalScroll(
            Static(id="theatre-stage"),
            Static(id="theatre-caption"),
            id="theatre-scroll",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.title = self.animation.title
        self.sub_title = self.animation.summary or "step through it"
        self.query_one("#theatre-title", Static).update(f"[b {INK}]{safe(self.animation.title)}[/]")
        self.show()

    # ------------------------------------------------------------ rendering

    def show(self) -> None:
        frame = self.animation.frame(self.index)
        total = len(self.animation)

        # Five raw hex values used to live on this screen — `#3a352c`, `#f0c14b`
        # and `#c8c0b0` are not in the palette at all, they are a near-FRAME,
        # a near-GOLD and a near-BODY invented here. A gold that is four points
        # off the gold on every other screen does not read as a highlight, it
        # reads as a rendering fault.
        state = "playing" if self.playing else "paused"
        self.query_one("#theatre-progress", Static).update(
            f"{gauge((self.index + 1) / total if total else 0, 28, GOLD)}  "
            f"[{MUTE}]frame {self.index + 1} of {total}   {state}   "
            f"x{1 / SPEEDS[self.speed]:.1f}[/]"
        )
        self.query_one("#theatre-stage", Static).update(render(frame.scene))
        idiom = f"[b {GOLD}]{safe(frame.idiom)}[/]\n\n" if frame.idiom else ""
        self.query_one("#theatre-caption", Static).update(
            f"{idiom}[{BODY}]{safe(frame.caption)}[/]"
        )

    # ------------------------------------------------------------- controls

    def action_step(self, delta: int) -> None:
        self.pause()
        self.index = max(0, min(self.index + delta, len(self.animation) - 1))
        self.show()

    def action_first(self) -> None:
        self.pause()
        self.index = 0
        self.show()

    def action_last(self) -> None:
        self.pause()
        self.index = len(self.animation) - 1
        self.show()

    def action_toggle(self) -> None:
        if self.playing:
            self.pause()
        else:
            self.play()
        self.show()

    def action_faster(self) -> None:
        self.speed = min(self.speed + 1, len(SPEEDS) - 1)
        if self.playing:
            self.play()
        self.show()

    def action_slower(self) -> None:
        self.speed = max(self.speed - 1, 0)
        if self.playing:
            self.play()
        self.show()

    def play(self) -> None:
        # Playing from the last frame restarts, so the key never looks dead.
        if self.index >= len(self.animation) - 1:
            self.index = 0
        self.pause()
        self.playing = True
        self._ticker = self.set_interval(SPEEDS[self.speed], self.tick)

    def pause(self) -> None:
        self.playing = False
        if self._ticker is not None:
            self._ticker.stop()
            self._ticker = None

    def tick(self) -> None:
        if self.index >= len(self.animation) - 1:
            self.pause()
            self.show()
            return
        self.index += 1
        self.show()

    def action_leave(self) -> None:
        self.pause()
        self.app.pop_screen()
