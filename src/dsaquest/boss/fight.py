"""Running a boss fight.

The fight is a phase machine. Each phase builds a concrete challenge out of a
mode the learner already knows, judges it, and moves the two health bars. What
makes it a boss rather than a session is that nothing is named, the phases
compose, and a mistake costs something without ending the attempt.

Health is drama and scoring. The thing that actually decides whether a learner
is allowed to be here is the gate, and the gate is checked before the arena
opens — see :func:`gate_status`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fsrs import Scheduler

from ..content.loader import PatternLibrary
from ..content.problems import ProblemBank
from ..domain.boss import Boss, BossPhase, PhaseKind
from ..domain.enums import Difficulty, GameMode
from ..domain.problem import Problem
from ..game.modes.hunter import HunterRound, build_round, confusion_counts, judge_round
from ..game.modes.recall import RecallRound, auto_match
from ..game.modes.recall import build_round as build_recall
from ..game.modes.recall import grade as grade_recall
from ..game.session import ExerciseResult, begin_exercise, complete_exercise
from ..learning.mastery import PatternMastery
from ..storage import repositories as repo
from ..timing import Phase, PhaseTiming, PressureStage, Stopwatch, TimeBudget, budget_for

RESPECT_BOSS_VICTORY = 100
RESPECT_BOSS_DEFEAT = -3

#: A victory is Legendary only under this fraction of the target time.
LEGENDARY_PACE = 0.7


@dataclass(frozen=True, slots=True)
class Requirement:
    name: str
    needed: float
    actual: float

    @property
    def met(self) -> bool:
        return self.actual >= self.needed

    def describe(self) -> str:
        mark = "✓" if self.met else "✗"
        return f"{self.name:<16}{self.actual:>5.0%} of {self.needed:.0%}  {mark}"


@dataclass(frozen=True, slots=True)
class GateStatus:
    requirements: tuple[Requirement, ...]
    final_test_needed: bool
    final_test_passed: bool

    @property
    def open(self) -> bool:
        if self.final_test_needed and not self.final_test_passed:
            return False
        return all(r.met for r in self.requirements)

    @property
    def blockers(self) -> tuple[str, ...]:
        missing = [r.name for r in self.requirements if not r.met]
        if self.final_test_needed and not self.final_test_passed:
            missing.append("the master's final test")
        return tuple(missing)


@dataclass(frozen=True, slots=True)
class Challenge:
    """One phase, made concrete."""

    phase: BossPhase
    number: int
    total: int
    budget: TimeBudget
    attempt_id: int
    watch: Stopwatch
    pattern_id: str
    problem: Problem | None = None
    hunter: HunterRound | None = None
    recall: RecallRound | None = None
    template_file: str | None = None
    hole_id: str | None = None

    @property
    def kind(self) -> PhaseKind:
        return self.phase.kind


@dataclass(frozen=True, slots=True)
class PhaseOutcome:
    challenge: Challenge
    cleared: bool
    timed_out: bool
    detail: str


@dataclass(slots=True)
class Fight:
    boss: Boss
    boss_hp: int
    player_hp: int
    index: int = 0
    hints_used: int = 0
    failures: int = 0
    outcomes: list[PhaseOutcome] = field(default_factory=list)
    current: Challenge | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_phases(self) -> int:
        return len(self.boss.phases)

    @property
    def enraged(self) -> bool:
        """Removes hints and doubles what is at stake. Never touches the clock."""
        return self.failures >= self.boss.enrage_after

    @property
    def hints_allowed(self) -> bool:
        return not self.enraged

    @property
    def over(self) -> bool:
        return self.boss_hp <= 0 or self.player_hp <= 0 or self.index >= self.total_phases

    @property
    def won(self) -> bool:
        return self.boss_hp <= 0 and self.player_hp > 0

    @property
    def flawless(self) -> bool:
        return self.failures == 0

    def elapsed_ms(self) -> int:
        return int((datetime.now(UTC) - self.started_at).total_seconds() * 1000)


@dataclass(frozen=True, slots=True)
class FightVerdict:
    won: bool
    grade: str | None
    boss_hp: int
    player_hp: int
    duration_ms: int
    target_ms: int
    line: str
    respect_delta: int
    respect_total: int
    record: repo.BossRecord
    weakest: tuple[str, ...]


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


def gate_status(
    conn: sqlite3.Connection, boss: Boss, mastery: dict[str, PatternMastery]
) -> GateStatus:
    """Whether the learner has earned the right to fight.

    Measured across every pattern the boss draws from, using the *weakest* of
    them: a boss that composes four patterns is not survivable on three.
    """
    relevant = [mastery[p] for p in boss.patterns if p in mastery]

    def weakest(getter) -> float:
        return min((getter(m) for m in relevant), default=0.0)

    requirements = tuple(
        Requirement(name, needed, actual)
        for (name, needed), actual in zip(
            boss.gate.as_pairs(),
            (
                weakest(lambda m: m.recognition.score),
                weakest(lambda m: m.recall.score),
                weakest(lambda m: m.implementation.score),
                weakest(lambda m: m.retention),
            ),
            strict=True,
        )
        if needed > 0
    )

    progress = repo.get_master_progress(conn, boss.master_id)
    return GateStatus(
        requirements=requirements,
        final_test_needed=boss.gate.master_final_test,
        final_test_passed=progress.passed,
    )


# --------------------------------------------------------------------------
# Running the fight
# --------------------------------------------------------------------------


def open_fight(boss: Boss) -> Fight:
    return Fight(boss=boss, boss_hp=boss.boss_hp, player_hp=boss.player_hp)


def _pattern_for(fight: Fight, phase: BossPhase, seed: int) -> str:
    if phase.pattern:
        return phase.pattern
    patterns = fight.boss.patterns
    return patterns[seed % len(patterns)]


def next_challenge(
    conn: sqlite3.Connection,
    library: PatternLibrary,
    bank: ProblemBank,
    fight: Fight,
    *,
    seed: int,
) -> Challenge | None:
    """Build the next phase, or None when the fight is decided."""
    if fight.over:
        fight.current = None
        return None

    phase = fight.boss.phases[fight.index]
    pattern_id = _pattern_for(fight, phase, seed)
    difficulty = Difficulty.HARD if fight.boss.tier >= 3 else Difficulty.MEDIUM

    mode = GameMode.RECALL if phase.kind is PhaseKind.EXPLAIN else GameMode.HUNTER
    if phase.kind is PhaseKind.IMPLEMENT:
        mode = GameMode.COMPLETE

    budget = budget_for(conn, mode, difficulty, stage=PressureStage.BOSS)
    attempt_id = begin_exercise(
        conn,
        pattern_id=pattern_id,
        mode=mode,
        seed=seed,
        difficulty=difficulty,
    )
    watch = Stopwatch()
    watch.start(Phase.RECOGNISE)

    hunter = recall = problem = template_file = hole_id = None

    if phase.kind in (PhaseKind.RECOGNISE, PhaseKind.SURVIVE):
        candidates = bank.for_pattern(pattern_id)
        if not candidates:
            raise LookupError(f"{pattern_id} has no problems for a boss phase")
        problem = candidates[seed % len(candidates)]
        hunter = build_round(
            library, problem, seed=seed, history=confusion_counts(conn, pattern_id)
        )
    elif phase.kind is PhaseKind.EXPLAIN:
        recall = build_recall(library[pattern_id])
    else:
        from ..content.paths import read_template
        from ..game.modes.complete import parse_holes

        template_file = library[pattern_id].template_file
        holes = parse_holes(read_template(template_file))
        hole_id = holes[seed % len(holes)].id

    fight.current = Challenge(
        phase=phase,
        number=fight.index + 1,
        total=fight.total_phases,
        budget=budget,
        attempt_id=attempt_id,
        watch=watch,
        pattern_id=pattern_id,
        problem=problem,
        hunter=hunter,
        recall=recall,
        template_file=template_file,
        hole_id=hole_id,
    )
    return fight.current


def resolve(
    conn: sqlite3.Connection,
    library: PatternLibrary,
    fight: Fight,
    answer: object,
    *,
    scheduler: Scheduler,
) -> PhaseOutcome:
    """Judge the open phase and move both health bars.

    ``answer`` is an option index for recognition phases, free text for an
    explanation, and the filled hole for an implementation. ``None`` always
    means the clock ran out.
    """
    live = fight.current
    assert live is not None, "no phase is open"

    live.watch.stop()
    timing = PhaseTiming.from_stopwatch(live.watch)
    elapsed = live.watch.elapsed_ms
    timed_out = answer is None or live.budget.expired(elapsed)

    cleared = False
    detail = ""
    chosen: str | None = None

    if timed_out:
        detail = "the clock ran out"
    elif live.kind in (PhaseKind.RECOGNISE, PhaseKind.SURVIVE):
        assert live.hunter is not None
        feedback = judge_round(library, live.hunter, int(answer))  # type: ignore[arg-type]
        cleared = feedback.correct
        chosen = feedback.chosen_pattern_id
        detail = feedback.tell or feedback.why
    elif live.kind is PhaseKind.EXPLAIN:
        assert live.recall is not None
        text = str(answer)
        outcome = grade_recall(live.recall, text, auto_match(live.recall, text))
        cleared = outcome.correct
        detail = f"{outcome.credited}/{outcome.total} points"
    else:
        # Implementation is judged by the caller, which owns the sandbox; it
        # passes a bool through so the fight stays free of judge plumbing.
        cleared = bool(answer)
        detail = "accepted" if cleared else "rejected"

    mode = (
        GameMode.RECALL
        if live.kind is PhaseKind.EXPLAIN
        else GameMode.COMPLETE
        if live.kind is PhaseKind.IMPLEMENT
        else GameMode.HUNTER
    )
    complete_exercise(
        conn,
        live.attempt_id,
        ExerciseResult(
            correct=cleared,
            duration_ms=elapsed,
            chosen_pattern_id=chosen,
            timed_out=timed_out,
            phase_breakdown={p.value: ms for p, ms in timing.breakdown.items()},
            limit_ms=live.budget.limit_ms,
            pressure_stage=int(PressureStage.BOSS),
        ),
        library=library,
        scheduler=scheduler,
        pattern_id=live.pattern_id,
        mode=mode,
        difficulty=Difficulty.HARD if fight.boss.tier >= 3 else Difficulty.MEDIUM,
    )

    if cleared:
        fight.boss_hp = max(0, fight.boss_hp - live.phase.damage)
    else:
        fight.failures += 1
        fight.player_hp = max(0, fight.player_hp - fight.boss.damage_taken)

    outcome = PhaseOutcome(challenge=live, cleared=cleared, timed_out=timed_out, detail=detail)
    fight.outcomes.append(outcome)
    fight.index += 1
    fight.current = None
    return outcome


def target_ms(fight: Fight) -> int:
    """What a clean fight should take: the sum of every phase's par."""
    from ..learning.par import par_ms

    difficulty = Difficulty.HARD if fight.boss.tier >= 3 else Difficulty.MEDIUM
    total = 0
    for phase in fight.boss.phases:
        mode = (
            GameMode.RECALL
            if phase.kind is PhaseKind.EXPLAIN
            else GameMode.COMPLETE
            if phase.kind is PhaseKind.IMPLEMENT
            else GameMode.HUNTER
        )
        total += par_ms(mode, difficulty)
    return total


