"""Connection management and migrations.

Pragmas worth explaining, since the defaults are wrong for a desktop app:

``journal_mode=WAL``
    Readers no longer block the writer. The TUI reads stats while a judge run
    writes attempts; without WAL that is a ``database is locked`` error.

``synchronous=NORMAL``
    With WAL this is durable across application crashes and only risks the last
    transaction on a *power* loss. FULL costs an fsync per commit, which is a
    real stall on every XP tick for a guarantee a practice log does not need.

``foreign_keys=ON``
    Off by default in SQLite, for backwards compatibility. Our ON DELETE
    CASCADE rules are inert without it.

``busy_timeout``
    Rather than failing instantly on contention, wait. Cheap insurance against
    two ``dsa`` processes being open at once.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from platformdirs import user_data_dir

from .schema import LATEST_VERSION, MIGRATIONS

APP_NAME = "dsa-quest"


class DatabaseError(RuntimeError):
    pass


def default_db_path() -> Path:
    return Path(user_data_dir(APP_NAME, appauthor=False)) / "progress.db"


def utcnow() -> str:
    """The single source of 'now' for persisted timestamps: ISO-8601 UTC."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def connect(path: Path | str | None = None, *, migrate: bool = True) -> sqlite3.Connection:
    """Open (creating if needed) the progress database.

    Pass ``":memory:"`` for tests.
    """
    if path is None:
        path = default_db_path()

    target = str(path)
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(target, isolation_level=None)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    if target != ":memory:":
        # WAL is meaningless for an in-memory database and emits a warning.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")

    if migrate:
        apply_migrations(conn)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit transaction.

    ``isolation_level=None`` puts sqlite3 in autocommit mode, which means we
    control transactions rather than the driver guessing from statement types.
    """
    conn.execute("BEGIN")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Bring the database up to ``LATEST_VERSION``.

    Uses SQLite's built-in ``user_version`` rather than a bookkeeping table:
    it is atomic with the migration's own transaction, so a crash mid-migration
    cannot leave the version and the schema disagreeing.
    """
    current = schema_version(conn)

    if current > LATEST_VERSION:
        raise DatabaseError(
            f"database is at schema version {current}, but this build of DSA Quest "
            f"only understands {LATEST_VERSION}. Upgrade the application."
        )

    for migration in MIGRATIONS:
        if migration.version <= current:
            continue
        # BEGIN/COMMIT live inside the script rather than around it:
        # executescript() issues an implicit COMMIT if a transaction is already
        # open, so wrapping it in our own transaction() leaves nothing to commit
        # and raises "cannot commit - no transaction is active". Bundling the
        # user_version bump into the same script keeps schema and version
        # atomic, so a crash mid-migration cannot leave them disagreeing.
        conn.executescript(
            f"BEGIN;\n{migration.sql}\nPRAGMA user_version = {migration.version};\nCOMMIT;"
        )
        current = migration.version

    return current


def integrity_check(conn: sqlite3.Connection) -> list[str]:
    """Return a list of problems, empty when the database is sound."""
    problems: list[str] = []

    for row in conn.execute("PRAGMA integrity_check"):
        if row[0] != "ok":
            problems.append(f"integrity: {row[0]}")

    for row in conn.execute("PRAGMA foreign_key_check"):
        problems.append(f"foreign key: table {row[0]} row {row[1]} -> {row[2]}")

    return problems
