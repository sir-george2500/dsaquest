"""Masters — data-driven characters, dialogue and portraits.

No dialogue is hardcoded anywhere in the engine. A new master is a JSON file and
a portrait; nothing in this package changes.

Two rules govern how a master speaks:

* **The pool is chosen by measurement, never by chance.** Randomness only picks
  *between* lines that already fit what actually happened. A master who says
  "pathetic" after a good performance destroys the only thing that makes his
  harshness bearable — that it is true.
* **He does not repeat himself while he has anything new to say.** Spoken lines
  are recorded, and a pool only starts recycling once it is exhausted.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from random import Random

from ..content.paths import content_root

#: Pools every character must define. Missing one is a content error, because
#: the engine will ask for it at some point and silence is not a personality.
REQUIRED_POOLS = frozenset(
    {
        "greeting_first",
        "greeting_returning",
        "greeting_after_gap",
        "lesson_intro",
        "lesson_memorise",
        "drill_correct",
        "drill_wrong",
        "drill_streak",
        "trial_intro",
        "fail_wrong_pattern",
        "fail_timeout",
        "fail_wrong_answer",
        "success",
        "success_fast",
        "praise_exceptional",
        "praise_major",
        "memorisation_detected",
        "improvement_noticed",
        "commitment_noticed",
        "gate_locked",
        "gate_open",
        "final_test_intro",
        "victory",
    }
)


class CharacterError(RuntimeError):
    pass


def characters_dir() -> Path:
    return content_root() / "characters"


def assets_dir() -> Path:
    # assets/ sits beside content/ in a checkout, and beside the package when
    # installed. Resolved relative to content_root so both work.
    return content_root().parent / "assets" / "characters"


@dataclass(frozen=True)
class Master:
    id: str
    name: str
    title: str
    region: str
    patterns: tuple[str, ...]
    personality: dict[str, float]
    gate: dict[str, float]
    dialogue: dict[str, tuple[str, ...]]

    @property
    def praise_threshold(self) -> float:
        """Percentile of the student's own history required for top-tier praise."""
        return float(self.personality.get("praise_threshold", 0.85))

    @property
    def verbosity(self) -> float:
        return float(self.personality.get("verbosity", 0.3))

    def pool(self, name: str) -> tuple[str, ...]:
        try:
            return self.dialogue[name]
        except KeyError:
            raise CharacterError(f"{self.id}: no dialogue pool {name!r}") from None

    @cached_property
    def portrait(self) -> str:
        """ASCII portrait. Mandatory — the game must work with no image support."""
        path = assets_dir() / self.id / "portrait.txt"
        if not path.is_file():
            raise CharacterError(f"{self.id}: missing {path}")
        return path.read_text(encoding="utf-8").rstrip("\n")

    def image_path(self) -> Path | None:
        """Optional bitmap portrait, for terminals that can draw one."""
        path = assets_dir() / self.id / "portrait.png"
        return path if path.is_file() else None


def load_masters() -> dict[str, Master]:
    directory = characters_dir()
    if not directory.is_dir():
        return {}

    masters: dict[str, Master] = {}
    problems: list[str] = []

    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}: {exc}")
            continue

        missing = REQUIRED_POOLS - set(raw.get("dialogue", {}))
        if missing:
            problems.append(f"{path.name}: missing dialogue pools {sorted(missing)}")
            continue

        empty = [k for k, v in raw["dialogue"].items() if not v]
        if empty:
            problems.append(f"{path.name}: empty dialogue pools {sorted(empty)}")
            continue

        master = Master(
            id=raw["id"],
            name=raw["name"],
            title=raw.get("title", raw["name"]),
            region=raw.get("region", ""),
            patterns=tuple(raw.get("patterns") or [raw["pattern"]]),
            personality=raw.get("personality", {}),
            gate=raw.get("gate", {}),
            dialogue={k: tuple(v) for k, v in raw["dialogue"].items()},
        )
        if path.stem != master.id:
            problems.append(f"{path.name}: file name must match id {master.id!r}")
        masters[master.id] = master

    if problems:
        raise CharacterError("character content is invalid:\n  - " + "\n  - ".join(problems))

    return masters


# --------------------------------------------------------------------------
# Speaking
# --------------------------------------------------------------------------


def _spoken(conn: sqlite3.Connection, master_id: str, pool: str) -> set[int]:
    rows = conn.execute(
        "SELECT line_index FROM character_memory WHERE master_id = ? AND pool = ?",
        (master_id, pool),
    ).fetchall()
    return {row["line_index"] for row in rows}


def speak(
    conn: sqlite3.Connection | None,
    master: Master,
    pool: str,
    *,
    seed: int | None = None,
    **placeholders: object,
) -> str:
    """Pick a line from ``pool``, preferring one not yet spoken.

    ``conn`` may be ``None`` for previews and tests, in which case nothing is
    recorded and the choice is purely seeded.

    Placeholders the caller does not supply are removed rather than printed —
    see :func:`_substitute`.
    """
    lines = master.pool(pool)
    rng = Random(seed if seed is not None else 0)

    if conn is None:
        index = rng.randrange(len(lines))
    else:
        already = _spoken(conn, master.id, pool)
        fresh = [i for i in range(len(lines)) if i not in already]
        if fresh:
            index = fresh[rng.randrange(len(fresh))]
        else:
            # Pool exhausted: start over rather than falling silent.
            conn.execute(
                "DELETE FROM character_memory WHERE master_id = ? AND pool = ?",
                (master.id, pool),
            )
            index = rng.randrange(len(lines))
        conn.execute(
            "INSERT OR IGNORE INTO character_memory (master_id, pool, line_index, spoken_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (master.id, pool, index),
        )

    return _substitute(lines[index], placeholders)


#: A placeholder the author wrote but the caller did not supply.
_UNRESOLVED = re.compile(r"\s*\{[a-z_][a-z0-9_]*\}")


def strip_placeholders(line: str) -> str:
    """Drop unresolved placeholders from a line quoted outside :func:`speak`.

    A card shows a character's own words without knowing the context that would
    fill ``{requirement}`` or ``{shortfall}``. Printing the braces raw is worse
    than printing a slightly shorter sentence.
    """
    return re.sub(r"\s{2,}", " ", _UNRESOLVED.sub("", line)).strip()


def _substitute(line: str, values: dict[str, object]) -> str:
    """Fill placeholders, and drop any the caller did not supply.

    The same pool is spoken from more than one place — ``fail_wrong_pattern``
    fires from both a trial and a final test, and those know different things.
    Rather than force every call site to pass every key an author might use,
    unresolved placeholders are removed along with the space before them.

    Leaving them visible would print ``You needed {score} of {total}`` at the
    learner, which reads as a bug in a moment that is supposed to carry weight.
    """
    for key, value in values.items():
        line = line.replace("{" + key + "}", str(value))
    line = _UNRESOLVED.sub("", line)
    return re.sub(r"\s{2,}", " ", line).strip()


def greeting_pool(days_since_seen: int | None) -> str:
    """Which greeting fits. Absence is something a master notices."""
    if days_since_seen is None:
        return "greeting_first"
    if days_since_seen >= 3:
        return "greeting_after_gap"
    return "greeting_returning"
