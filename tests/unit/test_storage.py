"""Storage layer: migrations, repositories, and the invariants they promise."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from dsaquest.domain.enums import Dimension, GameMode, MistakeCode, Rating, Verdict
from dsaquest.storage import repositories as repo
from dsaquest.storage.db import (
    DatabaseError,
    apply_migrations,
    connect,
    integrity_check,
    schema_version,
    transaction,
)
from dsaquest.storage.schema import LATEST_VERSION


@pytest.fixture
def conn():
    connection = connect(":memory:")
    repo.ensure_profile(connection)
    yield connection
    connection.close()


# --- migrations ---------------------------------------------------------------


def test_migrations_reach_latest_version(conn):
    assert schema_version(conn) == LATEST_VERSION


def test_migrations_are_idempotent(conn):
    before = schema_version(conn)
    apply_migrations(conn)
    apply_migrations(conn)
    assert schema_version(conn) == before
    assert integrity_check(conn) == []


def test_a_newer_database_is_refused_rather_than_corrupted(conn):
    conn.execute(f"PRAGMA user_version = {LATEST_VERSION + 5}")
    with pytest.raises(DatabaseError, match="only understands"):
        apply_migrations(conn)


def test_foreign_keys_are_actually_enforced(conn):
    with pytest.raises(Exception, match="FOREIGN KEY"):
        conn.execute(
            "INSERT INTO submission (attempt_id, source, verdict, submitted_at) "
            "VALUES (9999, 'x', 'AC', '2026-01-01T00:00:00+00:00')"
        )


def test_profile_cannot_have_a_second_row(conn):
    with pytest.raises(Exception, match="CHECK|UNIQUE|PRIMARY"):
        conn.execute("INSERT INTO profile (id, created_at) VALUES (2, '2026-01-01T00:00:00+00:00')")


# --- profile and XP -----------------------------------------------------------


def test_ensure_profile_is_idempotent(conn):
    first = repo.ensure_profile(conn)
    second = repo.ensure_profile(conn)
    assert first.created_at == second.created_at


def test_xp_accumulates(conn):
    assert repo.add_xp(conn, 25) == 25
    assert repo.add_xp(conn, 50) == 75


def test_xp_is_never_removed(conn):
    """Losing a Boss Fight costs time, not progress. Nothing may take XP away."""
    with pytest.raises(ValueError):
        repo.add_xp(conn, -10)


# --- cards --------------------------------------------------------------------


def test_ensure_cards_creates_three_dimensions_per_pattern(conn):
    repo.ensure_cards(conn, ["sliding-window", "prefix-sum"])
    cards = repo.cards_for(conn, "sliding-window")
    assert {c.dimension for c in cards} == set(Dimension)
    assert all(c.is_new for c in cards)


def test_ensure_cards_is_idempotent_so_new_content_needs_no_migration(conn):
    repo.ensure_cards(conn, ["sliding-window"])
    repo.ensure_cards(conn, ["sliding-window", "two-pointers"])
    assert len(repo.cards_for(conn, "sliding-window")) == 3
    assert len(repo.cards_for(conn, "two-pointers")) == 3


def test_due_cards_are_ordered_most_overdue_first(conn):
    repo.ensure_cards(conn, ["a", "b"])
    card_a = repo.get_card(conn, "a", Dimension.RECALL)
    card_b = repo.get_card(conn, "b", Dimension.RECALL)
    repo.update_card(
        conn,
        card_a.id,
        state="review",
        stability=1.0,
        difficulty=5.0,
        due_at="2026-01-05T00:00:00+00:00",
        last_review_at="2026-01-01T00:00:00+00:00",
        reps=1,
        lapses=0,
    )
    repo.update_card(
        conn,
        card_b.id,
        state="review",
        stability=1.0,
        difficulty=5.0,
        due_at="2026-01-02T00:00:00+00:00",
        last_review_at="2026-01-01T00:00:00+00:00",
        reps=1,
        lapses=0,
    )
    due = repo.due_cards(conn, now="2026-06-01T00:00:00+00:00")
    ordering = [(c.pattern_id, c.dimension) for c in due]
    assert ordering.index(("b", Dimension.RECALL)) < ordering.index(("a", Dimension.RECALL))


def test_due_cards_excludes_the_future(conn):
    repo.ensure_cards(conn, ["a"])
    card = repo.get_card(conn, "a", Dimension.RECOGNITION)
    repo.update_card(
        conn,
        card.id,
        state="review",
        stability=10.0,
        difficulty=5.0,
        due_at="2099-01-01T00:00:00+00:00",
        last_review_at="2026-01-01T00:00:00+00:00",
        reps=3,
        lapses=0,
    )
    due = repo.due_cards(conn, now="2026-06-01T00:00:00+00:00")
    assert ("a", Dimension.RECOGNITION) not in [(c.pattern_id, c.dimension) for c in due]


def test_review_log_is_appendable_and_linked(conn):
    repo.ensure_cards(conn, ["a"])
    card = repo.get_card(conn, "a", Dimension.IMPLEMENTATION)
    log_id = repo.log_review(conn, card_id=card.id, rating=Rating.GOOD, mode=GameMode.SOLVE)
    assert log_id > 0
    row = conn.execute("SELECT rating, mode FROM review_log WHERE id = ?", (log_id,)).fetchone()
    assert row["rating"] == "good" and row["mode"] == "solve"


# --- attempts and cascades ----------------------------------------------------


def _finished_attempt(conn, pattern="sliding-window", *, correct=True, chosen=None, seed=1):
    attempt_id = repo.start_attempt(conn, pattern_id=pattern, mode=GameMode.HUNTER, seed=seed)
    repo.finish_attempt(
        conn, attempt_id, correct=correct, chosen_pattern_id=chosen, duration_ms=4200
    )
    return attempt_id


def test_deleting_an_attempt_cascades_to_its_children(conn):
    attempt_id = _finished_attempt(conn)
    repo.record_submission(
        conn,
        attempt_id=attempt_id,
        source="int main(){}",
        verdict=Verdict.ACCEPTED,
        tests_passed=3,
        tests_total=3,
    )
    repo.record_mistake(
        conn,
        attempt_id=attempt_id,
        pattern_id="sliding-window",
        code=MistakeCode.INVARIANT_WINDOW_NOT_SHRUNK,
    )
    conn.execute("DELETE FROM attempt WHERE id = ?", (attempt_id,))
    assert conn.execute("SELECT COUNT(*) FROM submission").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM mistake").fetchone()[0] == 0


def test_accuracy_distinguishes_no_history_from_zero(conn):
    assert repo.accuracy(conn, "never-seen") is None
    _finished_attempt(conn, "prefix-sum", correct=False)
    assert repo.accuracy(conn, "prefix-sum") == 0.0


def test_median_duration_ignores_failed_attempts(conn):
    for ms, ok in ((1000, True), (3000, True), (99999, False)):
        attempt_id = repo.start_attempt(conn, pattern_id="p", mode=GameMode.SOLVE, seed=1)
        repo.finish_attempt(conn, attempt_id, correct=ok, duration_ms=ms)
    assert repo.median_duration_ms(conn, "p", GameMode.SOLVE) == 2000


def test_confusion_pairs_report_what_was_chosen_not_just_that_it_was_wrong(conn):
    for _ in range(3):
        _finished_attempt(conn, "prefix-sum", correct=False, chosen="sliding-window")
    _finished_attempt(conn, "prefix-sum", correct=False, chosen="two-pointers")
    _finished_attempt(conn, "prefix-sum", correct=True, chosen="prefix-sum")

    pairs = repo.confusion_pairs(conn)
    assert pairs[0] == ("prefix-sum", "sliding-window", 3)
    # A correct answer is not a confusion.
    assert all(chosen != actual for actual, chosen, _ in pairs)


def test_top_mistakes_survives_a_retired_code(conn):
    attempt_id = _finished_attempt(conn)
    repo.record_mistake(
        conn, attempt_id=attempt_id, pattern_id="p", code=MistakeCode.CPP_INT_OVERFLOW
    )
    conn.execute(
        "INSERT INTO mistake (attempt_id, pattern_id, code, observed_at) VALUES (?,?,?,?)",
        (attempt_id, "p", "CODE_THAT_NO_LONGER_EXISTS", "2026-01-01T00:00:00+00:00"),
    )
    codes = repo.top_mistakes(conn)
    assert (MistakeCode.CPP_INT_OVERFLOW, 1) in codes
    assert len(codes) == 1, "unknown codes must be skipped, not crash the stats screen"


# --- streaks ------------------------------------------------------------------


def test_streak_cannot_be_farmed_by_practising_twice_in_one_day(conn):
    today = date(2026, 8, 13)
    assert repo.touch_streak(conn, "daily", today=today).current == 1
    assert repo.touch_streak(conn, "daily", today=today).current == 1


def test_streak_increments_on_consecutive_days(conn):
    start = date(2026, 8, 13)
    for offset in range(4):
        streak = repo.touch_streak(conn, "daily", today=start + timedelta(days=offset))
    assert streak.current == 4
    assert streak.best == 4


def test_streak_resets_after_a_missed_day_but_best_is_kept(conn):
    start = date(2026, 8, 13)
    for offset in range(3):
        repo.touch_streak(conn, "daily", today=start + timedelta(days=offset))
    streak = repo.touch_streak(conn, "daily", today=start + timedelta(days=5))
    assert streak.current == 1
    assert streak.best == 3


def test_a_lapsed_streak_reads_as_zero_without_being_written_to(conn):
    """A streak last touched three days ago is broken, even though nothing wrote to it."""
    start = date(2026, 8, 13)
    repo.touch_streak(conn, "daily", today=start)
    assert repo.get_streak(conn, "daily", today=start + timedelta(days=1)).current == 1
    assert repo.get_streak(conn, "daily", today=start + timedelta(days=3)).current == 0
    assert repo.get_streak(conn, "daily", today=start + timedelta(days=3)).best == 1


def test_unknown_streak_is_zero_not_an_error(conn):
    assert repo.get_streak(conn, "perfect").current == 0


# --- unlocks and sessions -----------------------------------------------------


def test_unlock_reports_whether_it_was_newly_unlocked(conn):
    assert repo.unlock_pattern(conn, "two-pointers") is True
    assert repo.unlock_pattern(conn, "two-pointers") is False
    assert repo.unlocked_patterns(conn) == {"two-pointers"}


def test_session_totals_are_computed_from_its_attempts(conn):
    session_id = repo.start_session(conn)
    for xp in (10, 25):
        attempt_id = repo.start_attempt(
            conn, pattern_id="p", mode=GameMode.HUNTER, seed=1, session_id=session_id
        )
        repo.finish_attempt(conn, attempt_id, correct=True, xp_awarded=xp)
    repo.end_session(conn, session_id)

    row = conn.execute(
        "SELECT xp_earned, modes FROM session WHERE id = ?", (session_id,)
    ).fetchone()
    assert row["xp_earned"] == 35
    assert row["modes"] == "hunter"


def test_empty_session_does_not_produce_null_totals(conn):
    session_id = repo.start_session(conn)
    repo.end_session(conn, session_id)
    row = conn.execute(
        "SELECT xp_earned, modes FROM session WHERE id = ?", (session_id,)
    ).fetchone()
    assert row["xp_earned"] == 0
    assert row["modes"] == ""


def test_transaction_rolls_back_on_error(conn):
    with pytest.raises(RuntimeError, match="boom"), transaction(conn):
        repo.add_xp(conn, 100)
        raise RuntimeError("boom")
    assert repo.get_profile(conn).xp == 0
