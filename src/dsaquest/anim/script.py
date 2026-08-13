"""Turning an authored script into frames.

An author writes a starting state and a list of steps. Each step says one line
about what is happening and applies a few small changes — move a pointer, mark
a cell, widen the span. The engine folds them:

    frame[i] = step[i] applied to frame[i-1]

so a frame cannot contradict the one before it. That is the whole reason for
the indirection. The alternative — authoring each picture whole — lets a
sliding window's left pointer jump backwards between two frames, and nothing
would catch it, and the student would learn the wrong thing from a picture that
looked authoritative.

Everything an author can get wrong is checked at load: an index off the end of
the array, an unknown mark, a pointer that was never introduced, a step with
nothing to say. The errors name the step number, because a script is a hundred
lines of YAML and "index 7 out of range" on its own is useless.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .scene import (
    Animation,
    ArrayScene,
    BitsScene,
    Frame,
    Mark,
    Scene,
    TableScene,
)


class ScriptError(ValueError):
    """The script cannot be turned into frames."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


#: Keys every step may carry, whatever the scene kind.
_COMMON = {"say", "note", "idiom"}
_KEYS: dict[str, set[str]] = {
    "array": _COMMON | {"point", "move", "unpoint", "span", "mark", "set"},
    "bits": _COMMON | {"value", "highlight"},
    "table": _COMMON | {"cursor", "set", "mark"},
}


def _mark(name: str, where: str, problems: list[str]) -> Mark:
    try:
        return Mark(name)
    except ValueError:
        problems.append(
            f"{where}: unknown mark {name!r}; expected one of {[m.value for m in Mark]}"
        )
        return Mark.PLAIN


def _index(value: Any, limit: int, where: str, problems: list[str]) -> int | None:
    try:
        index = int(value)
    except (TypeError, ValueError):
        problems.append(f"{where}: {value!r} is not an index")
        return None
    if not 0 <= index < limit:
        problems.append(f"{where}: index {index} is outside the array (0..{limit - 1})")
        return None
    return index


def _cell(key: Any, height: int, width: int, where: str, problems: list[str]):
    """Parse a ``"row,col"`` table key."""
    try:
        row_text, column_text = str(key).split(",")
        row, column = int(row_text), int(column_text)
    except (TypeError, ValueError):
        problems.append(f"{where}: {key!r} is not a 'row,col' cell")
        return None
    if not (0 <= row < height and 0 <= column < width):
        problems.append(f"{where}: cell {row},{column} is outside the {height}x{width} table")
        return None
    return row, column


def _start(raw: dict, kind: str, problems: list[str]) -> Scene | None:
    if kind == "array":
        values = [str(v) for v in raw.get("data", [])]
        if not values:
            problems.append("array animation has no 'data'")
            return None
        return ArrayScene(
            values=tuple(values),
            marks=tuple(Mark.PLAIN for _ in values),
            labels=tuple(str(v) for v in raw.get("labels", ())),
            note=str(raw.get("note", "")),
        )
    if kind == "bits":
        return BitsScene(
            value=int(raw.get("value", 0)),
            bits=int(raw.get("bits", 16)),
            note=str(raw.get("note", "")),
        )
    if kind == "table":
        rows = raw.get("rows") or []
        if not rows:
            problems.append("table animation has no 'rows'")
            return None
        width = max(len(r) for r in rows)
        grid = tuple(tuple(str(c) for c in r) + ("",) * (width - len(r)) for r in rows)
        return TableScene(
            rows=grid,
            marks=tuple(tuple(Mark.PLAIN for _ in row) for row in grid),
            row_labels=tuple(str(v) for v in raw.get("row_labels", ())),
            column_labels=tuple(str(v) for v in raw.get("column_labels", ())),
            note=str(raw.get("note", "")),
        )
    problems.append(f"unknown animation kind {kind!r}; expected array, bits or table")
    return None


def _apply_array(scene: ArrayScene, step: dict, where: str, problems: list[str]) -> ArrayScene:
    pointers = dict(scene.pointers)
    marks = list(scene.marks)
    values = list(scene.values)
    span = scene.span

    for name, raw_index in (step.get("point") or {}).items():
        index = _index(raw_index, len(values), f"{where}.point[{name}]", problems)
        if index is not None:
            pointers[str(name)] = index

    for name, delta in (step.get("move") or {}).items():
        name = str(name)
        if name not in pointers:
            problems.append(f"{where}.move[{name}]: moved a pointer that was never placed")
            continue
        index = _index(pointers[name] + int(delta), len(values), f"{where}.move[{name}]", problems)
        if index is not None:
            pointers[name] = index

    for name in step.get("unpoint") or ():
        pointers.pop(str(name), None)

    for raw_index, name in (step.get("mark") or {}).items():
        index = _index(raw_index, len(values), f"{where}.mark", problems)
        if index is not None:
            marks[index] = _mark(str(name), f"{where}.mark[{raw_index}]", problems)

    for raw_index, value in (step.get("set") or {}).items():
        index = _index(raw_index, len(values), f"{where}.set", problems)
        if index is not None:
            values[index] = str(value)

    if "span" in step:
        raw_span = step["span"]
        if raw_span is None:
            span = None
        else:
            try:
                low, high = (int(x) for x in raw_span)
            except (TypeError, ValueError):
                problems.append(f"{where}.span: expected [low, high] or null")
                low = high = None  # type: ignore[assignment]
            else:
                if not (0 <= low < len(values) and 0 <= high < len(values)):
                    problems.append(f"{where}.span: [{low}, {high}] is outside the array")
                elif high < low:
                    problems.append(f"{where}.span: [{low}, {high}] runs backwards")
                else:
                    span = (low, high)

    return replace(
        scene,
        values=tuple(values),
        marks=tuple(marks),
        pointers=tuple(pointers.items()),
        span=span,
        note=str(step.get("note", scene.note)),
    )


