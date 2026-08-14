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
from textual.widgets import Footer, Header, Input, Static

from ..art.sprite import load_sprite, sprite_text
from ..content.loader import ContentError
from ..content.paths import content_root
from ..storage import repositories as repo
from .card import BACK, BODY, CARD_BACK, FAINT, FRAME, GOLD, INK, MEASURE, MUTE
from .master import safe

#: One left edge at column 4, and a bounded reading measure.
#:
#: The prologue used to be a top-anchored strip of text over an empty screen:
#: `#story-mid` took `1fr`, so at forty rows the naming input sat twenty rows
#: below the sentence that asked for the name, alone at the bottom of a void.
#: The beat is now a block that grows with its content, and the whole
#: composition is centred vertically — a prologue is a page, not a dashboard.
STORY_CSS = f"""
StoryScreen {{ background: {BACK}; align-vertical: middle; }}
#story-chapter {{ padding: 0 4; color: {FAINT}; }}
#story-title {{ padding: 0 4 1 4; text-style: bold; color: {INK}; }}
#story-mid {{ layout: horizontal; height: auto; max-height: 1fr; padding: 0 2; }}
#story-art {{ width: 28; height: 14; padding: 0 1; }}
#story-text {{ width: 1fr; padding: 0 2; height: auto; max-width: {MEASURE}; }}
#story-mid VerticalScroll {{ width: 1fr; height: auto; max-height: 100%; }}
/* The field sits directly under the sentence that asks for a name, in the
   text column's own left edge, with a prompt beside it. */
/* Height three and no padding of its own: Textual's Input reserves a row for a
   `tall` border it no longer has, and the leftover row rendered as a slab of
   card-back sitting a row below and a column left of the box — a shadow the
   design does not have. */
#story-name {{
    margin: 0 4; width: 34; height: 3; padding: 0 1;
    border: round {FRAME}; background: {CARD_BACK};
}}
#story-name:focus {{ border: round {GOLD}; }}
#story-ask {{ padding: 1 4 0 4; color: {MUTE}; }}
#story-progress {{ padding: 1 4 0 4; color: {FAINT}; }}
"""


def paragraphs(text: str) -> str:
    """One blank line between the author's lines.

    The prologue is written a thought to a line, and each thought is two or
    three lines long once wrapped. Rendered with the author's single breaks the
    beat came out as one solid block of eight lines with three ragged right
    edges inside it and nothing marking where one thought ended and the next
    began — the hardest thing on the screen to read, on the screen whose only
    job is to be read. This is presentation, not content: the file still holds
    one line per thought.
    """
    return "\n\n".join(line.strip() for line in text.split("\n") if line.strip())


@dataclass(frozen=True, slots=True)
class Beat:
    id: str
    title: str
    text: str
    art: str = ""
    ask_name: bool = False
    """This beat asks the player what to call themselves."""


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
                ask_name=bool(b.get("ask_name", False)),
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
        # The field is prefilled with the legend's name, so its placeholder is
        # never seen and the box arrived unlabelled — a bordered rectangle with
        # a word already in it, and no statement of what it wanted.
        yield Static(id="story-ask")
        yield Input(placeholder="your name", id="story-name")
        yield Static(id="story-progress")
        yield Footer()

    def on_mount(self) -> None:
        self.title = self.story.title
        self.show()

    def show(self) -> None:
        beat = self.story.beats[self.index]
        self.query_one("#story-chapter", Static).update(
            f"[{FAINT}]{' '.join(self.story.title.upper())}[/]"
        )
        self.query_one("#story-title", Static).update(f"[b {INK}]{safe(beat.title)}[/]")

        sprite_panel = self.query_one("#story-sprite", Static)
        art = self.sprite_for_beat(beat)
        sprite_panel.display = art is not None
        self.query_one("#story-art", Vertical).display = art is not None
        if art is not None:
            sprite_panel.update(art)

        hero = repo.warrior_name(self.app.context.conn)
        text = beat.text.replace("{hero}", hero)
        self.query_one("#story-text", Static).update(f"[{BODY}]{safe(paragraphs(text))}[/]")

        # The naming beat shows an input and nothing else does. Prefilled with
        # the legend's name, so a player who does not care can simply press on
        # and still be somebody.
        field = self.query_one("#story-name", Input)
        field.display = beat.ask_name
        ask = self.query_one("#story-ask", Static)
        ask.display = beat.ask_name
        if beat.ask_name:
            # Uncoloured, so the rule above decides. Written FAINT here it
            # overrode its own stylesheet and the only interactive thing on the
            # beat was the dimmest text on it.
            ask.update("WHAT ARE YOU CALLED")
        if beat.ask_name:
            if not field.value:
                field.value = hero
            self.set_timer(0.05, field.focus)

        last = self.index == len(self.story) - 1
        if beat.ask_name:
            # Space belongs to the field here — names contain spaces — so the
            # key that moves on has to change, and has to say so.
            keys = "enter — that is my name"
        elif last:
            keys = "space — begin"
        else:
            keys = "space — on   ← back   esc — skip"
        self.query_one("#story-progress", Static).update(
            f"[{GOLD}]{'●' * (self.index + 1)}[/]"
            f"[{FRAME}]{'○' * (len(self.story) - self.index - 1)}[/]   [{FAINT}]{keys}[/]"
        )

    def sprite_for_beat(self, beat: Beat):
        if not beat.art:
            return None
        path = content_root().parent / "assets" / "sprites" / f"{beat.art}.px"
        if not path.is_file():
            return None
        return sprite_text(load_sprite(path))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_next()

    def remember_name(self) -> None:
        beat = self.story.beats[self.index]
        if not beat.ask_name:
            return
        chosen = self.query_one("#story-name", Input).value.strip()
        if chosen:
            conn = self.app.context.conn
            repo.set_setting(conn, "warrior_name", chosen[:24])
            conn.commit()

    def action_next(self) -> None:
        self.remember_name()
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
        self.remember_name()
        self.finish()

    def finish(self) -> None:
        self.app.pop_screen()
        if self._on_finish is not None:
            self._on_finish()
