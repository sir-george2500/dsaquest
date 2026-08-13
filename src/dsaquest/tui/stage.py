"""The arena stage: a room to fight in, not a sprite on a background.

The boss used to float in empty space. A room reads as somewhere you have been
*brought*, which is most of what makes a boss feel like an occasion, and it
costs nothing at runtime — the whole thing is one text buffer painted once per
redraw.

It is drawn back to front, the way a painter would: the far wall, then the
pillars standing against it, then the torches on them, then the floor running
towards the viewer, and the boss last so nothing can paint over it. Everything
behind the boss is desaturated and dim so that the only saturated thing on the
screen is the thing trying to kill you.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.style import Style
from rich.text import Text

from ..art.sprite import Sprite, sprite_segments, upscale

#: char, foreground, background. Half-blocks need both, so a plain string grid
#: cannot hold a sprite. The colours are whatever Rich accepts — a hex string
#: for the room, a ``rich.color.Color`` straight off a sprite segment. Passing
#: them through untouched avoids a lossy round trip through ``str()``, which
#: yields a repr rather than a colour and fails to parse.
Cell = tuple[str, object, object]

BACK_WALL = "#0a0908"
WALL_SEAM = "#15130f"
PILLAR_DARK = "#161310"
PILLAR_FACE = "#221d18"
PILLAR_LIT = "#2e2720"
FLOOR_NEAR = "#1a1611"
FLOOR_FAR = "#100e0b"
RING = "#2a2318"
TORCH_CORE = "#ffd98a"
TORCH_GLOW = "#8a5a1e"
TORCH_POST = "#241d16"


@dataclass(frozen=True, slots=True)
class Torch:
    x: int
    y: int


def _blank(width: int, height: int) -> list[list[Cell]]:
    return [[(" ", None, BACK_WALL) for _ in range(width)] for _ in range(height)]


def _paint_wall(grid: list[list[Cell]], width: int, horizon: int) -> None:
    """Faint vertical seams, so the back of the room has depth without detail."""
    for x in range(width // 5, width - width // 5, 11):
        for y in range(horizon):
            grid[y][x] = ("│", WALL_SEAM, BACK_WALL)


def _paint_pillars(grid: list[list[Cell]], width: int, horizon: int) -> None:
    """Pillars down both sides, bunching towards the edges.

    Confined to the outer fifth of each side. Placing them by a fixed offset
    from the edge looked right at 100 columns and marched straight across the
    boss at 50, because the middle is not reserved by anything — so the middle
    is reserved here, explicitly, and a narrow stage simply gets fewer pillars.
    """
    margin = max(6, width // 5)
    for offset, thickness in ((0, 3), (7, 2), (13, 2)):
        if offset + thickness > margin:
            continue
        for x in (offset, width - offset - thickness):
            if x < 0 or x + thickness > width:
                continue
            for y in range(horizon):
                for dx in range(thickness):
                    face = PILLAR_LIT if dx == 0 else PILLAR_FACE
                    grid[y][x + dx] = ("█", face, BACK_WALL)
            for dx in range(thickness):
                grid[0][x + dx] = ("▄", PILLAR_DARK, PILLAR_LIT)


def _paint_torch(grid: list[list[Cell]], torch: Torch, height: int) -> None:
    """A flame, its glow, and a bracket running down to nothing."""
    x, y = torch.x, torch.y
    if not (0 <= x < len(grid[0]) and 0 <= y < height):
        return
    grid[y][x] = ("▄", TORCH_CORE, TORCH_GLOW)
    if y + 1 < height:
        grid[y + 1][x] = ("▌", TORCH_POST, BACK_WALL)
    if y + 2 < height:
        grid[y + 2][x] = ("▌", TORCH_POST, BACK_WALL)
    # The halo. Dim, one cell out, and never over the flame itself.
    for dx, dy in ((-1, 0), (1, 0), (0, -1)):
        gx, gy = x + dx, y + dy
        if 0 <= gx < len(grid[0]) and 0 <= gy < height:
            grid[gy][gx] = (" ", None, "#1c1408")


def _paint_floor(grid: list[list[Cell]], width: int, horizon: int, height: int) -> None:
    """Boards receding to the horizon, and rings centred where the boss stands."""
    depth = max(1, height - horizon)
    for row in range(horizon, height):
        t = (row - horizon) / depth
        shade = FLOOR_NEAR if t > 0.5 else FLOOR_FAR
        for x in range(width):
            grid[row][x] = (" ", None, shade)

    centre = width // 2
    for index, (ry, rx) in enumerate(((2, 26), (4, 38), (6, 50))):
        cy = horizon + ry
        if not (horizon <= cy < height):
            continue
        for step in range(-rx, rx + 1):
            # A flattened ellipse: the floor is seen at a shallow angle, so the
            # vertical radius is a fraction of the horizontal one.
            x = centre + step
            if not 0 <= x < width:
                continue
            offset = 1.0 - (step / rx) ** 2
            if offset < 0:
                continue
            dy = int(round((offset**0.5) * (1.6 + index * 0.4)))
            for sign in (-1, 1):
                y = cy + sign * dy
                if horizon <= y < height:
                    grid[y][x] = ("─", RING, grid[y][x][2])


def _blit(grid: list[list[Cell]], sprite: Sprite, scale: int, top: int, width: int) -> None:
    lines = sprite_segments(upscale(sprite, scale))
    art_width = sprite.width * scale
    left = max(0, (width - art_width) // 2)
    for row, segments in enumerate(lines):
        y = top + row
        if not 0 <= y < len(grid):
            continue
        for column, segment in enumerate(segments):
            x = left + column
            if not 0 <= x < width:
                continue
            style = segment.style
            if segment.text == " " or style is None:
                continue  # transparent: the room shows through
            fg = style.color
            bg = style.bgcolor if style.bgcolor is not None else grid[y][x][2]
            grid[y][x] = (segment.text, fg, bg)


def _to_text(grid: list[list[Cell]]) -> Text:
    text = Text(no_wrap=True, overflow="crop")
    for index, row in enumerate(grid):
        if index:
            text.append("\n")
        for char, fg, bg in row:
            text.append(char, Style(color=fg, bgcolor=bg))
    return text


def stage_text(
    sprite: Sprite | None,
    *,
    width: int,
    height: int,
    scale: int = 0,
    lit: bool = True,
) -> Text:
    """The whole room, as one Rich Text.

    ``scale`` of 0 picks one to fit: a boss should command the room without
    filling it, which is about half its height. At 24x24 that is scale 2 in a
    tall terminal and scale 1 in a short one — and the choice has to be made
    here rather than by the caller, because the caller knows the widget size
    and not how many rows a sprite costs.

    ``lit`` goes false when the boss is beaten — the torches go out rather than
    the picture being removed, so the room you won in is still there.
    """
    width = max(40, width)
    height = max(16, height)
    horizon = max(6, int(height * 0.42))

    grid = _blank(width, height)
    _paint_wall(grid, width, horizon)
    _paint_pillars(grid, width, horizon)
    _paint_floor(grid, width, horizon, height)

    if lit:
        near = max(2, horizon - 5)
        far = max(1, horizon - 8)
        margin = max(6, width // 5)
        for x in (margin - 2, width - margin + 1):
            _paint_torch(grid, Torch(x, near), height)
        if width >= 80:
            for x in (3, width - 4):
                _paint_torch(grid, Torch(x, far), height)

    if sprite is not None:
        if scale <= 0:
            wanted = height * 0.55
            scale = 2 if (sprite.height * 2 + 1) // 2 <= wanted else 1
            if sprite.width * scale > width - 8:
                scale = 1
        art_rows = (sprite.height * scale + 1) // 2
        # Stand the boss ON the floor: its feet land on the middle ring, so it
        # is standing in the room rather than hovering over it.
        feet = min(horizon + 5, height - 2)
        _blit(grid, sprite, scale, max(0, feet - art_rows), width)

    return _to_text(grid)
