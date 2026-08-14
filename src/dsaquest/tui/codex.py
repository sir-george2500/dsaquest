"""The Codex — who the masters are, read at the player's own pace.

Optional by design. Nothing here is required to finish the game, and the
training never waits on it. What it does is answer a question the lessons
raise and cannot answer themselves: *why does this person teach like this*.

Locked chapters are listed and can be opened. Opening one shows its title and
what it costs, not its text — so a player who finds that Warden Korrin has a
chapter called "What she got wrong" learns that felling her guardian is what
buys it. Hiding locked chapters entirely would lose that pull, and would make
a Codex that is a sixth read look finished.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..art.sprite import load_sprite, sprite_text
from ..codex import Depth, depth_reached, load_lore, read_student
from .card import (
    BACK,
    BODY,
    FAINT,
    FRAME,
    GOLD,
    INK,
    MEASURE,
    MUTE,
    RULE,
    accent_for,
    clip,
)
from .master import safe
from .roster import sprite_for

#: The index column, wide and narrow. Wide enough for "Adjudicator Sevrin Kol"
#: and a count; narrow enough to leave the prose a measure worth reading.
WIDE_INDEX = 36
NARROW_INDEX = 26

#: What the column spends on itself before any text is drawn: a cell of
#: padding on each side, the rule down its right edge, and the two the
#: stable scrollbar gutter reserves whether or not it is scrolling.
INDEX_CHROME = 5

#: Below this the portrait is dropped. Chosen from the arithmetic rather than
#: taste: 28 cells of portrait plus a 36-cell index plus padding leaves twelve
#: for the name, and no name fits in twelve.
NARROW_AT = 100

CODEX_CSS = f"""
CodexScreen {{ background: {BACK}; }}
#codex-title {{ padding: 1 3 0 3; text-style: bold; }}
#codex-sub {{ padding: 0 3 1 3; color: {MUTE}; }}
#codex-body {{ layout: horizontal; height: 1fr; padding: 0 2; }}
/* The width and the rule belong to the scrolling container. On the inner
   Static they left the container at 1fr, so the rule was drawn 34 cells in
   and the portrait began forty cells further right, with nothing between. */
#codex-index {{
    width: {WIDE_INDEX}; height: 1fr; padding: 0 1; border-right: solid {RULE};
    scrollbar-gutter: stable;
}}
#codex-right {{ width: 1fr; height: 1fr; padding: 0 2; }}
#codex-head {{ layout: horizontal; height: 14; }}
#codex-portrait {{ width: 28; height: 14; border: round {FRAME}; padding: 0 1; }}
#codex-meta {{ width: 1fr; height: 14; padding: 0 0 0 3; }}
#codex-entry {{ padding: 1 0; height: auto; max-width: {MEASURE}; }}
/* The verdict is drawn above the chapter and only when there is one, so
   an empty rule never appears where a master has nothing to say. */
#codex-verdict {{
    padding: 1 2; margin: 1 0 0 0; height: auto; max-width: {MEASURE};
    border-left: outer {RULE};
}}

/* Below a hundred columns the portrait is not affordable. At eighty it left
   twelve cells for the master's name, which wrapped to one word a line —
   "Elder / Vhast / , the / Unhur / ried" — and pushed the creed off the
   screen entirely. The face is the first thing to go, because the words are
   what the Codex is for. */
