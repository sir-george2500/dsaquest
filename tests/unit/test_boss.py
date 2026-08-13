"""Boss fights: the gate, the phase machine, health, enrage and victory tiers."""

from __future__ import annotations

import pytest

from dsaquest.boss import (
    conclude,
    gate_status,
    next_challenge,
    open_fight,
    resolve,
    target_ms,
    victory_grade,
)
from dsaquest.boss.loader import load_bosses
from dsaquest.content.lessons import load_curricula
from dsaquest.content.loader import load_library
from dsaquest.content.problems import load_problems
from dsaquest.domain.boss import PhaseKind
from dsaquest.domain.enums import Dimension, GameMode, Rating
from dsaquest.learning import apply_review, make_scheduler
from dsaquest.learning.mastery import all_mastery
from dsaquest.storage import repositories as repo
from dsaquest.storage.db import connect

BOSS_ID = "the-array-beast"


@pytest.fixture(scope="module")
def library():
    return load_library()


@pytest.fixture(scope="module")
def bank(library):
    return load_problems(library)


@pytest.fixture(scope="module")
def bosses(library, bank):
    return load_bosses(library, load_curricula(library, bank), bank)


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


def _mastery(conn, library, scheduler):
    return all_mastery(conn, library, scheduler=scheduler)


# --------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------


def test_every_boss_can_actually_be_beaten(bosses):
    """Phases must be able to remove all of the boss's health."""
    for boss in bosses:
        assert boss.total_damage >= boss.boss_hp, boss.id


def test_no_boss_ends_on_a_single_mistake(bosses):
    """A fight you lose to one wrong answer is a coin flip, not a test."""
    for boss in bosses:
        assert boss.player_hp > boss.damage_taken, boss.id


def test_every_boss_asks_the_learner_to_recognise_something(bosses):
    for boss in bosses:
        kinds = {p.kind for p in boss.phases}
        assert kinds & {PhaseKind.RECOGNISE, PhaseKind.SURVIVE}, boss.id


def test_a_boss_only_draws_on_patterns_its_master_teaches(bosses, library, bank):
    curricula = load_curricula(library, bank)
    for boss in bosses:
        governed = set(curricula[boss.master_id].patterns)
        assert set(boss.patterns) <= governed, boss.id


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


def test_the_gate_is_shut_on_a_fresh_profile(conn, library, scheduler, bosses):
    status = gate_status(conn, bosses[BOSS_ID], _mastery(conn, library, scheduler))
    assert not status.open
    assert status.blockers


def test_the_gate_names_every_missing_requirement(conn, library, scheduler, bosses):
    status = gate_status(conn, bosses[BOSS_ID], _mastery(conn, library, scheduler))
    assert "the master's final test" in status.blockers
    assert all(not r.met for r in status.requirements)


def test_the_gate_uses_the_weakest_pattern_not_the_average(conn, library, scheduler, bosses):
    """A boss composing four patterns is not survivable on three."""
    boss = bosses[BOSS_ID]
    strong, weak = boss.patterns[0], boss.patterns[1]
    for dimension in Dimension:
        for _ in range(10):
            card = repo.get_card(conn, strong, dimension)
            apply_review(conn, card, Rating.EASY, scheduler=scheduler, mode=GameMode.SOLVE)

    status = gate_status(conn, boss, _mastery(conn, library, scheduler))
    assert not status.open, f"{weak} is untouched; the gate must not open"


def test_passing_the_final_test_alone_is_not_enough(conn, library, scheduler, bosses):
    repo.record_final_test(conn, "master_arrays", score=6, total=6, passed=True)
    status = gate_status(conn, bosses[BOSS_ID], _mastery(conn, library, scheduler))
    assert status.final_test_passed
    assert not status.open, "mastery must have held, not merely been demonstrated once"


# --------------------------------------------------------------------------
# The fight
# --------------------------------------------------------------------------


def _fight_through(conn, library, bank, scheduler, boss, *, clear: list[bool]):
    fight = open_fight(boss)
    for index, should_clear in enumerate(clear):
        challenge = next_challenge(conn, library, bank, fight, seed=index + 1)
        if challenge is None:
            break
        if challenge.kind in (PhaseKind.RECOGNISE, PhaseKind.SURVIVE):
            assert challenge.hunter is not None
            answer = (
                challenge.hunter.correct_index
                if should_clear
                else (challenge.hunter.correct_index + 1) % len(challenge.hunter.options)
            )
        elif challenge.kind is PhaseKind.EXPLAIN:
            pattern = library[challenge.pattern_id]
            answer = (
                " ".join(phrase for point in pattern.recall_rubric for phrase in point.accepts[:1])
                if should_clear
                else "no idea"
            )
        else:
            answer = should_clear
        resolve(conn, library, fight, answer, scheduler=scheduler)
    return fight


def test_clearing_every_phase_defeats_the_boss(conn, library, bank, scheduler, bosses):
    boss = bosses[BOSS_ID]
    fight = _fight_through(conn, library, bank, scheduler, boss, clear=[True] * 4)

    assert fight.won
    assert fight.boss_hp == 0
    assert fight.player_hp == boss.player_hp
    assert fight.flawless