def victory_grade(fight: Fight, duration_ms: int, target: int) -> str | None:
    """Normal, Strong, Perfect or Legendary — or None if the boss stands."""
    if not fight.won:
        return None
    if fight.flawless and fight.hints_used == 0:
        if duration_ms <= target * LEGENDARY_PACE:
            return "legendary"
        return "perfect"
    if fight.hints_used <= 1 and fight.failures <= 1:
        return "strong"
    return "normal"


def conclude(conn: sqlite3.Connection, fight: Fight, *, seed: int) -> FightVerdict:
    from random import Random

    duration = fight.elapsed_ms()
    target = target_ms(fight)
    grade = victory_grade(fight, duration, target)
    won = fight.won

    record = repo.record_boss_fight(
        conn,
        fight.boss.id,
        won=won,
        grade=grade,
        duration_ms=duration,
        hp_left=fight.player_hp,
        hints_used=fight.hints_used,
    )

    delta = RESPECT_BOSS_VICTORY if won else RESPECT_BOSS_DEFEAT
    if fight.enraged:
        # Enrage doubles what is at stake in both directions.
        delta *= 2
    respect_total = repo.add_respect(conn, fight.boss.master_id, delta)

    if won and grade in ("perfect", "legendary"):
        pool = "perfect"
    elif won and record.attempts > 1:
        pool = "rematch"
    elif won:
        pool = "victory"
    else:
        pool = "defeat"

    lines = fight.boss.pool(pool) or fight.boss.pool("defeat") or ("...",)
    line = lines[Random(seed).randrange(len(lines))]

    weakest = tuple(dict.fromkeys(o.challenge.pattern_id for o in fight.outcomes if not o.cleared))

    return FightVerdict(
        won=won,
        grade=grade,
        boss_hp=fight.boss_hp,
        player_hp=fight.player_hp,
        duration_ms=duration,
        target_ms=target,
        line=line,
        respect_delta=delta,
        respect_total=respect_total,
        record=record,
        weakest=weakest,
    )