def _apply_bits(scene: BitsScene, step: dict, where: str, problems: list[str]) -> BitsScene:
    value = scene.value
    if "value" in step:
        try:
            value = int(step["value"])
        except (TypeError, ValueError):
            problems.append(f"{where}.value: not an integer")

    highlight = scene.highlight
    if "highlight" in step:
        raw = step["highlight"] or ()
        positions = []
        for item in raw:
            try:
                position = int(item)
            except (TypeError, ValueError):
                problems.append(f"{where}.highlight: {item!r} is not a bit position")
                continue
            if not 0 <= position < scene.bits:
                problems.append(f"{where}.highlight: bit {position} is outside 0..{scene.bits - 1}")
                continue
            positions.append(position)
        highlight = tuple(positions)

    return replace(scene, value=value, highlight=highlight, note=str(step.get("note", scene.note)))


def _apply_table(scene: TableScene, step: dict, where: str, problems: list[str]) -> TableScene:
    rows = [list(r) for r in scene.rows]
    marks = [list(m) for m in scene.marks]
    cursor = scene.cursor

    for key, value in (step.get("set") or {}).items():
        cell = _cell(key, scene.height, scene.width, f"{where}.set", problems)
        if cell:
            rows[cell[0]][cell[1]] = str(value)

    for key, name in (step.get("mark") or {}).items():
        cell = _cell(key, scene.height, scene.width, f"{where}.mark", problems)
        if cell:
            marks[cell[0]][cell[1]] = _mark(str(name), f"{where}.mark[{key}]", problems)

    if "cursor" in step:
        raw = step["cursor"]
        if raw is None:
            cursor = None
        else:
            cell = _cell(
                f"{raw[0]},{raw[1]}", scene.height, scene.width, f"{where}.cursor", problems
            )
            if cell:
                cursor = cell

    return replace(
        scene,
        rows=tuple(tuple(r) for r in rows),
        marks=tuple(tuple(m) for m in marks),
        cursor=cursor,
        note=str(step.get("note", scene.note)),
    )


_APPLY = {"array": _apply_array, "bits": _apply_bits, "table": _apply_table}


def build_animation(raw: dict, *, identifier: str = "") -> Animation:
    """Fold a parsed script into frames, or raise with every problem at once."""
    problems: list[str] = []
    animation_id = str(raw.get("id") or identifier)
    if not animation_id:
        problems.append("animation has no 'id'")

    kind = str(raw.get("kind", "array"))
    steps = raw.get("steps") or []
    if not steps:
        problems.append(f"{animation_id}: no steps, so there is nothing to show")

    scene = _start(raw, kind, problems)
    if scene is None or problems:
        raise ScriptError(problems or [f"{animation_id}: could not build a starting scene"])

    apply = _APPLY[kind]
    allowed = _KEYS[kind]
    frames: list[Frame] = []
    idiom = str(raw.get("idiom", ""))

    for number, step in enumerate(steps, start=1):
        where = f"{animation_id} step {number}"
        if not isinstance(step, dict):
            problems.append(f"{where}: expected a mapping")
            continue
        unknown = set(step) - allowed
        if unknown:
            problems.append(f"{where}: unknown key(s) {sorted(unknown)} for a {kind} animation")
        caption = str(step.get("say", "")).strip()
        if not caption:
            problems.append(f"{where}: no 'say' — a frame with no explanation teaches nothing")

        scene = apply(scene, step, where, problems)
        idiom = str(step.get("idiom", idiom))
        frames.append(Frame(number=number, scene=scene, caption=caption, idiom=idiom))

    if problems:
        raise ScriptError(problems)

    return Animation(
        id=animation_id,
        title=str(raw.get("title", animation_id)),
        frames=tuple(frames),
        secret=str(raw.get("secret", "")),
        pattern=str(raw.get("pattern", "")),
        summary=str(raw.get("summary", "")),
    )
