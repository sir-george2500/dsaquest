"""Mode A — Pattern Hunter.

Show a statement with no label and ask which pattern it is. This is the mode
the whole application exists for.

The distractors are the entire difficulty of the exercise. Drawn at random from
33 patterns, the question is trivial — "graph BFS" next to "sliding window" on
an array problem answers itself. Drawn from the correct pattern's
``confusable_with`` graph, the learner has to actually discriminate.

Two refinements on top of that:

* **Distractors adapt to you.** Patterns you have personally mistaken for this
  one before are drawn first, so your own wrong answers make later rounds
  harder. The confusion matrix that drives this is a plain query over
  ``attempt.chosen_pattern_id`` — no bookkeeping required.
* **Wrong answers explain themselves with the discriminator.** Choosing
  ``prefix-sum`` on a sliding-window problem returns the *tell* the pattern
  library already stores for that exact pair, which is a specific question you
  can ask next time — not "wrong, it was sliding window".

Everything is deterministic in ``seed`` so an attempt can be replayed exactly.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from random import Random

from ...content.loader import PatternLibrary
from ...content.problems import ProblemBank
from ...domain.enums import Difficulty
from ...domain.problem import Problem

DEFAULT_CHOICES = 4


@dataclass(frozen=True, slots=True)
class HunterOption:
    pattern_id: str
    name: str


@dataclass(frozen=True, slots=True)
class HunterRound:
    problem: Problem
    options: tuple[HunterOption, ...]
    correct_index: int
    seed: int

    @property
    def correct_option(self) -> HunterOption:
        return self.options[self.correct_index]

    def option_index(self, pattern_id: str) -> int | None:
        for index, option in enumerate(self.options):
            if option.pattern_id == pattern_id:
                return index
        return None

    def labelled(self) -> tuple[tuple[str, HunterOption], ...]:
        """Options paired with A/B/C/D labels for display."""
        return tuple((chr(ord("A") + index), option) for index, option in enumerate(self.options))


@dataclass(frozen=True, slots=True)
class HunterFeedback:
    correct: bool
    chosen_pattern_id: str
    actual_pattern_id: str
    why: str
    signals: tuple[str, ...]
    tell: str
    """The discriminator for this specific confusion, when the library has one."""
    classic_ref: str

    @property
    def has_tell(self) -> bool:
        return bool(self.tell)


def confusion_counts(conn: sqlite3.Connection, pattern_id: str) -> dict[str, int]:
    """How often this learner has picked each wrong pattern for ``pattern_id``."""
    rows = conn.execute(
        """
        SELECT chosen_pattern_id, COUNT(*) AS n
          FROM attempt
         WHERE pattern_id = ?
           AND chosen_pattern_id IS NOT NULL
           AND chosen_pattern_id <> pattern_id
         GROUP BY chosen_pattern_id
        """,
        (pattern_id,),
    ).fetchall()
    return {row["chosen_pattern_id"]: row["n"] for row in rows}


def _distractor_pool(
    library: PatternLibrary,
    correct_id: str,
    history: dict[str, int],
) -> list[str]:
    """Candidate distractors, most instructive first.

    Tier 1: patterns the library says are confusable with this one, ordered by
            how often *this learner* has actually confused them.
    Tier 2: the rest of the same world — plausible neighbours.
    Tier 3: everything else, so the pool never runs dry on a small library.
    """
    correct = library[correct_id]

    confusable = [c.pattern_id for c in correct.confusable_with]
    confusable.sort(key=lambda pid: (-history.get(pid, 0), pid))

    same_world = [
        p.id
        for p in library.worlds.get(correct.world, ())
        if p.id != correct_id and p.id not in confusable
    ]

    rest = [
        p.id
        for p in library
        if p.id != correct_id and p.id not in confusable and p.id not in same_world
    ]

    return confusable + same_world + rest


def build_round(
    library: PatternLibrary,
    problem: Problem,
    *,
    seed: int,
    history: dict[str, int] | None = None,
    choices: int = DEFAULT_CHOICES,
) -> HunterRound:
    """Assemble one multiple-choice round.

    Raises if the library cannot supply enough distinct options, rather than
    silently presenting a two-option question that can be won by coin flip.
    """
    if choices < 2:
        raise ValueError("a recognition round needs at least two options")

    pool = _distractor_pool(library, problem.pattern, history or {})
    wanted = choices - 1
    if len(pool) < wanted:
        raise ValueError(
            f"only {len(pool)} distractors available for {problem.pattern!r}, need {wanted}"
        )

    distractors = pool[:wanted]
    pattern_ids = [problem.pattern, *distractors]

    # Shuffle deterministically so a replayed seed reproduces the exact screen,
    # including which letter was correct.
    Random(seed).shuffle(pattern_ids)

    options = tuple(HunterOption(pattern_id=pid, name=library[pid].name) for pid in pattern_ids)
    return HunterRound(
        problem=problem,
        options=options,
        correct_index=pattern_ids.index(problem.pattern),
        seed=seed,
    )


def judge_round(library: PatternLibrary, round_: HunterRound, chosen_index: int) -> HunterFeedback:
    """Grade an answer and produce feedback aimed at the specific mistake."""
    if not 0 <= chosen_index < len(round_.options):
        raise IndexError(f"choice {chosen_index} outside 0..{len(round_.options) - 1}")

    chosen = round_.options[chosen_index].pattern_id
    actual = round_.problem.pattern
    correct = chosen == actual

    tell = ""
    if not correct:
        confusion = library[actual].confusion_with(chosen)
        if confusion is not None:
            tell = confusion.tell

    return HunterFeedback(
        correct=correct,
        chosen_pattern_id=chosen,
        actual_pattern_id=actual,
        why=round_.problem.why,
        signals=round_.problem.signals_present,
        tell=tell,
        classic_ref=round_.problem.classic_ref,
    )


def choose_problem(
    bank: ProblemBank,
    pattern_id: str,
    *,
    seed: int,
    exclude: frozenset[str] = frozenset(),
    difficulty: Difficulty | None = None,
) -> Problem:
    """Pick a problem for a pattern, avoiding recently-seen ones.

    Falls back to the full set when everything has been excluded, because
    repeating a problem is much better than showing none.
    """
    candidates = bank.for_pattern(pattern_id, difficulty=difficulty)
    if not candidates:
        candidates = bank.for_pattern(pattern_id)
    if not candidates:
        raise LookupError(f"no problems available for pattern {pattern_id!r}")

    fresh = tuple(p for p in candidates if p.id not in exclude) or candidates
    return fresh[Random(seed).randrange(len(fresh))]


def recent_problem_ids(
    conn: sqlite3.Connection, pattern_id: str, *, limit: int = 3
) -> frozenset[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT problem_id FROM attempt
         WHERE pattern_id = ? AND problem_id IS NOT NULL
         ORDER BY started_at DESC LIMIT ?
        """,
        (pattern_id, limit),
    ).fetchall()
    return frozenset(row["problem_id"] for row in rows)


def build_round_for(
    conn: sqlite3.Connection,
    library: PatternLibrary,
    bank: ProblemBank,
    pattern_id: str,
    *,
    seed: int,
    choices: int = DEFAULT_CHOICES,
) -> HunterRound:
    """Convenience: pick a problem and build an adaptive round in one call."""
    problem = choose_problem(
        bank, pattern_id, seed=seed, exclude=recent_problem_ids(conn, pattern_id)
    )
    return build_round(
        library,
        problem,
        seed=seed,
        history=confusion_counts(conn, pattern_id),
        choices=choices,
    )
