"""Application wiring.

One place that opens the database, loads content, and builds a scheduler, so
the CLI and the TUI cannot diverge on how the app is assembled.

``ensure_cards`` runs on every startup. That is what makes adding a pattern to
the content tree sufficient to make it schedulable — no migration, no import
step, no manual sync.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path

from fsrs import Scheduler

from .content.lessons import CurriculumSet, load_curricula
from .content.loader import PatternLibrary, load_library
from .content.problems import ProblemBank, load_problems
from .learning.fsrs_bridge import make_scheduler
from .storage import repositories as repo
from .storage.db import connect
from .world.character import Master, load_masters


@dataclass
class AppContext:
    conn: sqlite3.Connection
    library: PatternLibrary
    bank: ProblemBank
    scheduler: Scheduler
    db_path: str
    curricula: CurriculumSet | None = None
    masters: dict[str, Master] = field(default_factory=dict)

    def master_for(self, pattern_id: str):
        """The master who teaches this pattern, with his curriculum, or None.

        Patterns authored before the master system have no teacher yet; they
        remain playable through the ordinary modes.
        """
        if self.curricula is None:
            return None
        curriculum = self.curricula.for_pattern(pattern_id)
        if curriculum is None:
            return None
        master = self.masters.get(curriculum.master_id)
        return None if master is None else (master, curriculum)

    @cached_property
    def profile(self) -> repo.Profile:
        return repo.get_profile(self.conn)

    def refresh_profile(self) -> repo.Profile:
        self.__dict__.pop("profile", None)
        return self.profile

    def now(self) -> datetime:
        return datetime.now(UTC)

    def close(self) -> None:
        self.conn.close()


def build(db_path: Path | str | None = None, *, fuzz: bool = True) -> AppContext:
    conn = connect(db_path)
    profile = repo.ensure_profile(conn)

    library = load_library()
    bank = load_problems(library)

    # Idempotent: new content becomes schedulable simply by existing.
    repo.ensure_cards(conn, [pattern.id for pattern in library])

    return AppContext(
        conn=conn,
        library=library,
        bank=bank,
        scheduler=make_scheduler(profile.target_retention, fuzz=fuzz),
        db_path=str(db_path) if db_path else "",
        curricula=load_curricula(library, bank),
        masters=load_masters(),
    )
