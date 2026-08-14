"""The warden card — a pixel portrait and a dossier, side by side.

The layout is the one from the design reference: a framed portrait on the left,
a letterspaced rank line, a display name, a domain in the character's accent
colour, a rule, a one-line description, a two-by-two stat block, and a pulled
quote against an accent bar.

Two decisions worth stating.

**The stats are real.** Every value on a card comes from content or from the
save file — hit points, tier, phase count, times fought, secrets held. It would
have been easy to invent "STANCE: Immovable Ox" to match the reference exactly,
and it would have made the card decorative. A card that shows you your own
record is worth looking at twice; a card that shows you flavour text is not.

**Letterspacing is adaptive.** The rank line is set with a space between every
character, which is what gives it the small-caps feel — but that doubles its
width, and at a narrow card it wraps and looks broken. So it is letterspaced
only when it fits, and set plainly when it does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.theme import Theme
from textual.widgets import Static

from ..art.sprite import load_sprite, sprite_text

#: Canonical sprite size, plus its frame border and padding.
SPRITE_COLS = 24
FRAME_W = SPRITE_COLS + 4
FRAME_H = SPRITE_COLS // 2 + 2

#: The palette. Warm near-black, one ink, three greys, and a per-card accent.
#:
#: Every screen imports these rather than typing hex. Before this was enforced
#: each screen had invented its own greys — the home screen's road used
#: ``#4a453d`` for "sealed" while the arena used ``#3a352c`` for a spent blow
#: and the story used ``#3a352c`` for an unread dot, three near-identical
#: values doing the same job under three names.
BACK = "#100f0d"
CARD_BACK = "#15140f"
RULE = "#2b2822"
FRAME = "#38332b"
INK = "#ece5d6"
MUTE = "#8a7f6d"
FAINT = "#6b6459"
BODY = "#a89e8d"
VALUE = "#cfc7b8"

#: The three state colours. One green, one red, one dead grey, used for every
#: pass/fail/locked mark in the game.
GOOD = "#6fae7f"
BAD = "#c04a3a"
SEALED = "#4a453d"
GOLD = "#d9a441"

#: The one cool colour. It is already the theme's ``secondary``, the accent for
#: the search warden and for the graphs master, and the settled-cell blue in the
#: animation renderer — four places that each spelled a blue of their own.
COOL = "#7f9fd9"

#: A guardian you can reach but have not felled. Warmer than SEALED and much
#: quieter than GOLD, so a boss's name sits behind the chapter that names it
#: instead of shouting over it. It lived as a bare ``#7a5c4a`` in the home
#: screen's road, the last invented colour left outside this file.
EMBER = "#7a5c4a"

#: The reading measure. Prose set wider than this is a wall: at 160 columns an
#: unconstrained paragraph runs 150 characters and the eye loses its place
#: returning to the left edge. Panels stay full width; the text inside them
#: does not.
MEASURE = 78

#: One saturated colour per character, carrying their identity across every
#: screen they appear on. Kept in code rather than content because it is a
#: presentation choice, not something a content author should have to pick.
ACCENTS: dict[str, str] = {
    "the-array-beast": "#d9a441",
    "the-search-warden": "#7f9fd9",
    "the-thirty-two": "#5fd7c0",
    "master_arrays": "#d9a441",
    "master_bits": "#5fd7c0",
    "master_search": "#7f9fd9",
    "master_greed": "#b08ad9",
    "master_trees": "#6fae7f",
    "master_strings": "#c0705f",
    "master_graphs": "#7f9fd9",
    "master_dp": "#9d7ad9",
    "master_math": "#e8d8a0",
    "master_structures": "#8fa3c4",
    "master_foundations": "#d9a441",
    # A boss takes its master's colour: it is the region's own thing, and the
    # player should feel they are still in the Ridge of Greed when they meet it.
    "the-exchange": "#b08ad9",
    "the-rootless": "#6fae7f",
    "the-unread-line": "#c0705f",
    "the-unweighted-lie": "#7f9fd9",
    "the-elite-coder": "#dfe6f0",
}
DEFAULT_ACCENT = "#d9a441"

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII"}


def quest_theme() -> Theme:
    """The palette above, bound to Textual's design tokens.

    Half the app styles itself with ``$primary``/``$success``/``$error``, which
    resolved to stock Textual blue, green and red — so a screen that borrowed a
    theme colour looked like a different application from one that used the
    palette. Rather than hunting every ``$`` down, the tokens are pointed at the
    palette: one registration turns the blue scrollbars, the blue text input and
    the blue panel borders warm, everywhere, at once.
    """
    return Theme(
        name="quest",
        primary=GOLD,
        secondary="#7f9fd9",
        accent=GOLD,
        warning=GOLD,
        error=BAD,
        success=GOOD,
        foreground=INK,
        background=BACK,
        surface=BACK,
        panel=CARD_BACK,
        dark=True,
        variables={
            "border": RULE,
            "border-blurred": RULE,
            "scrollbar": RULE,
            "scrollbar-hover": FRAME,
            "scrollbar-active": MUTE,
            "scrollbar-background": BACK,
            "scrollbar-background-hover": BACK,
            "scrollbar-background-active": BACK,
            "footer-background": CARD_BACK,
            "footer-key-foreground": GOLD,
            "footer-description-foreground": BODY,
            "footer-item-background": CARD_BACK,
            "block-cursor-background": GOLD,
            "block-cursor-foreground": BACK,
            "input-selection-background": f"{GOLD} 35%",
            "text-muted": MUTE,
            "text-disabled": SEALED,
        },
    )


#: Every list of choices in the game is a list of Buttons — the drill options,
#: the boss's phases, the duel, the journey's masters. A stock Textual Button
#: is three rows tall with a full-width border, so four options cost twelve
#: rows and read as four empty slabs with a centred label floating in each.
#: The rest of the game answers a question with a numbered row of text; these
#: now look like one, and get their affordance from a left bar that lights up
#: on focus rather than from a box.
BUTTON_CSS = f"""
Button {{
    width: 100%; height: 1; min-width: 0;
    border: none; border-left: outer {RULE};
    background: transparent; color: {BODY};
    padding: 0 2; margin: 0;
    text-align: left; content-align: left middle;
    text-style: none;
}}
Button:hover {{ background: {CARD_BACK}; color: {INK}; border-left: outer {MUTE}; }}
Button:focus {{ background: {CARD_BACK}; color: {INK}; border-left: outer {GOLD}; }}
Button.-active {{ background: {CARD_BACK}; color: {INK}; }}
"""


CARD_CSS = f"""
WardenCard {{
    height: auto;
    background: {CARD_BACK};
    border: round {RULE};
    padding: 1 2;
    margin: 0 1 1 0;
}}
WardenCard .card-head {{ layout: horizontal; height: {FRAME_H}; }}
WardenCard .card-frame {{
    width: {FRAME_W}; height: {FRAME_H};
    border: round {FRAME}; padding: 0 1;
}}
/* Padding-top one, so the rank line is level with the top of the art rather
   than with the frame's border a row above it. */
