"""Turning a game outcome into an FSRS rating.

FSRS asks one question after every review: Again, Hard, Good, or Easy? In Anki
the user answers it. Here we must *derive* it, because a learner grading their
own coding is a learner grading it generously.

The rubric differs by dimension, because the same signal means different things:

* **Recognition** is multiple choice, so being right is cheap and being *fast*
  is the real evidence. Hesitation on a four-way choice means the pattern was
  reconstructed, not recognised.
* **Recall** is self-graded — but the self-grade is capped by an objective
  check. Miss an essential rubric point and it is ``Again`` no matter what you
  clicked. You can be generous with yourself about the parts that do not
  matter; you cannot be generous about the invariant.
* **Implementation** is judged by a compiler, so honesty is free. Hints and
  retries are what modulate it.

One rule overrides everything: a judge failure is never the learner's fault and
never produces a rating.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.enums import Dimension, GameMode, Rating, Verdict

#: Faster than this fraction of par earns Easy — fluent, not merely correct.
FAST_FRACTION = 0.6

#: Slower than this multiple of par is downgraded to Hard even when correct.
SLOW_MULTIPLE = 2.0

#: Recognition is a four-way choice; the bar for "fluent" is tighter.
RECOGNITION_FAST_FRACTION = 0.5
RECOGNITION_SLOW_MULTIPLE = 1.5


@dataclass(frozen=True, slots=True)
class ReviewOutcome:
    """Everything observed about one exercise, before it becomes a rating."""

    mode: GameMode
    correct: bool
    hints_used: int = 0
    tries: int = 1
    duration_ms: int | None = None
    par_ms: int | None = None
    verdict: Verdict | None = None
    self_grade: Rating | None = None
    """Mode B only: what the learner clicked after seeing the canonical answer."""
    essential_missed: bool = False
    """Mode B only: an essential rubric point was not hit. Caps the self-grade."""

    @property
    def dimension(self) -> Dimension:
        return self.mode.trains

    @property
    def pace(self) -> float | None:
        """Duration as a fraction of par. ``None`` when either is unknown."""
        if not self.duration_ms or not self.par_ms or self.par_ms <= 0:
            return None
        return self.duration_ms / self.par_ms


def rate(outcome: ReviewOutcome) -> Rating | None:
    """Derive the FSRS rating, or ``None`` when this review should not count.

    ``None`` means "pretend this never happened": the scheduler is not updated
    and no review is logged. Reserved for judge failures, where recording a
    lapse would punish the learner for our bug.
    """
    if outcome.verdict is Verdict.INTERNAL_ERROR:
        return None

    match outcome.dimension:
        case Dimension.RECOGNITION:
            return _rate_recognition(outcome)
        case Dimension.RECALL:
            return _rate_recall(outcome)
        case Dimension.IMPLEMENTATION:
            return _rate_implementation(outcome)
    raise ValueError(f"unhandled dimension: {outcome.dimension}")


def _rate_recognition(outcome: ReviewOutcome) -> Rating:
    if not outcome.correct:
        return Rating.AGAIN

    # A second guess on a multiple-choice question is elimination, not recall.
    if outcome.tries > 1 or outcome.hints_used:
        return Rating.HARD

    pace = outcome.pace
    if pace is None:
        return Rating.GOOD
    if pace <= RECOGNITION_FAST_FRACTION:
        return Rating.EASY
    if pace >= RECOGNITION_SLOW_MULTIPLE:
        return Rating.HARD
    return Rating.GOOD


def _rate_recall(outcome: ReviewOutcome) -> Rating:
    """Self-graded, with an objective floor.

    The self-grade is trusted for nuance and overruled on essentials. This is
    what makes an honest system out of a subjective one: lying only costs you
    more reviews, and it cannot lift you past a missed invariant.
    """
    if not outcome.correct or outcome.essential_missed:
        return Rating.AGAIN

    grade = outcome.self_grade or Rating.GOOD

    # Needing the answer revealed in stages is not an Easy review.
    if outcome.hints_used and grade is Rating.EASY:
        return Rating.GOOD
    return grade


def _rate_implementation(outcome: ReviewOutcome) -> Rating:
    accepted = outcome.correct and (outcome.verdict is None or outcome.verdict.is_pass)
    if not accepted:
        return Rating.AGAIN

    if outcome.hints_used or outcome.tries > 2:
        return Rating.HARD

    pace = outcome.pace
    if outcome.tries > 1:
        # Right on the second submission: real knowledge, imperfect execution.
        return Rating.HARD if (pace is not None and pace >= SLOW_MULTIPLE) else Rating.GOOD

    if pace is None:
        return Rating.GOOD
    if pace <= FAST_FRACTION:
        return Rating.EASY
    if pace >= SLOW_MULTIPLE:
        return Rating.HARD
    return Rating.GOOD


def describe(rating: Rating) -> str:
    """Short user-facing justification, shown next to the next-review interval."""
    return {
        Rating.AGAIN: "missed — this comes back soon",
        Rating.HARD: "correct, but effortful",
        Rating.GOOD: "solid",
        Rating.EASY: "fluent — this one can wait longer",
    }[rating]
