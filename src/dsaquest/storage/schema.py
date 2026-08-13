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


_V2 = """
-- What the student has been taught, and how fluent they are with it.
--
-- One row per (master, secret). The state machine is the teaching loop itself:
--
--   untaught -> taught -> drilling -> fluent -> tested
--
-- `fluent` is reached on evidence, not on a quota: consecutive correct drills
-- across enough distinct drill kinds. That is what lets the master shorten the
-- drilling for a student who clearly has it, and lengthen it for one who does
-- not, rather than dealing everyone the same ten questions.
CREATE TABLE lesson_progress (
    id                  INTEGER PRIMARY KEY,
    master_id           TEXT    NOT NULL,
    secret_id           TEXT    NOT NULL,
    state               TEXT    NOT NULL DEFAULT 'untaught'
                                CHECK (state IN ('untaught','taught','drilling','fluent','tested')),
    drills_seen         INTEGER NOT NULL DEFAULT 0 CHECK (drills_seen >= 0),
    drills_correct      INTEGER NOT NULL DEFAULT 0 CHECK (drills_correct >= 0),
    consecutive_correct INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_correct >= 0),
    taught_at           TEXT,
    fluent_at           TEXT,
    tested_at           TEXT,
    UNIQUE (master_id, secret_id)
);

CREATE INDEX idx_lesson_master ON lesson_progress (master_id);

-- Append-only log of every drill answered. Drives the adaptive drill count and
-- the master's memory of what you keep getting wrong.
CREATE TABLE drill_attempt (
    id           INTEGER PRIMARY KEY,
    master_id    TEXT    NOT NULL,
    secret_id    TEXT    NOT NULL,
    drill_id     TEXT    NOT NULL,
    kind         TEXT    NOT NULL,
    correct      INTEGER NOT NULL CHECK (correct IN (0, 1)),
    given        TEXT    NOT NULL DEFAULT '',
    duration_ms  INTEGER,
    attempted_at TEXT    NOT NULL
);

CREATE INDEX idx_drill_secret ON drill_attempt (master_id, secret_id, attempted_at);
CREATE INDEX idx_drill_id ON drill_attempt (drill_id);

-- Respect is per-master and never decays. See docs/game-design.md section 15:
-- a master forgetting your victories is not strict, it is broken.
CREATE TABLE respect (
    master_id  TEXT    PRIMARY KEY,
    points     INTEGER NOT NULL DEFAULT 0 CHECK (points >= 0),
    met_at     TEXT    NOT NULL,
    last_seen  TEXT    NOT NULL
);

-- Which dialogue lines a master has already spoken, so he does not repeat
-- himself. Not the master's memory of the student -- that is derived from the
-- event log -- only what has been said aloud.
CREATE TABLE character_memory (
    id         INTEGER PRIMARY KEY,
    master_id  TEXT NOT NULL,
    pool       TEXT NOT NULL,
    line_index INTEGER NOT NULL,
    spoken_at  TEXT NOT NULL,
    UNIQUE (master_id, pool, line_index)
);
"""


_V3 = """
-- Where the time went, per attempt. One total duration says a student was slow;
-- this says which part was slow, which is the only part that can be trained.
--
-- Rows exist only for the phases actually entered. `debug` in particular is
-- absent unless a submission failed, which is what makes its presence such a
-- sharp signal.
CREATE TABLE phase_timing (
    id         INTEGER PRIMARY KEY,
    attempt_id INTEGER NOT NULL REFERENCES attempt (id) ON DELETE CASCADE,
    phase      TEXT    NOT NULL
                       CHECK (phase IN ('recognise', 'plan', 'implement', 'debug')),
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    UNIQUE (attempt_id, phase)
);

CREATE INDEX idx_phase_attempt ON phase_timing (attempt_id);

-- The deadline in force and whether it was reached. Stored on the attempt so a
-- later change to the par table cannot retroactively rewrite whether a past
-- attempt timed out.
ALTER TABLE attempt ADD COLUMN limit_ms INTEGER;
ALTER TABLE attempt ADD COLUMN timed_out INTEGER NOT NULL DEFAULT 0;
ALTER TABLE attempt ADD COLUMN pressure_stage INTEGER;
"""


_V4 = """
-- The master's final test: all his secrets at once, nothing named.
--
-- Attempts are counted but never held against the student. Failing a final
-- test costs a little respect and nothing else; the remedy is more training,
-- which is the only thing that would actually help.
CREATE TABLE master_progress (
    master_id     TEXT    PRIMARY KEY,
    attempts      INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    passed        INTEGER NOT NULL DEFAULT 0 CHECK (passed IN (0, 1)),
    best_score    INTEGER,
    best_total    INTEGER,
    first_passed_at TEXT,
    last_attempt_at TEXT
);
"""


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "initial schema", _V1),
    Migration(2, "lessons, drills, respect, character memory", _V2),
    Migration(3, "phase timing and deadlines", _V3),
    Migration(4, "master final test", _V4),
)

LATEST_VERSION = max(m.version for m in MIGRATIONS)
