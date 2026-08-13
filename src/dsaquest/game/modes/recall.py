"""Mode B — Pattern Recall.

Given only the pattern's name, produce its structure from memory: the signals
that reveal it, the invariant that makes it correct, its complexity, and the
mistakes that ruin it.

Grading a free-text answer is the hard part, and the design's position is that
the self-grade is **trusted for nuance and overruled on essentials**. So:

* Every rubric point is matched objectively against the phrases the pattern
  author listed in ``accepts``.
* For **essential** points that match is authoritative. You may be generous
  with yourself about whether you mentioned the amortised argument; you may not
  be generous about whether you stated the invariant.
* For the rest, the learner's own tick decides. Anki has shown for two decades
  that people grade themselves honestly once the answer is in front of them,
  and lying only buys more reviews.

The cost is a false negative when a learner phrases an essential differently
from every listed form. That is why the expected phrasing is always shown
afterwards: a missed match becomes a vocabulary lesson rather than a silent
mark against them, and the fix is to widen ``accepts`` in the content.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...content.loader import PatternLibrary
from ...domain.enums import Rating
from ...domain.pattern import Pattern, RubricPoint


def _normalise(text: str) -> str:
    """Lowercase, collapse whitespace, and strip the punctuation people vary on."""
    lowered = " ".join(text.lower().split())
    return "".join(ch for ch in lowered if ch.isalnum() or ch.isspace())


@dataclass(frozen=True, slots=True)
class PointResult:
    point: RubricPoint
    matched: bool
    """Objectively found in the answer via one of the author's accepted phrases."""
    ticked: bool
    """What the learner claims, after seeing the canonical answer."""

    @property
    def credited(self) -> bool:
        """Essentials are decided by the match; the rest by the learner."""
        return self.matched if self.point.essential else (self.matched or self.ticked)

    @property
    def overridden(self) -> bool:
        """The learner claimed a point the matcher did not find."""
        return self.ticked and not self.matched


@dataclass(frozen=True, slots=True)
class RecallRound:
    pattern: Pattern

    @property
    def points(self) -> tuple[RubricPoint, ...]:
        return self.pattern.recall_rubric

    @property
    def essential(self) -> tuple[RubricPoint, ...]:
        return self.pattern.essential_rubric

    @property
    def prompt(self) -> str:
        return (
            f"{self.pattern.name}\n\n"
            "From memory: what signals reveal it, what invariant makes it correct, "
            "what it costs, and what usually goes wrong."
        )


@dataclass(frozen=True, slots=True)
class RecallOutcome:
    results: tuple[PointResult, ...]
    self_grade: Rating
    answer: str

    @property
    def credited(self) -> int:
        return sum(1 for r in self.results if r.credited)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def essential_missed(self) -> bool:
        return any(r.point.essential and not r.credited for r in self.results)

    @property
    def missed(self) -> tuple[PointResult, ...]:
        return tuple(r for r in self.results if not r.credited)

    @property
    def overrides(self) -> tuple[PointResult, ...]:
        return tuple(r for r in self.results if r.overridden)

    @property
    def correct(self) -> bool:
        """A recall counts as correct when no essential point was missed."""
        return not self.essential_missed

    @property
    def fraction(self) -> float:
        return self.credited / self.total if self.total else 0.0


def build_round(pattern: Pattern) -> RecallRound:
    if not pattern.recall_rubric:
        raise ValueError(f"{pattern.id} has no recall rubric")
    return RecallRound(pattern=pattern)


def match_point(point: RubricPoint, answer: str) -> bool:
    """Whether the answer contains any phrase the author accepts for this point."""
    if not point.accepts:
        return False
    haystack = _normalise(answer)
    return any(_normalise(phrase) in haystack for phrase in point.accepts if phrase.strip())


def auto_match(round_: RecallRound, answer: str) -> dict[str, bool]:
    """Objective first pass over the whole rubric, used to pre-tick the form."""
    return {point.key: match_point(point, answer) for point in round_.points}


def grade(
    round_: RecallRound,
    answer: str,
    ticked: dict[str, bool] | None = None,
    *,
    self_grade: Rating = Rating.GOOD,
) -> RecallOutcome:
    """Grade a recall attempt.

    ``ticked`` is what the learner claims after the reveal. Omitting it means
    they claimed nothing, so only the objective matches count.
    """
    claims = ticked or {}
    results = tuple(
        PointResult(
            point=point,
            matched=match_point(point, answer),
            ticked=bool(claims.get(point.key, False)),
        )
        for point in round_.points
    )
    return RecallOutcome(results=results, self_grade=self_grade, answer=answer)


def canonical_answer(pattern: Pattern, *, library: PatternLibrary | None = None) -> str:
    """What the master would have said — shown after the learner commits.

    Every cue is followed by its authored ``note``, which is the *reason* the
    cue means what it means: "No contiguity means no window." Those notes were
    written for all 126 cues in the library and shown by ``dsa pattern``, but
    this panel — the one a learner actually reads, at the moment they have just
    failed to recall something — printed the bare cue and dropped the reason.
    A cue without its reason is a fact to memorise, which is the exact habit
    this product exists to break.

    ``library`` is optional and only used to name the pattern an anti-signal
    points at. Without it the raw id is printed, which is still true, just
    uglier; a missing library must not cost the learner the explanation.
    """

    def named(pattern_id: str) -> str:
        if library is not None and pattern_id in library:
            return library[pattern_id].name
        return pattern_id

    lines = [f"{pattern.name}", ""]

    lines.append("SIGNALS")
    for signal in sorted(pattern.signals, key=lambda s: -s.strength):
        lines.append(f"  {'*' * signal.strength} {signal.cue}")
        if signal.note.strip():
            lines.append(f"      {signal.note.strip()}")

    if pattern.anti_signals:
        lines += ["", "RULES IT OUT"]
        for anti in pattern.anti_signals:
            lines.append(f"  {anti.cue}  ->  {named(anti.instead)}")
            if anti.note.strip():
                lines.append(f"      {anti.note.strip()}")

    lines += [
        "",
        "INVARIANT",
        f"  {pattern.invariant.strip()}",
        "",
        "COMPLEXITY",
        f"  time {pattern.complexity.time}, space {pattern.complexity.space}",
    ]

    if pattern.traps:
        lines += ["", "COMMON MISTAKES"]
        for trap in pattern.traps:
            lines.append(f"  {trap.description.strip()}")

    return "\n".join(lines)


def expected_phrases(point: RubricPoint) -> str:
    """The wording the matcher was looking for, shown when a point is missed.

    A missed match should teach the vocabulary rather than be a silent mark
    against the learner.
    """
    return ", ".join(f"'{p}'" for p in point.accepts) if point.accepts else ""
