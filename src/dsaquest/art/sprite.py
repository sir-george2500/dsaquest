"""Pixel art in a terminal cell grid.

A terminal cell is about twice as tall as it is wide, which makes it a bad
pixel. The half-block glyph ``▀`` fixes that: it paints the top half in the
foreground colour and the bottom half in the background colour, so **one cell
holds two square pixels** stacked vertically. A 24x24 sprite becomes 24 columns
by 12 rows, and the pixels come out square.

This needs 24-bit colour. Every terminal worth running this game in has it
(``COLORTERM=truecolor``); on one that does not, Rich downsamples to the 256
colour cube on its own and the art degrades rather than breaks.

The sprite format is plain text so it diffs, greps and can be hand-edited:

    # name: The Array Beast
    # palette: . none  k #14100e  b #3d2f26  g #d9a441
    ....kkkk....
    ...kbbbbk...

One character per pixel, a palette mapping those characters to hex, and ``.``
(or any character mapped to ``none``) for transparent. Transparency is real:
it emits an unstyled space, so a sprite sits on whatever the card behind it is
painted, instead of carrying a background of its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from rich.segment import Segment
from rich.style import Style
from rich.text import Text

#: Upper half block. Foreground paints the top pixel, background the bottom.
HALF = "▀"

#: Lower half block, for a column whose top pixel is transparent.
LOWER = "▄"

_PALETTE_ENTRY = re.compile(r"(\S+)\s*=?\s*(#[0-9a-fA-F]{6}|none)")


class SpriteError(ValueError):
    """The sprite file cannot be read as pixels."""


@dataclass(frozen=True)
class Sprite:
    """A grid of pixels, each either a hex colour or None for transparent."""

    name: str
    rows: tuple[tuple[str | None, ...], ...]

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    @property
    def cell_height(self) -> int:
        """Rows of terminal cells needed, two pixels to a cell."""
        return (self.height + 1) // 2

    def pixel(self, x: int, y: int) -> str | None:
        if 0 <= y < self.height and 0 <= x < len(self.rows[y]):
            return self.rows[y][x]
        return None


def parse_sprite(text: str, *, name: str = "") -> Sprite:
    """Read the sprite format. Raises SpriteError rather than guessing."""
    palette: dict[str, str | None] = {}
    pixel_lines: list[str] = []
    title = name

    for line in text.splitlines():
        if line.startswith("#"):
            body = line[1:].strip()
            if body.lower().startswith("name:"):
                title = body[5:].strip()
            elif body.lower().startswith("palette:"):
                for char, value in _PALETTE_ENTRY.findall(body[8:]):
                    palette[char] = None if value == "none" else value.lower()
            continue
        if not line.strip():
            continue
        pixel_lines.append(line.rstrip("\n"))

    if not pixel_lines:
        raise SpriteError(f"sprite {title or name!r} has no pixel rows")

    width = max(len(line) for line in pixel_lines)
    unknown = {ch for line in pixel_lines for ch in line if ch not in palette and ch not in " ."}
    if unknown:
        raise SpriteError(f"sprite {title or name!r} uses {sorted(unknown)} with no palette entry")

    rows = tuple(tuple(palette.get(ch) for ch in line.ljust(width)) for line in pixel_lines)
    return Sprite(name=title or name, rows=rows)


@cache
def load_sprite(path: Path) -> Sprite:
    """Parse a sprite file. Cached — sprites are immutable and re-read often."""
    return parse_sprite(path.read_text(encoding="utf-8"), name=path.stem)


def upscale(sprite: Sprite, factor: int) -> Sprite:
    """Repeat every pixel ``factor`` times in both directions.

    Nearest-neighbour on purpose. Pixel art is not a low-resolution photograph
    to be smoothed; the hard edge IS the art, and any interpolation turns a
    24x24 portrait into a blur. Scaling before the half-block pass means one
    renderer serves every size.
    """
    if factor <= 1:
        return sprite
    rows = tuple(
        tuple(pixel for pixel in row for _ in range(factor))
        for row in sprite.rows
        for _ in range(factor)
    )
    return Sprite(name=sprite.name, rows=rows)


def sprite_segments(sprite: Sprite) -> list[list[Segment]]:
    """One list of segments per terminal row.

    Two pixel rows collapse into one cell row. The four transparency cases are
    all distinct and all reachable, so each is handled rather than approximated:
    both pixels solid, top only, bottom only, neither.
    """
    lines: list[list[Segment]] = []
    for top_y in range(0, sprite.height, 2):
        segments: list[Segment] = []
        for x in range(sprite.width):
            top = sprite.pixel(x, top_y)
            bottom = sprite.pixel(x, top_y + 1)
            if top is None and bottom is None:
                segments.append(Segment(" "))
            elif top is None:
                segments.append(Segment(LOWER, Style(color=bottom)))
            elif bottom is None:
                segments.append(Segment(HALF, Style(color=top)))
            else:
                segments.append(Segment(HALF, Style(color=top, bgcolor=bottom)))
        lines.append(segments)
    return lines


def sprite_text(sprite: Sprite, *, scale: int = 1) -> Text:
    """The sprite as a Rich Text, ready to hand to a Static.

    ``scale`` is in source pixels. A cell is twice as tall as it is wide and
    holds two stacked pixels, so scale 1 gives ``width`` columns by
    ``height / 2`` rows, and scale 2 gives twice each — 24x24 becomes 48x24,
    which is the size a boss wants and a side portrait does not.
    """
    text = Text(no_wrap=True, overflow="crop")
    for index, line in enumerate(sprite_segments(upscale(sprite, scale))):
        if index:
            text.append("\n")
        for segment in line:
            text.append(segment.text, segment.style)
    return text
