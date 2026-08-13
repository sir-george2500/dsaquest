"""Mode D — Pattern Duel.

Two statements, side by side, chosen because they are *genuinely* mistakable
for each other. Say which is which.

This is the sharpest recognition drill the content can produce. In Mode A a
distractor can often be dismissed without understanding the problem — an array
statement is not a graph problem, and the learner never has to articulate why.
A duel removes that escape. Both answers are individually plausible for both
statements, so the only thing that separates them is the discriminator, and the
learner has to find it before they can commit.

Three rules make the mode work, and breaking any one of them makes it a
formality rather than a test:

* **The pair comes from the confusion graph, never at random.** ``prefix-sum``
  against ``graph-bfs`` answers itself; ``prefix-sum`` against ``sliding-window``
  does not. Only mutually-confusable pairs are eligible — the library enforces
  reciprocity precisely so that a duel can be posed in either direction.
* **The presentation order is seed-determined, the option order is not.** If the
  two patterns were listed in the same order as the two statements, matching
  them positionally would win every time. Options are offered in a fixed
  canonical order; only the statements move.
* **The feedback quotes the library, not the mode.** When the learner gets a
  side wrong, the discriminator shown is the ``tell`` the pattern author already
  wrote for that exact ordered pair, in the direction of the mistake — never a
  sentence this module invented.

Everything is deterministic in ``seed``, so a duel can be replayed exactly.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from random import Random

from ...content.loader import PatternLibrary
from ...content.problems import ProblemBank
from ...domain.problem import Problem
from .hunter import choose_problem, confusion_counts, recent_problem_ids

_SEED_SPACE = 2**32

POSITIONS = (0, 1)
"""The two places a statement can appear on screen."""


class DuelError(LookupError):
    """Raised when the content cannot supply a duel worth playing.

    A subclass of ``LookupError`` so callers can handle "this pattern has
    nothing to fight" alongside ``choose_problem``'s missing-problem failure.
    """


@dataclass(frozen=True, slots=True)
class DuelOption:
    """One of the two answers on offer, for display."""

    pattern_id: str
    name: str


@dataclass(frozen=True, slots=True)
class Duel:
    """One posed duel: two statements, two candidate patterns, one discriminator."""

    problems: tuple[Problem, Problem]
    """The statements in the order they are shown. The order is seed-determined."""

    options: tuple[DuelOption, DuelOption]
    """The two answers on offer, in a canonical order unrelated to the statements."""

    tell: str
    """The library's discriminator for the ordered pair as presented (left then right)."""

    reverse_tell: str
    """The same pair's discriminator read the other way round."""

    seed: int

    @property
    def pattern_ids(self) -> tuple[str, str]:
        """The true pattern behind each displayed position — the answer key."""
        return (self.problems[0].pattern, self.problems[1].pattern)

    @property
    def pair(self) -> tuple[str, str]:
        """The two duelling patterns, in the order the options are offered."""
        return (self.options[0].pattern_id, self.options[1].pattern_id)

    @property
    def correct_assignment(self) -> dict[int, str]:
        """The assignment that scores full marks — useful for replay and tests."""
        return {position: self.pattern_ids[position] for position in POSITIONS}

    def position_of(self, pattern_id: str) -> int:
        """Where the statement for ``pattern_id`` was shown."""
        try:
            return self.pattern_ids.index(pattern_id)
        except ValueError:
            raise KeyError(f"{pattern_id!r} is not in this duel") from None

    def name_of(self, pattern_id: str) -> str:
        for option in self.options:
            if option.pattern_id == pattern_id:
                return option.name
        raise KeyError(f"{pattern_id!r} is not in this duel")

    def labelled(self) -> tuple[tuple[str, Problem], ...]:
        """Statements paired with A/B labels for display."""
        return tuple((chr(ord("A") + position), self.problems[position]) for position in POSITIONS)


@dataclass(frozen=True, slots=True)
class DuelFeedback:
    """The verdict on one duel, aimed at the specific mistake that was made."""

    correct: bool
    """True only when *both* sides were assigned correctly."""

    assignment: tuple[str, str]
    """What the learner said, by position."""

    actual: tuple[str, str]
    """What each position really was."""

    wrong_positions: tuple[int, ...]
    tell: str
    """The library's discriminator, directed at the first mistake when there was one."""

    whys: tuple[str, str]
    """Each problem's ``why`` — what in that statement gave it away — by position."""

    @property
    def has_tell(self) -> bool:
        return bool(self.tell)

    @property
    def swapped(self) -> bool:
        """Both patterns named, both on the wrong side — the near miss."""
        return len(self.wrong_positions) == 2 and self.assignment == (
            self.actual[1],
            self.actual[0],
        )

    @property
    def collapsed(self) -> bool:
        """The same pattern assigned to both statements — no discrimination at all."""
        return self.assignment[0] == self.assignment[1]

    def why(self, position: int) -> str:
        return self.whys[position]


def _tell(library: PatternLibrary, actual_id: str, other_id: str) -> str:
    """The discriminator shown when ``other_id`` is picked on an ``actual_id`` problem."""
    confusion = library[actual_id].confusion_with(other_id)
    return confusion.tell if confusion is not None else ""