def test_a_mistake_costs_health_without_ending_the_fight(conn, library, bank, scheduler, bosses):
    boss = bosses[BOSS_ID]
    fight = _fight_through(conn, library, bank, scheduler, boss, clear=[False, True, True, True])

    assert fight.player_hp == boss.player_hp - boss.damage_taken
    assert len(fight.outcomes) == 4, "one failure must not end the attempt"
    assert not fight.won, "a missed phase leaves the boss standing"


def test_enrage_fires_on_repeated_failure_and_removes_hints(conn, library, bank, scheduler, bosses):
    boss = bosses[BOSS_ID]
    fight = _fight_through(conn, library, bank, scheduler, boss, clear=[False, False, True, True])

    assert fight.enraged
    assert not fight.hints_allowed


def test_enrage_never_shortens_the_clock(conn, library, bank, scheduler, bosses):
    """Accelerating a timer punishes thinking, which is what it should teach.

    Compared per phase *kind*: recognise and explain have different pars, so
    comparing one phase's budget with the next says nothing. What matters is
    that the same kind of challenge gets the same clock enraged or not.
    """
    from dsaquest.domain.enums import Difficulty
    from dsaquest.timing import PressureStage, budget_for

    boss = bosses[BOSS_ID]
    fight = open_fight(boss)

    calm = {
        mode: budget_for(conn, mode, Difficulty.MEDIUM, stage=PressureStage.BOSS).limit_ms
        for mode in (GameMode.HUNTER, GameMode.RECALL, GameMode.COMPLETE)
    }

    for seed in (1, 2):
        next_challenge(conn, library, bank, fight, seed=seed)
        resolve(conn, library, fight, None, scheduler=scheduler)
    assert fight.enraged

    for mode, limit in calm.items():
        enraged = budget_for(conn, mode, Difficulty.MEDIUM, stage=PressureStage.BOSS).limit_ms
        assert enraged == limit, f"{mode.value} lost time to enrage"


def test_running_out_of_health_ends_the_attempt(conn, library, bank, scheduler, bosses):
    boss = bosses[BOSS_ID]
    fight = _fight_through(conn, library, bank, scheduler, boss, clear=[False] * 4)

    assert fight.player_hp == 0
    assert not fight.won
    assert fight.over


# --------------------------------------------------------------------------
# Victory tiers
# --------------------------------------------------------------------------


def test_a_flawless_fight_is_perfect(conn, library, bank, scheduler, bosses):
    fight = _fight_through(conn, library, bank, scheduler, bosses[BOSS_ID], clear=[True] * 4)
    target = target_ms(fight)
    assert victory_grade(fight, target, target) == "perfect"


def test_a_fast_flawless_fight_is_legendary(conn, library, bank, scheduler, bosses):
    fight = _fight_through(conn, library, bank, scheduler, bosses[BOSS_ID], clear=[True] * 4)
    target = target_ms(fight)
    assert victory_grade(fight, int(target * 0.5), target) == "legendary"


def test_a_standing_boss_earns_no_grade(conn, library, bank, scheduler, bosses):
    fight = _fight_through(
        conn, library, bank, scheduler, bosses[BOSS_ID], clear=[True, True, True, False]
    )
    assert victory_grade(fight, 1, target_ms(fight)) is None


def test_victory_pays_respect_and_defeat_costs_little(conn, library, bank, scheduler, bosses):
    boss = bosses[BOSS_ID]
    won = _fight_through(conn, library, bank, scheduler, boss, clear=[True] * 4)
    verdict = conclude(conn, won, seed=1)

    assert verdict.won
    assert verdict.respect_delta > 0
    assert verdict.record.defeated
    assert verdict.line

    lost = _fight_through(conn, library, bank, scheduler, boss, clear=[False] * 4)
    loss = conclude(conn, lost, seed=2)
    assert not loss.won
    assert loss.respect_delta < 0
    assert abs(loss.respect_delta) < verdict.respect_delta, "failing must cost far less"
    assert loss.record.defeated, "a later defeat cannot un-defeat the boss"


def test_a_defeat_names_what_to_train(conn, library, bank, scheduler, bosses):
    fight = _fight_through(conn, library, bank, scheduler, bosses[BOSS_ID], clear=[False] * 4)
    verdict = conclude(conn, fight, seed=3)
    assert verdict.weakest


def test_a_scrappy_rematch_cannot_lower_a_perfect(conn, library, bank, scheduler, bosses):
    boss = bosses[BOSS_ID]
    conclude(conn, _fight_through(conn, library, bank, scheduler, boss, clear=[True] * 4), seed=1)
    best = repo.get_boss_record(conn, boss.id).best_grade

    conclude(
        conn,
        _fight_through(conn, library, bank, scheduler, boss, clear=[False, True, True, True]),
        seed=2,
    )
    assert repo.get_boss_record(conn, boss.id).best_grade == best
