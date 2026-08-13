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

from dataclasses import dataclass
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from ..art.sprite import load_sprite, sprite_text

#: Canonical sprite size, plus its frame border and padding.
SPRITE_COLS = 24
FRAME_W = SPRITE_COLS + 4
FRAME_H = SPRITE_COLS // 2 + 2

#: The palette. Warm near-black, one ink, three greys, and a per-card accent.
BACK = "#100f0d"
CARD_BACK = "#15140f"
RULE = "#2b2822"
FRAME = "#38332b"
INK = "#ece5d6"
MUTE = "#8a7f6d"
FAINT = "#6b6459"
BODY = "#a89e8d"
VALUE = "#cfc7b8"

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
}
DEFAULT_ACCENT = "#d9a441"

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII"}

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
WardenCard .card-meta {{ width: 1fr; height: {FRAME_H}; padding: 0 0 0 2; }}
"""


def accent_for(identifier: str) -> str:
    return ACCENTS.get(identifier, DEFAULT_ACCENT)


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
            with Vertical(classes="card-meta"):
                yield Static(
                    Text(letterspace(data.rank, self.meta_width), style=MUTE, no_wrap=True)
                )
                yield Static("")
                yield Static(
                    Text(clip(data.name, self.meta_width), style=f"bold {INK}", no_wrap=True)
                )
                yield Static("")
                yield Static(Text(clip(data.domain, self.meta_width), style=accent, no_wrap=True))

        yield Static(Text("─" * self.inner, style=RULE, no_wrap=True))
        yield Static(
            Text.assemble(
                ("◈  ", accent),
                (clip(data.blurb, self.inner - 3), f"italic {BODY}"),
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
        """
        half = self.inner // 2
        widths = (half, self.inner - half)
        rows: list[Text] = []
        stats = list(self.data.stats)
        for index in range(0, len(stats), 2):
            pair = stats[index : index + 2]
            row = Text(no_wrap=True)
            for column, stat in enumerate(pair):
                width = widths[column]
                # Nine, not eight: "PATTERNS" is exactly eight characters, so
                # an eight-wide label ran straight into its value.
                label = stat.label[:9].ljust(9)
                row.append(label, style=FAINT)
                row.append(
                    clip(stat.value, width - 9).rjust(width - 9),
                    style=self.data.accent if stat.accented else VALUE,
                )
            rows.append(row)
        return rows
