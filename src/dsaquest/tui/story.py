"""The story — where the game starts.

Six beats explaining what this place is and what it will ask of you, read at
your own pace. It exists because the product's premise is unusual enough to
need stating: a learner who can already solve problems, and cannot recognise
them. Dropping someone straight into a drill leaves them to infer that from
the mechanics, and most will infer something else.

It is shown once, on a profile that has never played, and is reachable
afterwards from `s`. Read once and never again is the right default for a
prologue; unreachable afterwards is not, because the one person who wants to
re-read it is the person who came back after a month away.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..art.sprite import load_sprite, sprite_text
from ..content.loader import ContentError
from ..content.paths import content_root
from .master import safe

STORY_CSS = """
StoryScreen { background: #0d0c0a; }
#story-chapter { padding: 1 3 0 3; color: #6b6459; }
#story-title { padding: 0 3 1 3; text-style: bold; }
/* 1fr, not auto: an auto row grows past the screen, the screen sprouts its
   own scrollbar, and the chapter and title scroll off the top while looking
   for all the world like they were never rendered. The inner VerticalScroll
   is what should absorb a long beat. */
#story-mid { layout: horizontal; height: 1fr; padding: 0 2; }
#story-art { width: 30; height: 14; padding: 0 1; }
#story-text { width: 1fr; padding: 0 2; height: auto; }
#story-mid VerticalScroll { width: 1fr; height: 1fr; }
#story-progress { padding: 1 3; color: #6b6459; }
"""


@dataclass(frozen=True, slots=True)
class Beat:
    id: str
    title: str
    text: str
    art: str = ""


@dataclass(frozen=True, slots=True)
class Story:
    id: str
    title: str
    beats: tuple[Beat, ...]

    def __len__(self) -> int:
        return len(self.beats)


def story_dir() -> Path:
    return content_root() / "story"


@cache
def load_story(name: str = "prologue") -> Story | None:
    """Read a story, or None if none is authored. Never raises on absence."""
    path = story_dir() / f"{name}.yaml"
    if not path.is_file():
        return None

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    beats = raw.get("beats") or []
    problems = [
        f"beat {index}: no {field!r}"
        for index, beat in enumerate(beats, start=1)
        for field in ("id", "title", "text")
        if not str(beat.get(field, "")).strip()
    ]
    if not beats:
        problems.append("no beats, so there is no story")
    if problems:
        raise ContentError([f"{path.name}: {problem}" for problem in problems])

    return Story(
        id=str(raw.get("id", name)),
        title=str(raw.get("title", name)),
        beats=tuple(
            Beat(
                id=str(b["id"]),
                title=str(b["title"]),
                text=str(b["text"]).strip(),
                art=str(b.get("art", "")),
            )
            for b in beats
        ),
    )


class StoryScreen(Screen):
    """Read the prologue, one beat at a time."""

    BINDINGS = [
        Binding("space", "next", "Continue"),
        Binding("right", "next", "", show=False),
        Binding("left", "back", "Back"),
        Binding("escape", "leave", "Skip"),
    ]

    def __init__(self, story: Story, *, on_finish=None) -> None:
        super().__init__()
        self.story = story
        self.index = 0
        self._on_finish = on_finish

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="story-chapter")
        yield Static(id="story-title")
        with Horizontal(id="story-mid"):
            with Vertical(id="story-art"):
                yield Static(id="story-sprite")
            yield VerticalScroll(Static(id="story-text"))
        yield Static(id="story-progress")
        yield Footer()

    def on_mount(self) -> None:
        self.title = self.story.title
        self.show()

    def show(self) -> None:
        beat = self.story.beats[self.index]
        self.query_one("#story-chapter", Static).update(
            f"[#6b6459]{' '.join(self.story.title.upper())}[/]"
        )
        self.query_one("#story-title", Static).update(f"[b #ece5d6]{safe(beat.title)}[/]")

        sprite_panel = self.query_one("#story-sprite", Static)
        art = self.sprite_for_beat(beat)
        sprite_panel.display = art is not None
        self.query_one("#story-art", Vertical).display = art is not None
        if art is not None:
            sprite_panel.update(art)

        self.query_one("#story-text", Static).update(f"[#c8c0b0]{safe(beat.text)}[/]")

        last = self.index == len(self.story) - 1
        keys = "space — begin" if last else "space — on   ← back   esc — skip"
        self.query_one("#story-progress", Static).update(
            f"[#d9a441]{'●' * (self.index + 1)}[/]"
            f"[#3a352c]{'○' * (len(self.story) - self.index - 1)}[/]   [#6b6459]{keys}[/]"
        )

    def sprite_for_beat(self, beat: Beat):
        if not beat.art:
            return None
        path = content_root().parent / "assets" / "sprites" / f"{beat.art}.px"
        if not path.is_file():
            return None
        return sprite_text(load_sprite(path))

    def action_next(self) -> None:
        if self.index + 1 < len(self.story):
            self.index += 1
            self.show()
            return
        self.finish()

    def action_back(self) -> None:
        if self.index:
            self.index -= 1
            self.show()

    def action_leave(self) -> None:
        self.finish()

    def finish(self) -> None:
        self.app.pop_screen()
        if self._on_finish is not None:
            self._on_finish()
