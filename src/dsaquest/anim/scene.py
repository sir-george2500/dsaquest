"""What an animation is made of.

A concept animation is a list of **frames**, and a frame is a picture of the
algorithm's state plus one line saying what just happened. The student steps
through them, forwards and backwards, as slowly as they like.

Frames are never authored directly. An author writes a list of small *steps* —
move this pointer, mark that cell, widen the window — and the engine folds them
into frames (see ``script.py``). The reason is the same one behind differential
judging: an authored frame can contradict the frame before it and nothing would
notice, whereas a frame computed by applying a step to the previous state
cannot. An animation of binary search whose window silently grows is worse than
no animation, because the student will believe it.

Three scene kinds cover almost the whole curriculum:

* :class:`ArrayScene` — a row of cells with named pointers under them and an
  optional highlighted span. Arrays, two pointers, sliding windows, prefix
  sums, binary search, sorting, greedy scans.
* :class:`BitsScene` — one integer as its bits. The Master of Bits.
* :class:`TableScene` — a filled grid with a cursor. Dynamic programming.

Trees and graphs are deliberately absent: they need layout, and a bad layout
teaches a wrong shape. Better to have no picture than a misleading one.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum


class Mark(StrEnum):
    """What has happened to one cell. Rendering maps these to colour."""

    PLAIN = "plain"
    """Untouched."""

    ACTIVE = "active"
    """Being looked at right now."""

    IN = "in"
    """Inside the current window, or otherwise admitted."""

    SETTLED = "settled"
    """Finished with — decided, sorted into place, already counted."""

    OUT = "out"
    """Ruled out. Binary search's discarded half lives here."""

    ANSWER = "answer"
    """The answer, or the best found so far."""


@dataclass(frozen=True, slots=True)
class ArrayScene:
    """A row of values, with named pointers and an optional span."""

    values: tuple[str, ...]
    marks: tuple[Mark, ...]
    pointers: tuple[tuple[str, int], ...] = ()
    """Named indices drawn under the row, in author order."""

    span: tuple[int, int] | None = None
    """An inclusive range drawn as a bracket under the row."""

    note: str = ""
    """Running state worth showing — "best = 3", "sum = 12"."""

    labels: tuple[str, ...] = ()
    """Optional per-cell labels drawn above, e.g. indices."""

    @property
    def width(self) -> int:
        return len(self.values)


@dataclass(frozen=True, slots=True)
class BitsScene:
    """One integer, as bits, most significant first."""

    value: int
    bits: int = 16
    highlight: tuple[int, ...] = ()
    """Bit positions (0 = least significant) drawn as the focus."""

    note: str = ""
    expression: str = ""
    """The C++ being demonstrated, e.g. ``n & (n - 1)``."""


@dataclass(frozen=True, slots=True)
class TableScene:
    """A grid, for dynamic programming."""

    rows: tuple[tuple[str, ...], ...]
    cursor: tuple[int, int] | None = None
    marks: tuple[tuple[Mark, ...], ...] = ()
    row_labels: tuple[str, ...] = ()
    column_labels: tuple[str, ...] = ()
    note: str = ""

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0


Scene = ArrayScene | BitsScene | TableScene


@dataclass(frozen=True, slots=True)
class Frame:
    """One step of the story: a picture, and what just happened."""

    number: int
    scene: Scene
    caption: str
    idiom: str = ""
    """The line of C++ this frame is executing, if the author named one."""


@dataclass
class Animation:
    """A whole animation, ready to play."""

    id: str
    title: str
    frames: tuple[Frame, ...] = field(default_factory=tuple)
    secret: str = ""
    pattern: str = ""
    summary: str = ""

    def __len__(self) -> int:
        return len(self.frames)

    def frame(self, index: int) -> Frame:
        """Clamped rather than wrapping — running off the end should stop, not loop."""
        if not self.frames:
            raise IndexError(f"animation {self.id!r} has no frames")
        return self.frames[max(0, min(index, len(self.frames) - 1))]


def marked(scene: ArrayScene, index: int, mark: Mark) -> ArrayScene:
    marks = list(scene.marks)
    marks[index] = mark
    return replace(scene, marks=tuple(marks))
