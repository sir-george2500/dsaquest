"""The road, loaded from content.

One file names the order Delta-X walks in and what is said at each stop. It
references masters and guardians that already exist — the story is built around
the cast, and a chapter naming an unknown master is refused rather than skipped,
because a silently missing chapter is a hole in the road nobody would notice.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

import yaml

from ..content.loader import ContentError
from ..content.paths import content_root


@dataclass(frozen=True, slots=True)
class Chapter:
    id: str
    number: str
    name: str
    master: str
    boss: str = ""
    arrival: str = ""
    master_says: tuple[str, ...] = ()
    boss_says: str = ""
    victory: str = ""
    revelation: str = ""


@dataclass(frozen=True, slots=True)
class FinalChapter:
    id: str
    number: str
    name: str
    boss: str
    arrival: str = ""
    boss_says: tuple[str, ...] = ()
    victory: str = ""
    revelation: str = ""


@dataclass(frozen=True, slots=True)
class Story:
    title: str
    hero: str
    villain: str
    chapters: tuple[Chapter, ...]
    final: FinalChapter | None = None

    def chapter_for(self, master_id: str) -> Chapter | None:
        for chapter in self.chapters:
            if chapter.master == master_id:
                return chapter
        return None


def chapters_file():
    return content_root() / "story" / "chapters.yaml"


@cache
def load_chapters() -> Story:
    path = chapters_file()
    if not path.is_file():
        return Story(title="", hero="", villain="", chapters=())

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    problems: list[str] = []
    chapters: list[Chapter] = []

    for index, entry in enumerate(raw.get("chapters") or [], start=1):
        missing = [k for k in ("id", "name", "master") if not entry.get(k)]
        if missing:
            problems.append(f"chapter {index}: missing {missing}")
            continue
        chapters.append(
            Chapter(
                id=str(entry["id"]),
                number=str(entry.get("number", index)),
                name=str(entry["name"]),
                master=str(entry["master"]),
                boss=str(entry.get("boss", "")),
                arrival=str(entry.get("arrival", "")).strip(),
                master_says=tuple(str(x) for x in entry.get("master_says", ())),
                boss_says=str(entry.get("boss_says", "")).strip(),
                victory=str(entry.get("victory", "")).strip(),
                revelation=str(entry.get("revelation", "")).strip(),
            )
        )

    final = None
    raw_final = raw.get("final")
    if raw_final:
        final = FinalChapter(
            id=str(raw_final.get("id", "final")),
            number=str(raw_final.get("number", "")),
            name=str(raw_final.get("name", "")),
            boss=str(raw_final.get("boss", "")),
            arrival=str(raw_final.get("arrival", "")).strip(),
            boss_says=tuple(str(x) for x in raw_final.get("boss_says", ())),
            victory=str(raw_final.get("victory", "")).strip(),
            revelation=str(raw_final.get("revelation", "")).strip(),
        )

    if problems:
        raise ContentError([f"{path.name}: {p}" for p in problems])

    return Story(
        title=str(raw.get("title", "")),
        hero=str(raw.get("hero", "DELTA-X")),
        villain=str(raw.get("villain", "")),
        chapters=tuple(chapters),
        final=final,
    )
