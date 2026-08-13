"""Repositories — the only code that writes SQL.

Deliberately plain functions over a connection rather than an ORM. The queries
here are the interesting part (the confusion matrix, the due-card selection),
and an ORM would hide exactly those behind generated SQL.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from ..domain.enums import Dimension, GameMode, MistakeCode, Rating, Verdict
from .db import transaction, utcnow

# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Profile:
    xp: int
    created_at: str
    timezone: str
    target_retention: float
    daily_goal_minutes: int
    cpp_standard: str
    editor_mode: str


def ensure_profile(conn: sqlite3.Connection, *, timezone: str = "UTC") -> Profile:
    conn.execute(
        "INSERT OR IGNORE INTO profile (id, created_at, timezone) VALUES (1, ?, ?)",
        (utcnow(), timezone),
    )
    return get_profile(conn)


def get_profile(conn: sqlite3.Connection) -> Profile:
    row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    if row is None:
        raise LookupError("no profile row; call ensure_profile first")
    return Profile(
        xp=row["xp"],
        created_at=row["created_at"],
        timezone=row["timezone"],
        target_retention=row["target_retention"],
        daily_goal_minutes=row["daily_goal_minutes"],
        cpp_standard=row["cpp_standard"],
        editor_mode=row["editor_mode"],
    )


def add_xp(conn: sqlite3.Connection, amount: int) -> int:
    """Add XP (never negative) and return the new total."""
    if amount < 0:
        raise ValueError("XP is never removed; losing a Boss Fight costs time, not progress")
    conn.execute("UPDATE profile SET xp = xp + ? WHERE id = 1", (amount,))
    return int(conn.execute("SELECT xp FROM profile WHERE id = 1").fetchone()[0])


# --------------------------------------------------------------------------
# Cards (FSRS memory state)
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CardRecord:
    """Persisted FSRS memory state for one (pattern, dimension) pair.

    The fields mirror ``fsrs.Card``'s constructor exactly, which is what lets
    the bridge round-trip without a lossy translation layer. ``step`` in
    particular must be stored: it tracks position within the learning steps, and
    dropping it silently restarts a card's learning phase on every load.
    """

    id: int
    pattern_id: str
    dimension: Dimension
    state: str
    step: int | None
    stability: float | None
    difficulty: float | None
    due_at: str
    last_review_at: str | None
    reps: int
    lapses: int

    @property
    def is_new(self) -> bool:
        """Never reviewed.

        FSRS has no "new" state — a fresh card is already ``Learning`` with
        ``step=0`` — so "new" is derived from the absence of a review rather
        than stored, which keeps our state column and FSRS's in agreement.
        """
        return self.last_review_at is None


def _card(row: sqlite3.Row) -> CardRecord:
    return CardRecord(
        id=row["id"],
        pattern_id=row["pattern_id"],
        dimension=Dimension(row["dimension"]),
        state=row["state"],
        step=row["step"],
        stability=row["stability"],
        difficulty=row["difficulty"],
        due_at=row["due_at"],
        last_review_at=row["last_review_at"],
        reps=row["reps"],
        lapses=row["lapses"],
    )


def ensure_cards(conn: sqlite3.Connection, pattern_ids: Iterable[str]) -> int:
    """Create the three cards for each pattern that does not have them yet.

    Idempotent, so it is safe to run on every startup — which is how new
    patterns added to the content tree become schedulable without a migration.
    """
    now = utcnow()
    rows = [(pid, dim.value, now) for pid in pattern_ids for dim in Dimension]
    with transaction(conn):
        cursor = conn.executemany(
            "INSERT OR IGNORE INTO card (pattern_id, dimension, due_at) VALUES (?, ?, ?)",
            rows,
        )
    # state/step default to 'learning'/0, matching a freshly constructed
    # fsrs.Card. due_at = now means an untouched pattern is immediately
    # offerable rather than waiting for a schedule that does not exist yet.
    return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0


def get_card(conn: sqlite3.Connection, pattern_id: str, dimension: Dimension) -> CardRecord:
    row = conn.execute(
        "SELECT * FROM card WHERE pattern_id = ? AND dimension = ?",
        (pattern_id, dimension.value),
    ).fetchone()
    if row is None:
        raise LookupError(f"no card for {pattern_id}/{dimension.value}")
    return _card(row)


def cards_for(conn: sqlite3.Connection, pattern_id: str) -> tuple[CardRecord, ...]:
    rows = conn.execute(
        "SELECT * FROM card WHERE pattern_id = ? ORDER BY dimension", (pattern_id,)
    ).fetchall()
    return tuple(_card(r) for r in rows)


def due_cards(
    conn: sqlite3.Connection,
    *,
    now: str | None = None,
    limit: int = 20,
    only: Sequence[str] | None = None,
) -> tuple[CardRecord, ...]:
    """Cards whose review is due, most overdue first.

    Ordering by ``due_at`` ascending means the longest-neglected material comes
    back first, which is what stops a weak pattern from being crowded out by a
    steady drip of newer ones.
    """
    now = now or utcnow()
    sql = "SELECT * FROM card WHERE due_at <= ?"
    params: list[object] = [now]
    if only is not None:
        if not only:
            return ()
        sql += f" AND pattern_id IN ({','.join('?' * len(only))})"
        params.extend(only)
    sql += " ORDER BY due_at ASC LIMIT ?"
    params.append(limit)
    return tuple(_card(r) for r in conn.execute(sql, params))


def update_card(
    conn: sqlite3.Connection,
    card_id: int,
    *,
    state: str,
    stability: float | None,
    difficulty: float | None,
    due_at: str,
    last_review_at: str,
    reps: int,
    lapses: int,
    step: int | None = None,
) -> None:
    conn.execute(
        """
        UPDATE card
           SET state = ?, step = ?, stability = ?, difficulty = ?, due_at = ?,
               last_review_at = ?, reps = ?, lapses = ?
         WHERE id = ?
        """,
        (state, step, stability, difficulty, due_at, last_review_at, reps, lapses, card_id),
    )


def log_review(
    conn: sqlite3.Connection,
    *,
    card_id: int,
    rating: Rating,
    mode: GameMode,
    attempt_id: int | None = None,
    elapsed_days: float | None = None,
    scheduled_days: float | None = None,
    duration_ms: int | None = None,
    reviewed_at: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO review_log
            (card_id, attempt_id, rating, reviewed_at, elapsed_days,
             scheduled_days, mode, duration_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            card_id,
            attempt_id,
            rating.value,
            reviewed_at or utcnow(),
            elapsed_days,
            scheduled_days,
            mode.value,
            duration_ms,
        ),
    )
    return int(cursor.lastrowid)


# --------------------------------------------------------------------------
# Attempts
# --------------------------------------------------------------------------


def start_attempt(
    conn: sqlite3.Connection,
    *,
    pattern_id: str,
    mode: GameMode,
    seed: int,
    problem_id: str | None = None,
    difficulty: str | None = None,
    session_id: int | None = None,
    par_ms: int | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO attempt
            (session_id, pattern_id, problem_id, seed, mode, difficulty, par_ms, started_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, pattern_id, problem_id, seed, mode.value, difficulty, par_ms, utcnow()),
    )
    return int(cursor.lastrowid)


def finish_attempt(
    conn: sqlite3.Connection,
    attempt_id: int,
    *,
    correct: bool,
    verdict: Verdict | None = None,
    chosen_pattern_id: str | None = None,
    hints_used: int = 0,
    tries: int = 1,
    duration_ms: int | None = None,
    xp_awarded: int = 0,
) -> None:
    conn.execute(
        """
        UPDATE attempt
           SET correct = ?, verdict = ?, chosen_pattern_id = ?, hints_used = ?,
               tries = ?, duration_ms = ?, xp_awarded = ?, finished_at = ?
         WHERE id = ?
        """,
        (
            int(correct),
            verdict.value if verdict else None,
            chosen_pattern_id,
            hints_used,
            tries,
            duration_ms,
            xp_awarded,
            utcnow(),
            attempt_id,
        ),
    )


def record_submission(
    conn: sqlite3.Connection,
    *,
    attempt_id: int,
    source: str,
    verdict: Verdict,
    tests_passed: int,
    tests_total: int,
    max_cpu_ms: int | None = None,
    max_memory_kb: int | None = None,
    compile_log: str = "",
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO submission
            (attempt_id, source, verdict, tests_passed, tests_total,
             max_cpu_ms, max_memory_kb, compile_log, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attempt_id,
            source,
            verdict.value,
            tests_passed,
            tests_total,
            max_cpu_ms,
            max_memory_kb,
            compile_log,
            utcnow(),
        ),
    )
    return int(cursor.lastrowid)


def record_mistake(
    conn: sqlite3.Connection,
    *,
    attempt_id: int,
    pattern_id: str,
    code: MistakeCode,
    note: str = "",
) -> None:
    conn.execute(
        "INSERT INTO mistake (attempt_id, pattern_id, code, note, observed_at) VALUES (?,?,?,?,?)",
        (attempt_id, pattern_id, code.value, note, utcnow()),
    )


# --------------------------------------------------------------------------
# Analytics
# --------------------------------------------------------------------------


def accuracy(conn: sqlite3.Connection, pattern_id: str, *, window: int = 20) -> float | None:
    """First-attempt success rate over the most recent ``window`` attempts.

    ``None`` when there is no history — which is different from 0.0 and must
    stay distinguishable, or an untouched pattern looks like a failed one.
    """
    rows = conn.execute(
        """
        SELECT correct FROM attempt
         WHERE pattern_id = ? AND finished_at IS NOT NULL
         ORDER BY started_at DESC LIMIT ?
        """,
        (pattern_id, window),
    ).fetchall()
    if not rows:
        return None
    return sum(r["correct"] for r in rows) / len(rows)


def median_duration_ms(conn: sqlite3.Connection, pattern_id: str, mode: GameMode) -> int | None:
    rows = conn.execute(
        """
        SELECT duration_ms FROM attempt
         WHERE pattern_id = ? AND mode = ? AND correct = 1 AND duration_ms IS NOT NULL
         ORDER BY duration_ms
        """,
        (pattern_id, mode.value),
    ).fetchall()
    if not rows:
        return None
    values = [r["duration_ms"] for r in rows]
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) // 2


def confusion_pairs(conn: sqlite3.Connection, *, limit: int = 10) -> list[tuple[str, str, int]]:
    """(actual_pattern, chosen_pattern, times) for wrong recognition answers.

    This is the query the whole ``chosen_pattern_id`` column exists for. It
    turns "you are weak at recognition" into "you call prefix-sum problems
    sliding-window, six times so far".
    """
    rows = conn.execute(
        """
        SELECT pattern_id, chosen_pattern_id, COUNT(*) AS n
          FROM attempt
         WHERE chosen_pattern_id IS NOT NULL
           AND chosen_pattern_id <> pattern_id
         GROUP BY pattern_id, chosen_pattern_id
         ORDER BY n DESC, pattern_id
         LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [(r["pattern_id"], r["chosen_pattern_id"], r["n"]) for r in rows]


