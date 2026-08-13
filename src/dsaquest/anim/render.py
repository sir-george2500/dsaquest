"""Drawing a scene.

Terminal-native and deliberately plain: boxed cells, carets for pointers, a
bracket for the span. Colour carries the marks, but never carries them *alone*
— a settled cell is dim and a ruled-out cell is struck through, so the picture
still reads if colour is lost or the reader cannot separate the hues.
"""

from __future__ import annotations

from rich.text import Text

from .scene import ArrayScene, BitsScene, Mark, Scene, TableScene

CELL = 5
"""Columns per array cell, including its right border."""

#: How each mark is painted. Style first, then a glyph that survives without it.
STYLES: dict[Mark, str] = {
    Mark.PLAIN: "#a89e8d",
    Mark.ACTIVE: "bold #f0c14b",
    Mark.IN: "bold #6fd97f",
    Mark.SETTLED: "#6b8fbf",
    Mark.OUT: "dim strike #6b6459",
    Mark.ANSWER: "bold #d9a441 reverse",
}

RULE = "#3a352c"
LABEL = "#6b6459"
NOTE = "#a89e8d"
POINTER = "#f0c14b"


def render(scene: Scene) -> Text:
    if isinstance(scene, ArrayScene):
        return _array(scene)
    if isinstance(scene, BitsScene):
        return _bits(scene)
    if isinstance(scene, TableScene):
        return _table(scene)
    raise TypeError(f"no renderer for {type(scene).__name__}")


def _array(scene: ArrayScene) -> Text:
    out = Text(no_wrap=True, overflow="crop")
    width = scene.width

    if scene.labels:
        out.append("  ")
        for index in range(width):
            label = scene.labels[index] if index < len(scene.labels) else ""
            out.append(f"{label:^{CELL}}", style=LABEL)
        out.append("\n")

    out.append("  " + "┌" + "┬".join("─" * (CELL - 1) for _ in range(width)) + "┐\n", style=RULE)

    out.append("  ")
    for index in range(width):
        out.append("│", style=RULE)
        out.append(f"{scene.values[index]:^{CELL - 1}}", style=STYLES[scene.marks[index]])
    out.append("│\n", style=RULE)

    out.append("  " + "└" + "┴".join("─" * (CELL - 1) for _ in range(width)) + "┘\n", style=RULE)

    # Pointers. Several may land on one cell, so they stack: carets on one row,
    # names on the next, and a shared cell lists both names.
    if scene.pointers:
        by_index: dict[int, list[str]] = {}
        for name, index in scene.pointers:
            by_index.setdefault(index, []).append(name)

        out.append("  ")
        for index in range(width):
            out.append(f"{'▲' if index in by_index else '':^{CELL}}", style=POINTER)
        out.append("\n  ")
        for index in range(width):
            names = ",".join(by_index.get(index, ()))
            out.append(f"{names:^{CELL}}", style=POINTER)
        out.append("\n")

    if scene.span is not None:
        low, high = scene.span
        out.append("  ")
        out.append(" " * (low * CELL))
        inner = (high - low + 1) * CELL - 2
        out.append("└" + "─" * max(0, inner) + "┘", style=STYLES[Mark.IN])
        out.append("\n")

    if scene.note:
        out.append(f"\n  {scene.note}", style=NOTE)
    return out


def _bits(scene: BitsScene) -> Text:
    out = Text(no_wrap=True, overflow="crop")
    positions = list(range(scene.bits - 1, -1, -1))

    if scene.expression:
        out.append(f"  {scene.expression}\n\n", style="bold #f0c14b")

    out.append("  ")
    for position in positions:
        bit = (scene.value >> position) & 1
        style = STYLES[Mark.ACTIVE] if position in scene.highlight else STYLES[Mark.PLAIN]
        out.append(f"{bit} ", style=style)
        if position % 4 == 0 and position:
            out.append(" ")
    out.append("\n  ")
    for position in positions:
        caret = "▲" if position in scene.highlight else " "
        out.append(f"{caret} ", style=POINTER)
        if position % 4 == 0 and position:
            out.append(" ")
    out.append("\n")

    out.append(f"\n  decimal {scene.value}", style=LABEL)
    if scene.note:
        out.append(f"\n  {scene.note}", style=NOTE)
    return out


def _table(scene: TableScene) -> Text:
    out = Text(no_wrap=True, overflow="crop")
    stub = max((len(label) for label in scene.row_labels), default=0) + 1
    cell = max(3, max((len(c) for row in scene.rows for c in row), default=1) + 2)

    if scene.column_labels:
        out.append(" " * (stub + 2))
        for label in scene.column_labels:
            out.append(f"{label:^{cell}}", style=LABEL)
        out.append("\n")

    for r, row in enumerate(scene.rows):
        label = scene.row_labels[r] if r < len(scene.row_labels) else ""
        out.append(f"  {label:>{stub}}", style=LABEL)
        for c, value in enumerate(row):
            mark = scene.marks[r][c] if scene.marks else Mark.PLAIN
            style = STYLES[mark]
            if scene.cursor == (r, c):
                out.append(f"[{value:^{cell - 2}}]", style=STYLES[Mark.ACTIVE])
            else:
                out.append(f"{value:^{cell}}", style=style)
        out.append("\n")

    if scene.note:
        out.append(f"\n  {scene.note}", style=NOTE)
    return out
