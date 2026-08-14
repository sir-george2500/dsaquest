"""The Codex: who each master is, revealed as you earn it.

Lore is optional and it is a reward. A player who never opens the Codex loses
nothing from the training; a player who does should find that the master who
has been demanding proofs of them for six lessons had a reason, and that the
reason is the same one the lessons are shaped around.

**Unlocking is tied to real progress, not to visits.** A biography that opens
because you walked past is worth nothing. These open because you trained, were
tested, and beat the thing guarding the region — so the last entry a master has
is genuinely rare, and reading it means something happened.

The gates are derived from the same records everything else reads. There is no
separate "lore unlocked" table, for the same reason there is no story-state
table: a second store is a second truth, and it goes wrong the first time
somebody does things out of order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from functools import cache

import yaml

from ..content.loader import ContentError
from ..content.paths import content_root
from ..storage import repositories as repo


class Depth(IntEnum):
    """How far into a master's story you have earned your way.

    Ordered, so an entry is visible when the player's depth is at least the
    entry's own. A boss victory reveals everything a trial did.
    """

    MET = 0
    """You have met them and begun."""

    TRAINED = 1
    """Every secret held."""

    TESTED = 2
    """Their final test passed."""

    FELLED = 3
    """Their guardian is down."""

    PERFECT = 4
    """Their guardian went down without landing a blow."""


_DEPTH_BY_NAME = {d.name.lower(): d for d in Depth}


@dataclass(frozen=True, slots=True)
class Entry:
    """One readable section of a master's story."""

    key: str
    title: str
    text: str
    depth: Depth = Depth.MET

    def visible(self, reached: Depth) -> bool:
        return reached >= self.depth


@dataclass(frozen=True, slots=True)
class Relationship:
    """What one master thinks of another. Occasional, and always pointed."""

    master: str
    stance: str
    line: str


@dataclass(frozen=True, slots=True)
class MasterLore:
    master: str
    epithet: str = ""
    clan: str = ""
    creed: str = ""
    """One line, in their own words. Shown at the top of their Codex page."""

    entries: tuple[Entry, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    diagnosis: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """What this master says for each weakness, in their own voice."""

    def entry(self, key: str) -> Entry | None:
        for item in self.entries:
            if item.key == key:
                return item
        return None

    def visible_entries(self, reached: Depth) -> tuple[Entry, ...]:
        return tuple(e for e in self.entries if e.visible(reached))

    def locked_entries(self, reached: Depth) -> tuple[Entry, ...]:
        return tuple(e for e in self.entries if not e.visible(reached))


def lore_dir():
    return content_root() / "lore"


@cache
def load_lore() -> dict[str, MasterLore]:
    """Every authored master story. Missing lore is absence, not an error.

    A master with no file simply has no Codex page yet — the game is playable
    without any of this, and refusing to start over an unwritten biography
    would be the tail wagging the dog.
    """
    directory = lore_dir()
    if not directory.is_dir():
        return {}

    out: dict[str, MasterLore] = {}
    problems: list[str] = []

    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        master = str(raw.get("master") or path.stem)

        entries: list[Entry] = []
        for index, item in enumerate(raw.get("entries") or [], start=1):
            missing = [k for k in ("key", "title", "text") if not str(item.get(k, "")).strip()]
            if missing:
                problems.append(f"{path.name}: entry {index} missing {missing}")
                continue
            name = str(item.get("depth", "met")).lower()
            if name not in _DEPTH_BY_NAME:
                problems.append(
                    f"{path.name}: entry {item['key']!r} has depth {name!r}; "
                    f"expected one of {sorted(_DEPTH_BY_NAME)}"
                )
                continue
            entries.append(
                Entry(
                    key=str(item["key"]),
                    title=str(item["title"]),
                    text=str(item["text"]).strip(),
                    depth=_DEPTH_BY_NAME[name],
                )
            )

        if not entries:
            problems.append(f"{path.name}: no entries, so there is nothing to read")

        out[master] = MasterLore(
            master=master,
            epithet=str(raw.get("epithet", "")),
            clan=str(raw.get("clan", "")),
            creed=str(raw.get("creed", "")).strip(),
            entries=tuple(entries),
            relationships=tuple(
                Relationship(
                    master=str(r.get("master", "")),
                    stance=str(r.get("stance", "")),
                    line=str(r.get("line", "")).strip(),
                )
                for r in raw.get("relationships") or []
            ),
            diagnosis={
                str(k): tuple(str(x) for x in v) for k, v in (raw.get("diagnosis") or {}).items()
            },
        )

    if problems:
        raise ContentError(problems)
    return out


def depth_reached(context, master_id: str) -> Depth:
    """How far the player has earned into this master's story.

    Read from training, the final test and the guardian's record — the same
    facts the journey reads, so the Codex can never disagree with the road.
    """
    from ..journey import boss_for, load_chapters
    from ..lessons import session as lesson_session

    conn = context.conn
    reached = Depth.MET

    curriculum = None
    if context.curricula is not None:
        try:
            curriculum = context.curricula[master_id]
        except (KeyError, LookupError):
            curriculum = None

    if curriculum is not None and lesson_session.training_complete(conn, curriculum):
        reached = Depth.TRAINED
    if repo.get_master_progress(conn, master_id).passed:
        reached = Depth.TESTED

    chapter = load_chapters().chapter_for(master_id)
    if chapter is not None:
        boss = boss_for(context, chapter)
        if boss is not None:
            record = repo.get_boss_record(conn, boss.id)
            if record.defeated:
                reached = Depth.FELLED
                if (record.best_grade or "") in ("perfect", "legendary"):
                    reached = Depth.PERFECT
    return reached


def diagnosis_line(master_id: str, weakness: str, *, seed: int = 0) -> str:
    """What this master says about that weakness, in their own voice.

    Falls back to the plain wording rather than to silence: the diagnosis is
    the useful part, and a master with no authored line should still tell the
    student the truth.
    """
    from .diagnosis import FALLBACK, Weakness

    lore = load_lore().get(master_id)
    lines = lore.diagnosis.get(weakness) if lore else None
    if lines:
        return lines[seed % len(lines)]
    try:
        return FALLBACK[Weakness(weakness)]
    except ValueError:
        return ""