WardenCard .card-meta {{ width: 1fr; height: {FRAME_H}; padding: 1 0 0 2; }}
"""


def accent_for(identifier: str) -> str:
    return ACCENTS.get(identifier, DEFAULT_ACCENT)


def gauge(fraction: float, width: int, colour: str, *, track: str = RULE) -> str:
    """One bar language for the whole game, as markup.

    Two rules, both learned from screenshots.

    **The empty track is a full block, not ``▁``.** Drawn as a baseline rule the
    unfilled part of a bar sits on the bottom row of the cell and reads as an
    underscore — a text field, or a rendering fault. At nought per cent the home
    screen showed two long horizontal lines and nothing that could be mistaken
    for a gauge. A dark full block is unmistakably an empty track.

    **A started bar always shows one lit cell.** Rounding to zero tells a player
    who has walked three chapters that they have walked none.
    """
    width = max(1, width)
    filled = max(0, min(width, int(round(fraction * width))))
    if fraction > 0 and filled == 0:
        filled = 1
    if fraction >= 1.0:
        filled = width
    return f"[{colour}]{'█' * filled}[/][{track}]{'█' * (width - filled)}[/]"


_TAG = re.compile(r"\[/?[^\[\]]*\]")
_SENTINEL = "\x00"


def printed_width(text: str) -> int:
    """How many cells a markup string occupies once rendered.

    Escaped brackets are hidden before the tag pattern runs, or ``\\[2]`` — a
    literal ``[2]`` on screen — is mistaken for a style tag and measured as
    nothing wide.
    """
    hidden = text.replace("\\[", _SENTINEL)
    return len(_TAG.sub("", hidden).replace(_SENTINEL, "["))


def _fits(items: list[str], width: int, per_row: int, gap: int) -> list[str] | None:
    """Chunk into rows of ``per_row``, or None if any row is too wide."""
    rows = []
    for start in range(0, len(items), per_row):
        chunk = items[start : start + per_row]
        if sum(printed_width(t) for t in chunk) + gap * (len(chunk) - 1) > width:
            return None
        rows.append((" " * gap).join(chunk))
    return rows


def pack(items: list[str], width: int, *, gap: int = 4) -> list[str]:
    """Lay markup items out in as few rows as fit, and balance those rows.

    Two problems, one function. A row of options that overflows does not wrap
    gracefully: Textual breaks it wherever the width runs out, which orphaned
    "\\[6] Roster" onto a line of its own at eighty columns with three columns of
    white space above it. Making the break deliberate keeps the row a row.

    But a *greedy* deliberate break orphans just as badly — seven options at a
    hundred columns came out six-then-one, and a lone "\\[7] Codex" under a full
    row reads as an afterthought rather than as the seventh of seven. So the row
    count is found greedily and the items are then spread evenly across it.
    """
    rows: list[str] = []
    line: list[str] = []
    used = 0
    for text in items:
        cells = printed_width(text)
        if line and used + gap + cells > width:
            rows.append((" " * gap).join(line))
            line, used = [text], cells
        else:
            used += cells + (gap if line else 0)
            line.append(text)
    if line:
        rows.append((" " * gap).join(line))

    if len(rows) > 1:
        per_row = -(-len(items) // len(rows))
        balanced = _fits(items, width, per_row, gap)
        if balanced is not None and len(balanced) == len(rows):
            return balanced
    return rows


def letterspace(text: str, width: int) -> str:
    """Space out every character, but only when the result still fits."""
    spaced = " ".join(text)
    return spaced if len(spaced) <= width else text


def clip(text: str, width: int) -> str:
    """Trim to width with an ellipsis, never mid-escape and never wrapping."""
    text = " ".join(text.split())
    return text if len(text) <= width else text[: max(0, width - 1)].rstrip() + "…"


@dataclass(frozen=True)
class Stat:
    label: str
    value: str
    accented: bool = False


@dataclass(frozen=True)
class CardData:
    """Everything a card shows. Assembled by the adapters, never invented."""

    identifier: str
    sprite: Path | None
    rank: str
    name: str
    domain: str
    blurb: str
    stats: tuple[Stat, ...]
    quote: str

    @property
    def accent(self) -> str:
        return accent_for(self.identifier)


class WardenCard(Vertical):
    """One character, rendered as a dossier card."""

    def __init__(self, data: CardData, *, width: int = 76) -> None:
        super().__init__(classes="warden-card")
        self.data = data
        self.card_width = width
        self.styles.width = width

    @property
    def inner(self) -> int:
        """Columns available inside the border and padding."""
        return self.card_width - 2 - 4

    @property
    def meta_width(self) -> int:
        return self.inner - FRAME_W - 2

    def compose(self) -> ComposeResult:
        data = self.data
        accent = data.accent

        with Horizontal(classes="card-head"):
            frame = Vertical(classes="card-frame")
            with frame:
                if data.sprite is not None and data.sprite.is_file():
                    yield Static(sprite_text(load_sprite(data.sprite)))
                else:
                    # A missing sprite must not blow up the roster; the frame
                    # stays, so the layout does not shift when art lands.
                    yield Static(Text("?", style=FAINT))
            # The blurb belongs beside the portrait, not under it. A 24x24
            # portrait is twelve rows tall and the three lines of identity are
            # five, so the card used to carry seven blank rows of dead column to
            # the right of every face.
            #
            # Moving the blurb up took five of those seven. The last two are
            # spent rather than left at the bottom: two blank rows between each
            # pair of lines instead of one, which lands the rank on the top of
            # the head, the name on the eyes and the blurb on the shoulders. A
            # column of text beside a picture has to be as tall as the picture
            # or it reads as a caption that has come loose.
            with Vertical(classes="card-meta"):
                yield Static(
                    Text.assemble(
                        (letterspace(data.rank, self.meta_width), MUTE),
                        "\n\n\n",
                        (clip(data.name, self.meta_width), f"bold {INK}"),
                        "\n\n\n",
                        (clip(data.domain, self.meta_width), accent),
                        "\n\n\n",
                        ("─" * self.meta_width, RULE),
                        "\n\n",
                        ("◈  ", accent),
                        (clip(data.blurb, self.meta_width - 3), f"italic {BODY}"),
                        no_wrap=True,
                    )
                )

        yield Static(Text("─" * self.inner, style=RULE, no_wrap=True))
        yield Static("")
        for row in self._stat_rows():
            yield Static(row)
        yield Static("")
        yield Static(
            Text.assemble(
                ("▌ ", accent),
                (clip(data.quote, self.inner - 2), f"italic {BODY}"),
                no_wrap=True,
            )
        )

    def _stat_rows(self) -> list[Text]:
        """Stats laid out two to a row, values flush right in their half.

        Alignment is computed into the string rather than delegated to nested
        containers: a container per cell is four widgets a row to keep in step,
        and one ``ljust``/``rjust`` pair cannot drift.

        The left cell keeps a gutter. Justifying its value to the full half
        width closed the gap entirely and the card read ``0/7RESPECT`` — the
        left column's value and the right column's label with nothing between
        them. A column needs a space it cannot spend to be a column.
        """
        gutter = 4
        half = self.inner // 2
        widths = (half, self.inner - half)
        rows: list[Text] = []
        stats = list(self.data.stats)
        for index in range(0, len(stats), 2):
            pair = stats[index : index + 2]
            row = Text(no_wrap=True)
            for column, stat in enumerate(pair):
                # The left column reserves a gutter; the last one runs to the
                # card's own padding, which is gutter enough.
                width = widths[column] - (gutter if column == 0 else 0)
                # Nine, not eight: "PATTERNS" is exactly eight characters, so
                # an eight-wide label ran straight into its value.
                label = stat.label[:9].ljust(9)
                row.append(label, style=FAINT)
                row.append(
                    clip(stat.value, width - 9).rjust(width - 9),
                    style=self.data.accent if stat.accented else VALUE,
                )
                if column == 0 and len(pair) > 1:
                    row.append(" " * gutter)
            rows.append(row)
        return rows
