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
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..anim.render import render
from ..anim.scene import Animation
from .master import safe

THEATRE_CSS = """
TheatreScreen { background: #100f0d; }
#theatre-title { padding: 1 2 0 2; text-style: bold; }
#theatre-progress { padding: 0 2 1 2; }
#theatre-stage { padding: 1 2; margin: 0 2; border: round #38332b; height: auto; min-height: 12; }
#theatre-idiom { padding: 1 2 0 2; }
#theatre-caption { padding: 1 2; margin: 0 2 1 2; border-left: thick #d9a441; height: auto; }
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
        yield VerticalScroll(Static(id="theatre-stage"))
        yield Static(id="theatre-idiom")
        yield Vertical(Static(id="theatre-caption"))
        yield Footer()

    def on_mount(self) -> None:
        self.title = self.animation.title
        self.sub_title = self.animation.summary or "step through it"
        self.query_one("#theatre-title", Static).update(
            f"[b #ece5d6]{safe(self.animation.title)}[/]"
        )
        self.show()

    # ------------------------------------------------------------ rendering

    def show(self) -> None:
        frame = self.animation.frame(self.index)
        total = len(self.animation)

        filled = int(round((self.index + 1) / total * 28)) if total else 0
        state = "playing" if self.playing else "paused"
        self.query_one("#theatre-progress", Static).update(
            f"[#d9a441]{'█' * filled}[/][#3a352c]{'░' * (28 - filled)}[/]  "
            f"[#8a7f6d]frame {self.index + 1} of {total}   {state}   "
            f"x{1 / SPEEDS[self.speed]:.1f}[/]"
        )
        self.query_one("#theatre-stage", Static).update(render(frame.scene))
        self.query_one("#theatre-idiom", Static).update(
            f"[b #f0c14b]{safe(frame.idiom)}[/]" if frame.idiom else ""
        )
        self.query_one("#theatre-caption", Static).update(
            f"[#c8c0b0]{safe(frame.caption)}[/]"
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
