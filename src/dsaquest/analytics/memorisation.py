"""Memorisation — did the learner remember the problems, or learn the pattern?

The failure mode this module exists to catch is the one that would quietly
hollow out the whole product: a learner who scores well on the problems they
have already met and badly on ones they have not. That is recall of a problem
set, not mastery of a technique, and §10 of the design names the measurement:

    memorisation_gap = accuracy(seen instances) − accuracy(fresh variants)

Two things make this harder than the formula suggests.

**A gap is not evidence.** With four attempts on each side, a learner who
genuinely knows the pattern will show a gap of 0.25 roughly as often as not.
Accusing them of memorising because a coin landed badly is worse than never
looking: the master's harshness is only bearable because it is *true* (§0), and
a false accusation spends that credit on noise. So the raw gap is never the
verdict on its own. It must clear a threshold **and** survive a conservative
interval test, and when it cannot, the answer is "not enough evidence" — a real
state, never 0.0 and never "fine".

**Novelty has a cost, and that cost is not a diagnosis.** A problem you have
never seen is genuinely harder than one you have; some positive gap is normal
and healthy. The threshold is set well above that ordinary cost so that being
slightly slower on new material is not treated as a confession.

What the numbers rest on
------------------------
Only attempts that record a ``problem_id`` can be classified, because the whole
question is whether *this problem* has been met before. Recall drills and
template completions record no problem and are invisible here — see
``storage.repositories.problem_exposure``.

Two honest limitations, stated because the UI should not overclaim:

* Fresh attempts are, by construction, weighted towards the beginning of a
  learner's history with a pattern — a first encounter can only happen once.
  A learner who has simply improved over time will therefore show a small
  positive gap that is not memorisation. The threshold absorbs the ordinary
  case; a very slow learner with a very long history is the case it cannot
  distinguish, and nothing in the event log can.
* The overall verdict pools every pattern, so it can disagree with all of its
  parts (Simpson's paradox) when the mix of fresh and repeated work differs
  sharply between patterns. It answers "is this learner's recall bound to
  remembered problems?", not "which pattern is the problem?" — that is what the
  per-pattern verdicts are for, and they are the ones a master should quote.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from math import sqrt

from ..storage import repositories as repo

#: Scope name used by the pooled verdict, so a UI can key both kinds the same.
OVERALL = "overall"

#: Gap at which the claim is made, in accuracy points.
#:
#: A fresh problem is legitimately harder than one already met, so a small
#: positive gap is the normal state of a healthy learner and must not read as an
#: accusation. Thirty points is far more than that ordinary novelty cost: at
#: that size the learner is passing familiar work and failing the same technique
#: in unfamiliar clothes, which is the thing §10 describes.
MEMORISATION_GAP = 0.30

#: Attempts required on **both** sides before anything at all is reported.
#:
#: Four is a floor, not a comfort. Three attempts move an accuracy figure in
#: 33-point steps, so no threshold applied to a three-sample proportion can
#: carry meaning. Four is the smallest sample at which even total separation
#: (4/4 against 0/4) is unlikely by chance — p ≈ 0.014 by Fisher's exact test —
#: and the interval test below still has to agree before anything is said.
MIN_ATTEMPTS_PER_SIDE = 4

#: One-sided 95% normal deviate, used for the Wilson bounds on each side.
#:
#: The two bounds are then required not to overlap, which is a stricter test
#: than comparing the proportions directly. That is deliberate and one-way: it
#: buys silence on ambiguous data at the cost of missing some real cases, and
#: those are the right way round when the output is an accusation.
CONFIDENCE_Z = 1.645


class Finding(StrEnum):
    """What can honestly be said. Three states, and the third is not a failure."""

    MEMORISING = "memorising"
    """Strong on remembered problems, weak on new ones, beyond doubting."""

    PATTERN_HOLDS = "pattern_holds"
    """Enough attempts on both sides, and no meaningful gap between them.

    The absence of this failure, not a certificate of mastery — that claim
    belongs to Warrior Strength, which measures far more than this.
    """

    NOT_ENOUGH_EVIDENCE = "not_enough_evidence"
    """Nothing can be said: too few attempts, or a gap the sample cannot support.

    Distinct from both other states on purpose. Reporting it as a gap of 0.0
    would read as "fine", and reporting a suspicious-but-thin gap as
    ``MEMORISING`` would be an accusation the data does not license.
    """


def _wilson(correct: int, total: int, *, z: float = CONFIDENCE_Z) -> tuple[float, float]:
    """Wilson score interval for a proportion.

    Not the textbook normal interval, which is exactly wrong where this module
    lives: at proportions near 0 or 1 — the interesting ones here — it collapses
    to zero width and would claim certainty from four attempts.
    """
    p = correct / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    spread = z * sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - spread), min(1.0, centre + spread)


@dataclass(frozen=True, slots=True)
class MemorisationVerdict:
    """The counts, the gap, and how much of it the sample will support.

    Deliberately a record of four integers with everything else derived, so the
    verdict cannot be constructed disagreeing with its own evidence. The sample
    sizes are carried alongside the gap because a UI that shows the gap without
    them is inviting the reader to trust a number this module would not.
    """

    scope: str
    """A pattern id, or :data:`OVERALL`."""

    seen_correct: int
    seen_total: int
    fresh_correct: int
    fresh_total: int

    @property
    def seen_accuracy(self) -> float | None:
        """``None`` when untried — different from 0.0, and must stay so."""
        return self.seen_correct / self.seen_total if self.seen_total else None

    @property
    def fresh_accuracy(self) -> float | None:
        return self.fresh_correct / self.fresh_total if self.fresh_total else None

    @property
    def gap(self) -> float | None:
        """Observed gap. ``None`` when either side has no attempts at all."""
        if self.seen_accuracy is None or self.fresh_accuracy is None:
            return None
        return self.seen_accuracy - self.fresh_accuracy

    @property
    def confident_gap(self) -> float | None:
        """The gap that survives the sample: seen's lower bound less fresh's upper.

        Negative — usually very negative on small samples — means the observed
        gap is inside what chance produces at this sample size. Exposed rather
        than hidden so the UI can show *how much* is actually established, which
        is nearly always less than the raw gap.
        """
        if not self.seen_total or not self.fresh_total:
            return None
        seen_low, _ = _wilson(self.seen_correct, self.seen_total)
        _, fresh_high = _wilson(self.fresh_correct, self.fresh_total)
        return seen_low - fresh_high

    @property
    def enough_attempts(self) -> bool:
        return (
            self.seen_total >= MIN_ATTEMPTS_PER_SIDE and self.fresh_total >= MIN_ATTEMPTS_PER_SIDE
        )

    @property
    def finding(self) -> Finding:
        gap = self.gap
        confident = self.confident_gap
        if not self.enough_attempts or gap is None or confident is None:
            return Finding.NOT_ENOUGH_EVIDENCE
        if gap >= MEMORISATION_GAP:
            # A gap the sample cannot support is not a smaller gap; it is an
            # unanswered question, and calling it PATTERN_HOLDS would clear a
            # learner the data does not clear.
            return Finding.MEMORISING if confident > 0 else Finding.NOT_ENOUGH_EVIDENCE
        return Finding.PATTERN_HOLDS

    @property
    def memorising(self) -> bool:
        return self.finding is Finding.MEMORISING

    @property
    def decided(self) -> bool:
        """Whether anything at all may be said to the learner about this scope."""
        return self.finding is not Finding.NOT_ENOUGH_EVIDENCE

    @property
    def detail(self) -> str:
        """One line, honest about the sample. Never states a gap it cannot support."""
        counts = f"{self.seen_total} repeated, {self.fresh_total} new"
        if self.finding is Finding.NOT_ENOUGH_EVIDENCE:
            if not self.enough_attempts:
                return f"{counts} — too few to judge"
            return f"{counts} — a gap is visible but the sample cannot support it"

        seen = self.seen_accuracy or 0.0
        fresh = self.fresh_accuracy or 0.0
        return f"{seen:.0%} on problems already met, {fresh:.0%} on new ones ({counts})"


@dataclass(frozen=True, slots=True)
class MemorisationReport:
    """The pooled verdict and one per pattern that has any classifiable history."""

    overall: MemorisationVerdict
    patterns: tuple[MemorisationVerdict, ...]

    def __getitem__(self, pattern_id: str) -> MemorisationVerdict:
        for verdict in self.patterns:
            if verdict.scope == pattern_id:
                return verdict
        raise KeyError(pattern_id)

    @property
    def memorised(self) -> tuple[MemorisationVerdict, ...]:
        """Patterns the master may call out, widest established gap first.

        Sorted by ``confident_gap`` rather than the raw gap: what he says out
        loud should be led by the case that is best supported, not the loudest.
        """
        called = [v for v in self.patterns if v.memorising]
        return tuple(sorted(called, key=lambda v: v.confident_gap or 0.0, reverse=True))

    @property
    def any_memorising(self) -> bool:
        return bool(self.memorised) or self.overall.memorising


def _verdict(scope: str, exposure: repo.ProblemExposure | None) -> MemorisationVerdict:
    if exposure is None:
        return MemorisationVerdict(scope, 0, 0, 0, 0)
    return MemorisationVerdict(
        scope=scope,
        seen_correct=exposure.seen_correct,
        seen_total=exposure.seen_total,
        fresh_correct=exposure.fresh_correct,
        fresh_total=exposure.fresh_total,
    )


def assess(conn: sqlite3.Connection, pattern_id: str) -> MemorisationVerdict:
    """Judge one pattern. A pattern with no history reports no evidence, not zero."""
    rows = repo.problem_exposure(conn, pattern_id=pattern_id)
    return _verdict(pattern_id, rows[0] if rows else None)


def assess_all(conn: sqlite3.Connection) -> MemorisationReport:
    """Judge every pattern with classifiable history, plus the pooled whole.

    The pooled counts are summed from the per-pattern rows rather than queried
    separately, so the overall verdict is always the arithmetic of the parts the
    UI is displaying beside it.
    """
    rows = repo.problem_exposure(conn)
    patterns = tuple(_verdict(row.pattern_id, row) for row in rows)

    overall = MemorisationVerdict(
        scope=OVERALL,
        seen_correct=sum(row.seen_correct for row in rows),
        seen_total=sum(row.seen_total for row in rows),
        fresh_correct=sum(row.fresh_correct for row in rows),
        fresh_total=sum(row.fresh_total for row in rows),
    )
    return MemorisationReport(overall=overall, patterns=patterns)