CodexScreen.narrow #codex-index {{ width: {NARROW_INDEX}; }}
CodexScreen.narrow #codex-portrait {{ display: none; }}
CodexScreen.narrow #codex-head {{ height: auto; }}
CodexScreen.narrow #codex-meta {{ height: auto; padding: 0; }}
"""


class CodexScreen(Screen):
    """Browse the masters' stories, and what each has earned you the right to read."""

    BINDINGS = [
        Binding("escape", "leave", "Back"),
        Binding("down,j", "move(1)", "Next master"),
        Binding("up,k", "move(-1)", "Previous master"),
        Binding("right,l,enter", "next_entry(1)", "Next chapter"),
        Binding("left,h", "next_entry(-1)", "Previous chapter"),
    ]

    def __init__(self, master_id: str = "") -> None:
        super().__init__()
        self.master_index = 0
        self.entry_index = 0
        self._wanted = master_id

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="codex-title")
        yield Static(id="codex-sub")
        with Horizontal(id="codex-body"):
            with VerticalScroll(id="codex-index"):
                yield Static(id="codex-list")
            with Vertical(id="codex-right"):
                with Horizontal(id="codex-head"):
                    with Vertical(id="codex-portrait"):
                        yield Static(id="codex-sprite")
                    with Vertical(id="codex-meta"):
                        yield Static(id="codex-name")
                        yield Static("")
                        yield Static(id="codex-creed")
                yield VerticalScroll(
                    Static(id="codex-verdict"),
                    Static(id="codex-entry"),
                )
        yield Footer()

    # ------------------------------------------------------------- plumbing

    def on_mount(self) -> None:
        self.title = "THE CODEX"
        if self._wanted:
            for index, master_id in enumerate(self.masters()):
                if master_id == self._wanted:
                    self.master_index = index
                    break
        self.refresh_view()

    def on_resize(self, event) -> None:
        """The index and the titles inside it are sized to the terminal."""
        self.set_class(event.size.width < NARROW_AT, "narrow")
        self.refresh_view()

    @property
    def index_width(self) -> int:
        """How many cells a row of the index may actually use.

        Derived rather than measured: the widget's own ``container_size`` is a
        layout behind at the moment it is wanted — ``on_resize`` sets the class
        and redraws before Textual has re-laid the column out — so reading it
        gave the *previous* width and every row wrapped. Two cells over is not
        a small error here: a wrapped row puts its count on a line of its own,
        and the eleven-master list becomes twenty-two.
        """
        width = NARROW_INDEX if self.has_class("narrow") else WIDE_INDEX
        return width - INDEX_CHROME

    def action_leave(self) -> None:
        self.app.pop_screen()
        home = self.app.screen
        if hasattr(home, "refresh_view"):
            home.refresh_view()

    def masters(self) -> list[str]:
        """Masters with a story, in road order so the Codex reads as a journey."""
        from ..journey import load_chapters

        lore = load_lore()
        ordered = [c.master for c in load_chapters().chapters if c.master in lore]
        ordered += [m for m in sorted(lore) if m not in ordered]
        return ordered

    @property
    def current_master(self) -> str:
        masters = self.masters()
        return masters[self.master_index % len(masters)] if masters else ""

    def action_move(self, delta: int) -> None:
        masters = self.masters()
        if not masters:
            return
        self.master_index = (self.master_index + delta) % len(masters)
        self.entry_index = 0
        self.refresh_view()

    def action_next_entry(self, delta: int) -> None:
        entries = self.entries()
        if not entries:
            return
        self.entry_index = (self.entry_index + delta) % len(entries)
        self.refresh_view()

    def entries(self):
        """Every chapter this master has, locked ones included.

        Locked chapters are navigable on purpose — opening one is how the
        player finds out what it would take to read it.
        """
        master_id = self.current_master
        lore = load_lore().get(master_id) if master_id else None
        return lore.entries if lore else ()

    def readable(self):
        master_id = self.current_master
        if not master_id:
            return ()
        lore = load_lore().get(master_id)
        if lore is None:
            return ()
        return lore.visible_entries(depth_reached(self.app.context, master_id))

    # ------------------------------------------------------------ rendering

    def refresh_view(self) -> None:
        context = self.app.context
        lore_by_master = load_lore()
        masters = self.masters()
        if not masters:
            self.query_one("#codex-title", Static).update(f"[b {INK}]THE CODEX[/]")
            self.query_one("#codex-list", Static).update(
                f"[{FAINT}]No master has a story written yet.[/]"
            )
            return

        master_id = self.current_master
        lore = lore_by_master[master_id]
        reached = depth_reached(context, master_id)
        master = context.masters.get(master_id)
        accent = accent_for(master_id)

        total_read = sum(
            len(lore_by_master[m].visible_entries(depth_reached(context, m))) for m in masters
        )
        total_all = sum(len(lore_by_master[m].entries) for m in masters)
        self.query_one("#codex-title", Static).update(f"[b {INK}]THE CODEX[/]")
        self.query_one("#codex-sub", Static).update(
            f"[{MUTE}]{total_read} of {total_all} chapters earned   ·   ↑↓ master   ←→ chapter[/]"
        )

        self.query_one("#codex-list", Static).update(self._index(context, lore_by_master, masters))

        path = sprite_for(master_id)
        self.query_one("#codex-sprite", Static).update(
            sprite_text(load_sprite(path)) if path.is_file() else ""
        )
        self.query_one("#codex-name", Static).update(
            f"[b {INK}]{safe(master.title if master else master_id)}[/]\n"
            f"[{accent}]{safe(lore.epithet)}[/]"
            + (f"\n[{FAINT}]{safe(lore.clan)}[/]" if lore.clan else "")
        )
        self.query_one("#codex-creed", Static).update(
            f'[i {BODY}]"{safe(lore.creed)}"[/]' if lore.creed else ""
        )

        verdict = self.query_one("#codex-verdict", Static)
        spoken = self.verdict_text(master_id, accent)
        verdict.update(spoken)
        # An empty Static still draws its rule and its padding, which would put
        # a bare vertical line above the chapter of every master who has not
        # watched the player work yet.
        verdict.display = bool(spoken)
        self.query_one("#codex-entry", Static).update(self.entry_text(lore, reached))

    def verdict_text(self, master_id: str, accent: str) -> str:
        """What this master currently sees in the player, if anything.

        Shown here because a story nobody acts on is decoration. The same
        reading is what the master speaks during training; this is the page
        where you can go and ask them what they think, deliberately, rather
        than waiting to be told mid-lesson.

        Nothing is drawn when there is no verdict. An empty panel headed "what
        he sees in you" would be worse than the absence — it reads as a master
        withholding, when in fact they have not watched you work yet.
        """
        reading = read_student(self.app.context, master_id)
        if reading is None:
            return ""
        return (
            f"[{accent}]WHAT THEY SEE IN YOU[/]\n\n"
            f"[i {BODY}]{safe(reading.line)}[/]\n\n"
            f"[{FAINT}]on {safe(reading.diagnosis.pattern_id)}, "
            f"over {reading.diagnosis.evidence} attempts[/]"
        )

    def _index(self, context, lore_by_master, masters: list[str]) -> str:
        """The masters, and the chapters of whichever is open.

        One line per master rather than two: eleven masters at two lines each
        pushed the open master's chapters off the bottom of an eighty-column
        terminal, which is precisely the part the player came here to read.
        """
        rows: list[str] = []
        entries = self.entries()
        # Two columns inside the index: the name, and a right-aligned count or
        # seal. Ragged, the seals wandered four cells either side of each other
        # and the column stopped reading as a column.
        column = self.index_width
        for index, other in enumerate(masters):
            other_lore = lore_by_master[other]
            read = len(other_lore.visible_entries(depth_reached(context, other)))
            whole = len(other_lore.entries)
            who = context.masters.get(other)
            label = who.title.split(",")[0] if who else other
            selected = index == self.master_index % len(masters)
            style = accent_for(other) if selected else (MUTE if read > 1 else FAINT)
            marker = "▾" if selected else " "
            count = f"{read}/{whole}"
            label = clip(label, column - len(count) - 3)
            gap = max(1, column - len(label) - len(count) - 2)
            rows.append(f"[{style}]{marker} {safe(label)}[/]{' ' * gap}[{FAINT}]{count}[/]")

            if not selected:
                continue
            for position, entry in enumerate(entries):
                open_here = position == self.entry_index % len(entries)
                unlocked = entry.visible(depth_reached(context, other))
                mark = "▸" if open_here else " "
                if unlocked:
                    entry_style = f"b {GOLD}" if open_here else BODY
                else:
                    entry_style = MUTE if open_here else FAINT
                # Four of indent, the marker and its space, and the seal:
                # seven cells spoken for before the title gets any.
                title = clip(entry.title, column - 8)
                gap = max(1, column - len(title) - 7)
                seal = f"{' ' * gap}[{FAINT}]×[/]" if not unlocked else ""
                rows.append(f"    [{entry_style}]{mark} {safe(title)}[/]{seal}")
        return "\n".join(rows)

    def entry_text(self, lore, reached: Depth) -> str:
        entries = lore.entries
        if not entries:
            return f"[{FAINT}]Nothing yet. Train under them and come back.[/]"

        entry = entries[self.entry_index % len(entries)]
        blocks = [f"[b {INK}]{safe(entry.title)}[/]", ""]

        if entry.visible(reached):
            # The YAML folds each paragraph onto one line, so a single newline
            # is a paragraph break. Rendered as-is they ran together into a
            # wall; a blank line between them is the whole of the fix.
            body = "\n\n".join(p.strip() for p in entry.text.split("\n") if p.strip())
            blocks.append(f"[{BODY}]{safe(body)}[/]")
        else:
            blocks += [
                f"[{FAINT}]Sealed.[/]",
                "",
                f"[{MUTE}]{_needed(entry.depth)}[/]",
            ]

        if lore.relationships and reached >= Depth.TRAINED:
            blocks += ["", f"[{FAINT}]{'─' * 40}[/]", "", f"[{MUTE}]ON THE OTHERS[/]", ""]
            for relationship in lore.relationships:
                blocks.append(f"[i {BODY}]{safe(relationship.line)}[/]\n")

        return "\n".join(blocks)


def _needed(depth: Depth) -> str:
    """What buys this chapter, said as an instruction rather than a state."""
    return {
        Depth.MET: "",
        Depth.TRAINED: "Hold every one of their secrets to read this.",
        Depth.TESTED: "Pass their final test to read this.",
        Depth.FELLED: "Fell their guardian to read this.",
        Depth.PERFECT: "Fell their guardian without being touched to read this.",
    }.get(depth, "")