def top_mistakes(conn: sqlite3.Connection, *, limit: int = 5) -> list[tuple[MistakeCode, int]]:
    rows = conn.execute(
        "SELECT code, COUNT(*) AS n FROM mistake GROUP BY code ORDER BY n DESC LIMIT ?",
        (limit,),
    ).fetchall()
    out: list[tuple[MistakeCode, int]] = []
    for row in rows:
        try:
            out.append((MistakeCode(row["code"]), row["n"]))
        except ValueError:
            # A code retired from the enum. Skip rather than crash the stats screen.
            continue
    return out


# --------------------------------------------------------------------------
# Streaks and unlocks
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Streak:
    kind: str
    current: int
    best: int
    last_day: str | None


def touch_streak(conn: sqlite3.Connection, kind: str, *, today: date | None = None) -> Streak:
    """Record activity for ``kind`` today and return the updated streak.

    Same-day repeats are idempotent — practising twice in a day is not a
    two-day streak, and a streak that can be farmed is not a streak.
    """
    today = today or datetime.now().date()
    today_s = today.isoformat()

    row = conn.execute("SELECT * FROM streak WHERE kind = ?", (kind,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO streak (kind, current, best, last_day) VALUES (?, 1, 1, ?)",
            (kind, today_s),
        )
        return Streak(kind, 1, 1, today_s)

    last = date.fromisoformat(row["last_day"]) if row["last_day"] else None
    if last == today:
        current = row["current"]
    elif last is not None and last == today - timedelta(days=1):
        current = row["current"] + 1
    else:
        current = 1

    best = max(row["best"], current)
    conn.execute(
        "UPDATE streak SET current = ?, best = ?, last_day = ? WHERE kind = ?",
        (current, best, today_s, kind),
    )
    return Streak(kind, current, best, today_s)


def get_streak(conn: sqlite3.Connection, kind: str, *, today: date | None = None) -> Streak:
    """Read a streak, reporting 0 if it has already lapsed.

    The stored ``current`` is only meaningful relative to ``last_day``; a streak
    last touched three days ago is broken even though nothing has written to it.
    Computing that on read means a lapsed streak never displays as intact.
    """
    row = conn.execute("SELECT * FROM streak WHERE kind = ?", (kind,)).fetchone()
    if row is None:
        return Streak(kind, 0, 0, None)

    today = today or datetime.now().date()
    last = date.fromisoformat(row["last_day"]) if row["last_day"] else None
    current = row["current"]
    if last is None or (today - last).days > 1:
        current = 0
    return Streak(kind, current, row["best"], row["last_day"])


def unlock_pattern(conn: sqlite3.Connection, pattern_id: str) -> bool:
    """Returns True if this call performed the unlock (so the UI can celebrate)."""
    cursor = conn.execute(
        "INSERT OR IGNORE INTO unlock (pattern_id, unlocked_at) VALUES (?, ?)",
        (pattern_id, utcnow()),
    )
    return cursor.rowcount > 0


def unlocked_patterns(conn: sqlite3.Connection) -> set[str]:
    return {r["pattern_id"] for r in conn.execute("SELECT pattern_id FROM unlock")}


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------


def start_session(conn: sqlite3.Connection) -> int:
    cursor = conn.execute("INSERT INTO session (started_at) VALUES (?)", (utcnow(),))
    return int(cursor.lastrowid)


def end_session(conn: sqlite3.Connection, session_id: int) -> None:
    conn.execute(
        """
        UPDATE session
           SET ended_at = ?,
               xp_earned = COALESCE(
                   (SELECT SUM(xp_awarded) FROM attempt WHERE session_id = ?), 0),
               modes = COALESCE(
                   (SELECT GROUP_CONCAT(DISTINCT mode) FROM attempt WHERE session_id = ?), '')
         WHERE id = ?
        """,
        (utcnow(), session_id, session_id, session_id),
    )


def attempts_today(conn: sqlite3.Connection, pattern_id: str, *, today: date | None = None) -> int:
    """Finished attempts at one pattern on the local calendar day.

    Drives the XP diminishing-returns multiplier. Uses ``localtime`` so "today"
    means the same thing here as it does for streaks — a session at 23:00 and
    one at 01:00 are different days to the learner even though they may be the
    same UTC day.
    """
    today = today or datetime.now().date()
    row = conn.execute(
        """
        SELECT COUNT(*) FROM attempt
         WHERE pattern_id = ?
           AND finished_at IS NOT NULL
           AND date(started_at, 'localtime') = ?
        """,
        (pattern_id, today.isoformat()),
    ).fetchone()
    return int(row[0])


def sessions_completed(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM session WHERE ended_at IS NOT NULL").fetchone()
    return int(row[0])


def perfect_boss_count(conn: sqlite3.Connection) -> int:
    """Boss Fights cleared first try with no hints."""
    row = conn.execute(
        """
        SELECT COUNT(*) FROM attempt
         WHERE mode = 'boss' AND correct = 1 AND tries = 1 AND hints_used = 0
        """
    ).fetchone()
    return int(row[0])


def best_solve_ratio(conn: sqlite3.Connection) -> float | None:
    """Fastest correct implementation as a fraction of its par time.

    Uses the ``par_ms`` recorded on the attempt rather than recomputing it, so
    a later change to the par table cannot retroactively rewrite history.
    """
    row = conn.execute(
        """
        SELECT MIN(CAST(duration_ms AS REAL) / par_ms) FROM attempt
         WHERE correct = 1
           AND duration_ms IS NOT NULL
           AND par_ms IS NOT NULL AND par_ms > 0
           AND mode IN ('solve', 'boss', 'complete')
        """
    ).fetchone()
    return float(row[0]) if row[0] is not None else None


def implementations_passed(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM attempt
         WHERE correct = 1 AND mode IN ('solve', 'boss', 'complete')
        """
    ).fetchone()
    return int(row[0])


# --------------------------------------------------------------------------
# Lessons and drills
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SecretProgress:
    master_id: str
    secret_id: str
    state: str
    drills_seen: int
    drills_correct: int
    consecutive_correct: int
    taught_at: str | None
    fluent_at: str | None
    tested_at: str | None

    @property
    def is_taught(self) -> bool:
        return self.state != "untaught"

    @property
    def is_fluent(self) -> bool:
        return self.state in ("fluent", "tested")

    @property
    def accuracy(self) -> float | None:
        """None when untried — different from 0.0 and must stay distinguishable."""
        if not self.drills_seen:
            return None
        return self.drills_correct / self.drills_seen


def _secret_progress(row: sqlite3.Row) -> SecretProgress:
    return SecretProgress(
        master_id=row["master_id"],
        secret_id=row["secret_id"],
        state=row["state"],
        drills_seen=row["drills_seen"],
        drills_correct=row["drills_correct"],
        consecutive_correct=row["consecutive_correct"],
        taught_at=row["taught_at"],
        fluent_at=row["fluent_at"],
        tested_at=row["tested_at"],
    )


def ensure_secret(conn: sqlite3.Connection, master_id: str, secret_id: str) -> SecretProgress:
    conn.execute(
        "INSERT OR IGNORE INTO lesson_progress (master_id, secret_id) VALUES (?, ?)",
        (master_id, secret_id),
    )
    return get_secret_progress(conn, master_id, secret_id)


def get_secret_progress(conn: sqlite3.Connection, master_id: str, secret_id: str) -> SecretProgress:
    row = conn.execute(
        "SELECT * FROM lesson_progress WHERE master_id = ? AND secret_id = ?",
        (master_id, secret_id),
    ).fetchone()
    if row is None:
        raise LookupError(f"no progress for {master_id}/{secret_id}; call ensure_secret")
    return _secret_progress(row)


def all_secret_progress(conn: sqlite3.Connection, master_id: str) -> tuple[SecretProgress, ...]:
    rows = conn.execute(
        "SELECT * FROM lesson_progress WHERE master_id = ? ORDER BY secret_id", (master_id,)
    ).fetchall()
    return tuple(_secret_progress(r) for r in rows)


def mark_taught(conn: sqlite3.Connection, master_id: str, secret_id: str) -> None:
    """Record that the master has delivered the lesson. Idempotent."""
    ensure_secret(conn, master_id, secret_id)
    conn.execute(
        """
        UPDATE lesson_progress
           SET state = CASE WHEN state = 'untaught' THEN 'taught' ELSE state END,
               taught_at = COALESCE(taught_at, ?)
         WHERE master_id = ? AND secret_id = ?
        """,
        (utcnow(), master_id, secret_id),
    )


def set_secret_state(conn: sqlite3.Connection, master_id: str, secret_id: str, state: str) -> None:
    column = {"fluent": "fluent_at", "tested": "tested_at"}.get(state)
    if column:
        conn.execute(
            f"UPDATE lesson_progress SET state = ?, {column} = COALESCE({column}, ?) "
            f"WHERE master_id = ? AND secret_id = ?",
            (state, utcnow(), master_id, secret_id),
        )
    else:
        conn.execute(
            "UPDATE lesson_progress SET state = ? WHERE master_id = ? AND secret_id = ?",
            (state, master_id, secret_id),
        )


def record_drill(
    conn: sqlite3.Connection,
    *,
    master_id: str,
    secret_id: str,
    drill_id: str,
    kind: str,
    correct: bool,
    given: str = "",
    duration_ms: int | None = None,
) -> SecretProgress:
    """Log one drill and roll the secret's counters forward in one transaction."""
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO drill_attempt
                (master_id, secret_id, drill_id, kind, correct, given, duration_ms, attempted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (master_id, secret_id, drill_id, kind, int(correct), given, duration_ms, utcnow()),
        )
        conn.execute(
            """
            UPDATE lesson_progress
               SET drills_seen = drills_seen + 1,
                   drills_correct = drills_correct + ?,
                   consecutive_correct = CASE WHEN ? THEN consecutive_correct + 1 ELSE 0 END,
                   state = CASE WHEN state IN ('untaught', 'taught') THEN 'drilling' ELSE state END
             WHERE master_id = ? AND secret_id = ?
            """,
            (int(correct), int(correct), master_id, secret_id),
        )
    return get_secret_progress(conn, master_id, secret_id)


def drill_kinds_passed(conn: sqlite3.Connection, master_id: str, secret_id: str) -> frozenset[str]:
    """Distinct drill kinds this secret has been answered correctly on.

    Fluency requires breadth, not just a streak: five correct EVALUATE drills
    prove a reflex, not understanding.
    """
    rows = conn.execute(
        """
        SELECT DISTINCT kind FROM drill_attempt
         WHERE master_id = ? AND secret_id = ? AND correct = 1
        """,
        (master_id, secret_id),
    ).fetchall()
    return frozenset(r["kind"] for r in rows)


def drills_answered(conn: sqlite3.Connection, master_id: str, secret_id: str) -> frozenset[str]:
    rows = conn.execute(
        "SELECT DISTINCT drill_id FROM drill_attempt WHERE master_id = ? AND secret_id = ?",
        (master_id, secret_id),
    ).fetchall()
    return frozenset(r["drill_id"] for r in rows)


# --------------------------------------------------------------------------
# Respect
# --------------------------------------------------------------------------


def add_respect(conn: sqlite3.Connection, master_id: str, points: int) -> int:
    """Add respect and return the new total. Never falls below zero."""
    now = utcnow()
    conn.execute(
        "INSERT OR IGNORE INTO respect (master_id, points, met_at, last_seen) VALUES (?,0,?,?)",
        (master_id, now, now),
    )
    conn.execute(
        "UPDATE respect SET points = MAX(0, points + ?), last_seen = ? WHERE master_id = ?",
        (points, now, master_id),
    )
    row = conn.execute("SELECT points FROM respect WHERE master_id = ?", (master_id,)).fetchone()
    return int(row[0])


def get_respect(conn: sqlite3.Connection, master_id: str) -> int:
    row = conn.execute("SELECT points FROM respect WHERE master_id = ?", (master_id,)).fetchone()
    return int(row[0]) if row else 0


def days_since_seen(conn: sqlite3.Connection, master_id: str) -> int | None:
    """Whole days since this master last saw the student. None if never met."""
    row = conn.execute("SELECT last_seen FROM respect WHERE master_id = ?", (master_id,)).fetchone()
    if row is None:
        return None
    return (datetime.now(UTC) - datetime.fromisoformat(row[0])).days


def record_timing(
    conn: sqlite3.Connection,
    attempt_id: int,
    *,
    breakdown: dict[str, int],
    limit_ms: int | None = None,
    timed_out: bool = False,
    pressure_stage: int | None = None,
) -> None:
    """Persist where the time went, and the clock that was in force.

    ``limit_ms`` is stored on the attempt rather than recomputed later, so a
    future change to the par table cannot retroactively rewrite whether a past
    attempt timed out.
    """
    with transaction(conn):
        conn.execute(
            "UPDATE attempt SET limit_ms = ?, timed_out = ?, pressure_stage = ? WHERE id = ?",
            (limit_ms, int(timed_out), pressure_stage, attempt_id),
        )
        for phase, duration in breakdown.items():
            if duration <= 0:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO phase_timing (attempt_id, phase, duration_ms) "
                "VALUES (?, ?, ?)",
                (attempt_id, phase, duration),
            )


def phase_breakdown(conn: sqlite3.Connection, attempt_id: int) -> dict[str, int]:
    rows = conn.execute(
        "SELECT phase, duration_ms FROM phase_timing WHERE attempt_id = ?", (attempt_id,)
    ).fetchall()
    return {row["phase"]: row["duration_ms"] for row in rows}


def timeout_rate(conn: sqlite3.Connection, pattern_id: str, *, window: int = 20) -> float | None:
    """Share of recent finished attempts that ran out of clock.

    A rising rate means the material is understood but not yet fluent, which is
    a different problem from getting it wrong and wants a different remedy.
    """
    rows = conn.execute(
        """
        SELECT timed_out FROM attempt
         WHERE pattern_id = ? AND finished_at IS NOT NULL
         ORDER BY started_at DESC LIMIT ?
        """,
        (pattern_id, window),
    ).fetchall()
    if not rows:
        return None
    return sum(row["timed_out"] for row in rows) / len(rows)


# --------------------------------------------------------------------------
# The master's final test
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MasterProgress:
    master_id: str
    attempts: int
    passed: bool
    best_score: int | None
    best_total: int | None
    first_passed_at: str | None
    last_attempt_at: str | None

    @property
    def best_fraction(self) -> float | None:
        if not self.best_total:
            return None
        return (self.best_score or 0) / self.best_total


def get_master_progress(conn: sqlite3.Connection, master_id: str) -> MasterProgress:
    conn.execute("INSERT OR IGNORE INTO master_progress (master_id) VALUES (?)", (master_id,))
    row = conn.execute("SELECT * FROM master_progress WHERE master_id = ?", (master_id,)).fetchone()
    return MasterProgress(
        master_id=row["master_id"],
        attempts=row["attempts"],
        passed=bool(row["passed"]),
        best_score=row["best_score"],
        best_total=row["best_total"],
        first_passed_at=row["first_passed_at"],
        last_attempt_at=row["last_attempt_at"],
    )


def record_final_test(
    conn: sqlite3.Connection, master_id: str, *, score: int, total: int, passed: bool
) -> MasterProgress:
    """Log one attempt at a master's final test.

    ``passed`` is sticky: once earned it is never revoked, even if a later
    rematch goes badly. A master does not un-recognise what you proved.
    """
    now = utcnow()
    get_master_progress(conn, master_id)
    with transaction(conn):
        conn.execute(
            """
            UPDATE master_progress
               SET attempts = attempts + 1,
                   passed = MAX(passed, ?),
                   best_score = CASE
                       WHEN best_score IS NULL OR ? > best_score THEN ? ELSE best_score END,
                   best_total = ?,
                   first_passed_at = COALESCE(first_passed_at, CASE WHEN ? THEN ? END),
                   last_attempt_at = ?
             WHERE master_id = ?
            """,
            (int(passed), score, score, total, int(passed), now, now, master_id),
        )
    return get_master_progress(conn, master_id)
