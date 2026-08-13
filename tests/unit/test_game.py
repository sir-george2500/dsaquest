"""Game mechanics: the XP curve, the two multipliers, unlocks, achievements."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from dsaquest.content.loader import load_library
from dsaquest.domain.enums import Difficulty, Dimension, GameMode, MistakeCode, Rating, Verdict
from dsaquest.game import (
    MAX_LEVEL,
    ExerciseResult,
    award,
    base_xp,
    begin_exercise,
    complete_exercise,
    level_for_xp,
    levelled_up,
    lock_state,
    playable,
    progress,
    title_for_level,
    xp_to_next,
)
from dsaquest.game.achievements import ACHIEVEMENTS, Snapshot, evaluate
from dsaquest.game.xp import DUE_REVIEW_BONUS, REPEAT_FLOOR
from dsaquest.learning import apply_review, make_scheduler
from dsaquest.learning.mastery import all_mastery
from dsaquest.storage import repositories as repo
from dsaquest.storage.db import connect

T0 = datetime(2026, 8, 13, 9, 0, tzinfo=UTC)
TODAY = date(2026, 8, 13)


@pytest.fixture(scope="module")
def library():
    return load_library()


@pytest.fixture
def conn(library):
    connection = connect(":memory:")
    repo.ensure_profile(connection)
    repo.ensure_cards(connection, [p.id for p in library])
    yield connection
    connection.close()


@pytest.fixture
def scheduler():
    return make_scheduler(0.90, fuzz=False)


# --------------------------------------------------------------------------
# Levels
# --------------------------------------------------------------------------


def test_level_one_starts_at_zero_xp():
    assert level_for_xp(0) == 1


def test_levels_are_monotonic_and_each_costs_more_than_the_last():
    costs = [xp_to_next(n) for n in range(1, MAX_LEVEL)]
    assert costs == sorted(costs)
    assert costs[0] < costs[-1]


def test_level_never_exceeds_the_cap():
    assert level_for_xp(10**9) == MAX_LEVEL
    assert progress(10**9).is_max
    assert progress(10**9).fraction == 1.0


def test_xp_is_never_negative():
    with pytest.raises(ValueError):
        level_for_xp(-1)


def test_titles_persist_until_the_next_threshold():
    assert title_for_level(1) == "Novice"
    assert title_for_level(4) == "Novice"
    assert title_for_level(10) == "Pattern Hunter"
    assert title_for_level(12) == "Pattern Hunter"
    assert title_for_level(MAX_LEVEL) == "Algorithm Master"


def test_multiple_levels_can_be_crossed_by_one_award():
    """A big Boss award must celebrate every level it crosses, not just the last."""
    crossed = levelled_up(0, 10_000)
    assert len(crossed) > 1
    assert crossed == tuple(range(2, level_for_xp(10_000) + 1))


def test_progress_bar_reflects_position_within_the_level():
    at_floor = progress(0)
    assert at_floor.fraction == 0.0
    assert at_floor.bar(10).startswith("░") or at_floor.bar(10) == "░" * 10


# --------------------------------------------------------------------------
# XP rules
# --------------------------------------------------------------------------


def test_harder_problems_pay_more():
    easy = base_xp(GameMode.SOLVE, Difficulty.EASY)
    hard = base_xp(GameMode.SOLVE, Difficulty.HARD)
    boss = base_xp(GameMode.BOSS, Difficulty.BOSS)
    assert easy < hard < boss


def test_grinding_one_pattern_stops_paying():
    """Diminishing returns is what makes breadth the profitable strategy."""
    first = award(mode=GameMode.HUNTER, correct=True, repeats_today=0).total
    second = award(mode=GameMode.HUNTER, correct=True, repeats_today=1).total
    third = award(mode=GameMode.HUNTER, correct=True, repeats_today=2).total
    assert first > second > third


def test_repeat_decay_has_a_floor_so_drilling_is_not_worthless():
    deep = award(mode=GameMode.SOLVE, correct=True, repeats_today=20)
    assert deep.components[0].factor == REPEAT_FLOOR, "decay must clamp at the floor"
    # The award is an integer, so compare against the rounded product rather
    # than the exact real value.
    assert deep.total == round(base_xp(GameMode.SOLVE) * REPEAT_FLOOR)
    assert deep.total > 0


def test_due_reviews_are_worth_more_so_the_greedy_play_is_the_right_one():
    """The highest-scoring action must be the one the scheduler wants."""
    ordinary = award(mode=GameMode.SOLVE, correct=True).total
    due = award(mode=GameMode.SOLVE, correct=True, was_due=True).total
    assert due == pytest.approx(ordinary * DUE_REVIEW_BONUS, rel=0.02)


def test_a_due_review_beats_a_fresh_repeat_of_a_favourite_pattern():
    """The two multipliers must combine so that revision wins on the numbers."""
    grind_again = award(mode=GameMode.SOLVE, correct=True, repeats_today=2).total
    do_the_due_one = award(mode=GameMode.SOLVE, correct=True, was_due=True).total
    assert do_the_due_one > grind_again


def test_streak_bonus_is_capped():
    forever = award(mode=GameMode.SOLVE, correct=True, streak_days=10_000).total
    modest = award(mode=GameMode.SOLVE, correct=True, streak_days=30).total
    assert forever == modest


def test_a_failed_attempt_pays_effort_but_not_nothing():
    """Half an hour on a Boss and receiving zero teaches you to stop playing."""
    failed = award(mode=GameMode.BOSS, correct=False, difficulty=Difficulty.BOSS)
    assert 0 < failed.total < base_xp(GameMode.BOSS, Difficulty.BOSS)


def test_a_wrong_multiple_choice_pays_nothing():
    """No effort award where there was no real work — otherwise it is farmable."""
    assert award(mode=GameMode.HUNTER, correct=False).total == 0


def test_effort_awards_ignore_multipliers():
    plain = award(mode=GameMode.SOLVE, correct=False).total
    boosted = award(mode=GameMode.SOLVE, correct=False, was_due=True, streak_days=100).total
    assert plain == boosted


def test_perfect_boss_earns_a_flat_bonus():
    clean = award(
        mode=GameMode.BOSS, correct=True, difficulty=Difficulty.BOSS, tries=1, hints_used=0
    )
    messy = award(
        mode=GameMode.BOSS, correct=True, difficulty=Difficulty.BOSS, tries=2, hints_used=1
    )
    assert clean.flat_bonus > 0
    assert messy.flat_bonus == 0
    assert clean.total > messy.total


def test_award_explains_itself():
    explanation = award(mode=GameMode.SOLVE, correct=True, was_due=True, repeats_today=1).explain()
    assert "base" in explanation and "due" in explanation and "repeat" in explanation


def test_xp_is_never_negative_from_any_combination():
    for mode in GameMode:
        for correct in (True, False):
            result = award(mode=mode, correct=correct, repeats_today=99, streak_days=0)
            assert result.total >= 0


# --------------------------------------------------------------------------
# Unlocks
# --------------------------------------------------------------------------


def test_root_patterns_are_playable_immediately(conn, library, scheduler):
    mastery = all_mastery(conn, library, scheduler=scheduler, now=T0)
    open_now = playable(conn, library, mastery)
    assert "two-pointers" in open_now
    assert "binary-search" in open_now
    assert "sliding-window" not in open_now


def test_a_locked_pattern_explains_exactly_what_it_needs(conn, library, scheduler):
    mastery = all_mastery(conn, library, scheduler=scheduler, now=T0)
    state = lock_state(library, mastery, "sliding-window")
    assert not state.unlocked
    assert {pattern_id for pattern_id, _ in state.blockers} == {
        "two-pointers",
        "hashing-frequency",
    }
    assert "two-pointers" in state.explain()


def test_unlocking_is_permanent_even_if_the_prerequisite_decays(conn, library, scheduler):
    """Taking back access because you forgot something would punish honesty."""
    at = T0
    for dimension in Dimension:
        for pattern_id in ("two-pointers", "hashing-frequency"):
            card_at = T0
            for _ in range(6):
                card = apply_review(
                    conn,
                    repo.get_card(conn, pattern_id, dimension),
                    Rating.GOOD,
                    scheduler=scheduler,
                    mode=GameMode.SOLVE,
                    now=card_at,
                )
                card_at = datetime.fromisoformat(card.due_at)
            at = max(at, card_at)

    from dsaquest.game import refresh_unlocks

    mastery = all_mastery(conn, library, scheduler=scheduler, now=at)
    assert "sliding-window" in refresh_unlocks(conn, library, mastery)

    far_future = at + timedelta(days=3650)
    decayed = all_mastery(conn, library, scheduler=scheduler, now=far_future)
    assert "sliding-window" in playable(conn, library, decayed)


# --------------------------------------------------------------------------
# Achievements
# --------------------------------------------------------------------------


def _snapshot(**overrides) -> Snapshot:
    base = dict(
        level=1,
        xp=0,
        daily_streak=0,
        best_daily_streak=0,
        patterns_started=0,
        patterns_mastered=0,
        patterns_total=6,
        implementations_passed=0,
        perfect_bosses=0,
        sessions=0,
        recovered_lapses=0,
        fastest_solve_ratio=None,
    )
    base.update(overrides)
    return Snapshot(**base)


def test_nothing_is_earned_from_an_empty_snapshot(conn):
    assert evaluate(conn, _snapshot()) == ()


def test_achievements_are_awarded_once(conn):
    first = evaluate(conn, _snapshot(implementations_passed=1))
    assert [a.code for a in first] == ["FIRST_BLOOD"]
    assert evaluate(conn, _snapshot(implementations_passed=5)) == ()


def test_completionist_needs_every_pattern(conn):
    codes = {a.code for a in evaluate(conn, _snapshot(patterns_mastered=6, patterns_total=6))}
    assert "COMPLETIONIST" in codes


def test_completionist_is_not_awarded_on_an_empty_library(conn):
    """patterns_total == 0 must not vacuously satisfy 'master everything'."""
    codes = {a.code for a in evaluate(conn, _snapshot(patterns_mastered=0, patterns_total=0))}
    assert "COMPLETIONIST" not in codes


def test_every_achievement_has_a_distinct_code():
    codes = [a.code for a in ACHIEVEMENTS]
    assert len(codes) == len(set(codes))


# --------------------------------------------------------------------------
# Recording a full exercise
# --------------------------------------------------------------------------


def test_recording_an_exercise_moves_every_subsystem(conn, library, scheduler):
    attempt_id = begin_exercise(
        conn, pattern_id="two-pointers", mode=GameMode.SOLVE, seed=7, difficulty=Difficulty.MEDIUM
    )
    outcome = complete_exercise(
        conn,
        attempt_id,
        ExerciseResult(
            correct=True,
            duration_ms=200_000,
            verdict=Verdict.ACCEPTED,
            source="int main(){}",
            tests_passed=3,
            tests_total=3,
        ),
        library=library,
        scheduler=scheduler,
        pattern_id="two-pointers",
        mode=GameMode.SOLVE,
        now=T0,
        today=TODAY,
    )

    assert outcome.xp.total > 0
    assert outcome.xp_total == outcome.xp.total
    assert outcome.rating is not None
    assert outcome.card is not None and outcome.card.reps == 1
    assert outcome.streak.current == 1
    assert outcome.level.level >= 1
    assert conn.execute("SELECT COUNT(*) FROM submission").fetchone()[0] == 1


def test_a_judge_failure_records_the_attempt_but_not_a_review(conn, library, scheduler):
    """Our bug costs the learner nothing — no lapse, no schedule change."""
    attempt_id = begin_exercise(conn, pattern_id="two-pointers", mode=GameMode.SOLVE, seed=1)
    outcome = complete_exercise(
        conn,
        attempt_id,
        ExerciseResult(correct=False, duration_ms=1000, verdict=Verdict.INTERNAL_ERROR),
        library=library,
        scheduler=scheduler,
        pattern_id="two-pointers",
        mode=GameMode.SOLVE,
        now=T0,
        today=TODAY,
    )
    assert outcome.rating is None
    assert outcome.card is None
    assert repo.get_card(conn, "two-pointers", Dimension.IMPLEMENTATION).reps == 0
    assert conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0] == 0


def test_mistakes_are_recorded_against_the_attempt(conn, library, scheduler):
    attempt_id = begin_exercise(conn, pattern_id="sliding-window", mode=GameMode.SOLVE, seed=3)
    complete_exercise(
        conn,
        attempt_id,
        ExerciseResult(
            correct=False,
            duration_ms=500_000,
            verdict=Verdict.WRONG_ANSWER,
            mistakes=(MistakeCode.INVARIANT_WINDOW_NOT_SHRUNK,),
        ),
        library=library,
        scheduler=scheduler,
        pattern_id="sliding-window",
        mode=GameMode.SOLVE,
        now=T0,
        today=TODAY,
    )
    assert repo.top_mistakes(conn)[0][0] is MistakeCode.INVARIANT_WINDOW_NOT_SHRUNK


def test_a_wrong_recognition_answer_records_what_was_chosen(conn, library, scheduler):
    attempt_id = begin_exercise(conn, pattern_id="prefix-sum", mode=GameMode.HUNTER, seed=5)
    complete_exercise(
        conn,
        attempt_id,
        ExerciseResult(correct=False, duration_ms=30_000, chosen_pattern_id="sliding-window"),
        library=library,
        scheduler=scheduler,
        pattern_id="prefix-sum",
        mode=GameMode.HUNTER,
        now=T0,
        today=TODAY,
    )
    assert repo.confusion_pairs(conn) == [("prefix-sum", "sliding-window", 1)]


def test_repeating_a_pattern_in_one_day_earns_less_each_time(conn, library, scheduler):
    """The repeat decay, counted against the day the attempts were actually written.

    `today` is taken from the clock rather than pinned. `begin_exercise` stamps
    `started_at` with the real time and takes no `now`, so a pinned TODAY only
    agrees with the rows on the one day it happens to name — this asserted
    nothing at all from the moment that date passed, and said so by failing at
    midnight rather than the day the mistake was made.
    """
    today = datetime.now(UTC).astimezone().date()
    totals = []
    for i in range(3):
        attempt_id = begin_exercise(conn, pattern_id="two-pointers", mode=GameMode.HUNTER, seed=i)
        outcome = complete_exercise(
            conn,
            attempt_id,
            ExerciseResult(correct=True, duration_ms=40_000),
            library=library,
            scheduler=scheduler,
            pattern_id="two-pointers",
            mode=GameMode.HUNTER,
            now=T0,
            today=today,
        )
        totals.append(outcome.xp.total)
    assert totals[0] > totals[1] > totals[2]
