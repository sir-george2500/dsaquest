"""Application wiring.

One place that opens the database, loads content, and builds a scheduler, so
the CLI and the TUI cannot diverge on how the app is assembled.

``ensure_cards`` runs on every startup. That is what makes adding a pattern to
the content tree sufficient to make it schedulable — no migration, no import
step, no manual sync.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path

from fsrs import Scheduler

from .content.loader import PatternLibrary, load_library
from .content.problems import ProblemBank, load_problems
from .learning.fsrs_bridge import make_scheduler
from .storage import repositories as repo
from .storage.db import connect


@dataclass
class AppContext:
    conn: sqlite3.Connection
    library: PatternLibrary
    bank: ProblemBank
    scheduler: Scheduler
    db_path: str

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
    )