def duel_pairs(library: PatternLibrary, bank: ProblemBank) -> tuple[tuple[str, str], ...]:
    """Every pair that can actually be duelled, each listed once in canonical order.

    A pair qualifies only when the confusion is *mutual* — both patterns name
    the other, so the discriminator exists in both directions — and both sides
    have a statement to show. Loading in strict mode already guarantees
    reciprocity; this re-checks it so a non-strict library degrades into "no
    duel available" rather than into a one-sided duel with no ``tell``.
    """
    pairs: set[tuple[str, str]] = set()
    for pattern in library:
        if not bank.for_pattern(pattern.id):
            continue
        for confusion in pattern.confusable_with:
            other_id = confusion.pattern_id
            if other_id not in library or not bank.for_pattern(other_id):
                continue
            if library[other_id].confusion_with(pattern.id) is None:
                continue  # one-sided: no discriminator to quote in both directions
            first, second = sorted((pattern.id, other_id))
            pairs.add((first, second))
    return tuple(sorted(pairs))


def _preferred(
    pairs: tuple[tuple[str, str], ...], history: Mapping[str, int]
) -> tuple[tuple[str, str], ...]:
    """Narrow to the pairs this learner has actually mixed up, when there are any.

    ``history`` is a confusion count per pattern id, exactly what
    ``hunter.confusion_counts`` returns. A pair's weight is how often either of
    its patterns has featured in a real mistake, so the duels a learner is
    served drift toward the discriminations they keep failing.
    """
    if not history:
        return pairs
    weights = {pair: history.get(pair[0], 0) + history.get(pair[1], 0) for pair in pairs}
    best = max(weights.values())
    if best <= 0:
        return pairs
    return tuple(pair for pair in pairs if weights[pair] == best)


def build_duel(
    library: PatternLibrary,
    bank: ProblemBank,
    *,
    seed: int,
    pattern_a: str | None = None,
    history: Mapping[str, int] | None = None,
    exclude: frozenset[str] = frozenset(),
) -> Duel:
    """Pose one duel.

    ``pattern_a`` pins one side, for drilling a specific pattern; the opponent
    is still drawn from its confusion graph. ``history`` biases which pair is
    chosen toward the ones this learner has demonstrably confused.

    Raises ``DuelError`` rather than inventing a pairing: two unrelated patterns
    make a duel that answers itself, which is worse than no duel at all.
    """
    pairs = duel_pairs(library, bank)
    if pattern_a is not None:
        if pattern_a not in library:
            raise KeyError(f"unknown pattern {pattern_a!r}")
        pairs = tuple(pair for pair in pairs if pattern_a in pair)
    if not pairs:
        subject = f"{pattern_a!r} has no" if pattern_a else "no pattern has a"
        raise DuelError(
            f"{subject} mutually-confusable partner with problems on both sides; "
            "a duel needs a genuine confusion, not two unrelated patterns"
        )

    rng = Random(seed)
    candidates = _preferred(pairs, history or {})
    first, second = candidates[rng.randrange(len(candidates))]

    # Only the statements move. The options stay in canonical order, otherwise
    # "the first option belongs to the first statement" would win every duel.
    left, right = (first, second) if rng.random() < 0.5 else (second, first)

    problems = (
        choose_problem(bank, left, seed=rng.randrange(_SEED_SPACE), exclude=exclude),
        choose_problem(bank, right, seed=rng.randrange(_SEED_SPACE), exclude=exclude),
    )
    options = (
        DuelOption(pattern_id=first, name=library[first].name),
        DuelOption(pattern_id=second, name=library[second].name),
    )
    return Duel(
        problems=problems,
        options=options,
        tell=_tell(library, left, right),
        reverse_tell=_tell(library, right, left),
        seed=seed,
    )


def judge_duel(library: PatternLibrary, duel: Duel, assignment: Mapping[int, str]) -> DuelFeedback:
    """Grade a duel.

    ``assignment`` maps each displayed position to the pattern the learner put
    there. The duel is correct only when **both** sides are right: naming both
    patterns but swapping them is a failure to discriminate, and so is putting
    the same pattern on both statements.
    """
    if set(assignment) != set(POSITIONS):
        raise ValueError(
            f"a duel needs an answer for positions {list(POSITIONS)}, got {sorted(assignment)}"
        )

    offered = set(duel.pair)
    strangers = sorted({pid for pid in assignment.values() if pid not in offered})
    if strangers:
        raise ValueError(f"{strangers} not among the duelling patterns {sorted(offered)}")

    given = (assignment[0], assignment[1])
    actual = duel.pattern_ids
    wrong = tuple(position for position in POSITIONS if given[position] != actual[position])

    # Quote the discriminator in the direction of the mistake: the tell stored
    # for "picked X on a problem that was really Y". With no mistake to point
    # at, show the pair's tell as presented.
    if wrong:
        position = wrong[0]
        tell = _tell(library, actual[position], given[position])
    else:
        tell = duel.tell

    return DuelFeedback(
        correct=not wrong,
        assignment=given,
        actual=actual,
        wrong_positions=wrong,
        tell=tell,
        whys=(duel.problems[0].why, duel.problems[1].why),
    )


def build_duel_for(
    conn: sqlite3.Connection,
    library: PatternLibrary,
    bank: ProblemBank,
    pattern_id: str,
    *,
    seed: int,
) -> Duel:
    """Convenience: pose a duel for one pattern, adapted to this learner's record.

    The opponent is biased toward the pattern they have actually mistaken this
    one for, and recently-seen statements are avoided.
    """
    return build_duel(
        library,
        bank,
        seed=seed,
        pattern_a=pattern_id,
        history=confusion_counts(conn, pattern_id),
        exclude=recent_problem_ids(conn, pattern_id),
    )
