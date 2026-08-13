"""Database schema, as an ordered list of migrations.

Design rule: **this database holds user state only.** Patterns, problems and
templates live in versioned YAML under ``content/``. Nothing here duplicates
them — ``pattern_id`` columns are plain TEXT referencing a content id, not
foreign keys into a mirrored table.

That split is what makes content editable without a migration, and what makes a
user's progress survive a content update. The cost is that referential
integrity for content ids is checked at load time (``content.loader``) rather
than by SQLite, which is the right trade when content ships with the app.

Timestamps are ISO-8601 UTC text. SQLite has no date type; text sorts correctly,
survives a ``.dump``, and is legible when you are debugging someone's database
over a chat window.
"""

from __future__ import annotations

from typing import NamedTuple


class Migration(NamedTuple):
    version: int
    name: str
    sql: str


_V1 = """
-- Exactly one row. The CHECK is what enforces that, rather than convention.
CREATE TABLE profile (
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    created_at         TEXT    NOT NULL,
    timezone           TEXT    NOT NULL DEFAULT 'UTC',
    xp                 INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
    target_retention   REAL    NOT NULL DEFAULT 0.90
                               CHECK (target_retention > 0.5 AND target_retention < 1.0),
    daily_goal_minutes INTEGER NOT NULL DEFAULT 20 CHECK (daily_goal_minutes > 0),
    cpp_standard       TEXT    NOT NULL DEFAULT 'c++20',
    editor_mode        TEXT    NOT NULL DEFAULT 'handoff'
                               CHECK (editor_mode IN ('handoff', 'inline', 'watch'))
);

-- One FSRS memory state per (pattern, dimension). Three cards per pattern,
-- because recognition, recall and implementation decay independently.
-- Columns mirror fsrs.Card's constructor so the bridge round-trips losslessly.
--
-- There is deliberately no 'new' state: FSRS models only Learning / Review /
-- Relearning, and a fresh card is already Learning with step 0. "Never seen"
-- is derived from last_review_at IS NULL, so our state column can never drift
-- out of agreement with the scheduler's.
--
-- `step` tracks position within the learning steps (0 or 1 while learning,
-- NULL once in review). Omitting it restarts a card's learning phase on every
-- load, which is invisible until you notice nothing ever graduates.
CREATE TABLE card (
    id             INTEGER PRIMARY KEY,
    pattern_id     TEXT    NOT NULL,
    dimension      TEXT    NOT NULL
                           CHECK (dimension IN ('recognition', 'recall', 'implementation')),
    state          TEXT    NOT NULL DEFAULT 'learning'
                           CHECK (state IN ('learning', 'review', 'relearning')),
    step           INTEGER DEFAULT 0,
    stability      REAL    CHECK (stability IS NULL OR stability > 0),
    difficulty     REAL    CHECK (difficulty IS NULL OR (difficulty >= 1 AND difficulty <= 10)),
    due_at         TEXT    NOT NULL,
    last_review_at TEXT,
    reps           INTEGER NOT NULL DEFAULT 0 CHECK (reps >= 0),
    lapses         INTEGER NOT NULL DEFAULT 0 CHECK (lapses >= 0),
    UNIQUE (pattern_id, dimension)
);

CREATE INDEX idx_card_due ON card (due_at);
CREATE INDEX idx_card_pattern ON card (pattern_id);

CREATE TABLE session (
    id          INTEGER PRIMARY KEY,
    started_at  TEXT    NOT NULL,
    ended_at    TEXT,
    xp_earned   INTEGER NOT NULL DEFAULT 0,
    modes       TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX idx_session_started ON session (started_at);

-- One row per exercise shown, whatever the mode.
--
-- `seed` makes any instance exactly reproducible, which is what lets a review
-- re-show the problem you got wrong rather than a different one.
--
-- `chosen_pattern_id` is the load-bearing column for analytics: recording what
-- the user picked, not merely that they were wrong, is what turns "you are bad
-- at DP" into "you reach for DP when greedy would do".
CREATE TABLE attempt (
    id                INTEGER PRIMARY KEY,
    session_id        INTEGER REFERENCES session (id) ON DELETE SET NULL,
    pattern_id        TEXT    NOT NULL,
    problem_id        TEXT,
    seed              INTEGER NOT NULL,
    mode              TEXT    NOT NULL,
    difficulty        TEXT,
    correct           INTEGER NOT NULL DEFAULT 0 CHECK (correct IN (0, 1)),
    verdict           TEXT,
    chosen_pattern_id TEXT,
    hints_used        INTEGER NOT NULL DEFAULT 0 CHECK (hints_used >= 0),
    tries             INTEGER NOT NULL DEFAULT 1 CHECK (tries >= 1),
    duration_ms       INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    par_ms            INTEGER,
    xp_awarded        INTEGER NOT NULL DEFAULT 0,
    started_at        TEXT    NOT NULL,
    finished_at       TEXT
);

CREATE INDEX idx_attempt_pattern ON attempt (pattern_id, started_at);
CREATE INDEX idx_attempt_session ON attempt (session_id);
CREATE INDEX idx_attempt_started ON attempt (started_at);
CREATE INDEX idx_attempt_confusion ON attempt (pattern_id, chosen_pattern_id)
    WHERE chosen_pattern_id IS NOT NULL;

-- Append-only. FSRS's parameter optimiser needs the full review history, so
-- rows here are never updated or deleted, only inserted.
CREATE TABLE review_log (
    id             INTEGER PRIMARY KEY,
    card_id        INTEGER NOT NULL REFERENCES card (id) ON DELETE CASCADE,
    attempt_id     INTEGER REFERENCES attempt (id) ON DELETE SET NULL,
    rating         TEXT    NOT NULL CHECK (rating IN ('again', 'hard', 'good', 'easy')),
    reviewed_at    TEXT    NOT NULL,
    elapsed_days   REAL,
    scheduled_days REAL,
    mode           TEXT    NOT NULL,
    duration_ms    INTEGER
);

CREATE INDEX idx_review_card ON review_log (card_id, reviewed_at);
CREATE INDEX idx_review_time ON review_log (reviewed_at);

CREATE TABLE submission (
    id            INTEGER PRIMARY KEY,
    attempt_id    INTEGER NOT NULL REFERENCES attempt (id) ON DELETE CASCADE,
    source        TEXT    NOT NULL,
    verdict       TEXT    NOT NULL,
    tests_passed  INTEGER NOT NULL DEFAULT 0,
    tests_total   INTEGER NOT NULL DEFAULT 0,
    max_cpu_ms    INTEGER,
    max_memory_kb INTEGER,
    compile_log   TEXT    NOT NULL DEFAULT '',
    submitted_at  TEXT    NOT NULL
);

CREATE INDEX idx_submission_attempt ON submission (attempt_id);

-- The controlled vocabulary from domain.enums.MistakeCode. Free text cannot be
-- aggregated; this can, which is what makes "your most common mistake" real.
CREATE TABLE mistake (
    id          INTEGER PRIMARY KEY,
    attempt_id  INTEGER NOT NULL REFERENCES attempt (id) ON DELETE CASCADE,
    pattern_id  TEXT    NOT NULL,
    code        TEXT    NOT NULL,
    note        TEXT    NOT NULL DEFAULT '',
    observed_at TEXT    NOT NULL
);

CREATE INDEX idx_mistake_code ON mistake (code, observed_at);
CREATE INDEX idx_mistake_pattern ON mistake (pattern_id);

CREATE TABLE unlock (
    pattern_id  TEXT PRIMARY KEY,
    unlocked_at TEXT NOT NULL
);

-- kind: 'daily' | 'pattern' | 'solve' | 'perfect'
CREATE TABLE streak (
    kind        TEXT    PRIMARY KEY,
    current     INTEGER NOT NULL DEFAULT 0 CHECK (current >= 0),
    best        INTEGER NOT NULL DEFAULT 0 CHECK (best >= 0),
    last_day    TEXT
);

CREATE TABLE achievement (
    code        TEXT PRIMARY KEY,
    unlocked_at TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT ''
);
"""


MIGRATIONS: tuple[Migration, ...] = (Migration(1, "initial schema", _V1),)

LATEST_VERSION = max(m.version for m in MIGRATIONS)
