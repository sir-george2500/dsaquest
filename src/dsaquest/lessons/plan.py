"""Deciding when the student is ready.

The master never deals a fixed ten questions. ``baseline_drills`` is his opening
judgement; this module revises it from evidence, which is the difference between
a teacher and a worksheet.

Fluency requires three things at once, and all three are load-bearing:

* **a streak** — consecutive correct answers, proving it is not luck;
* **breadth** — correct answers across several *kinds* of drill. Five correct
  arithmetic drills prove a reflex; they say nothing about whether the student
  knows what the trick means or when it breaks;
* **a floor** — a minimum number of attempts, so a student who guesses two
  right answers is not declared fluent.

A struggling student is not simply given more of the same. The next drill is
chosen from the kinds they have *not* yet passed, because repeating the kind
they are already good at teaches nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random

from ..domain.lesson import Drill, DrillKind, Secret
from ..storage.repositories import SecretProgress

#: Consecutive correct answers required before fluency is considered.
FLUENCY_STREAK = 3

#: Distinct drill kinds that must have been answered correctly.
FLUENCY_KINDS = 3

#: Fraction of the master's baseline that must be attempted regardless.
FLUENCY_FLOOR = 0.6

#: Accuracy below which the master extends the drilling.
STRUGGLING_ACCURACY = 0.6

#: Hard ceiling on drills per secret, so a stuck student is never trapped in a
#: loop. Past this the master moves on and lets spaced repetition do the rest.
MAX_DRILLS_MULTIPLIER = 2.5


@dataclass(frozen=True, slots=True)
class DrillVerdict:
    """The master's judgement on whether drilling continues."""

    fluent: bool
    exhausted: bool
    remaining_estimate: int
    reason: str

    @property
    def continue_drilling(self) -> bool:
        return not (self.fluent or self.exhausted)


def required_kinds(secret: Secret) -> int:
    """Breadth target, capped by what the secret actually offers."""
    return min(FLUENCY_KINDS, len(secret.drill_kinds))


def floor_attempts(secret: Secret) -> int:
    return max(2, int(round(secret.baseline_drills * FLUENCY_FLOOR)))


def ceiling_attempts(secret: Secret) -> int:
    return max(
        secret.baseline_drills + 2, int(round(secret.baseline_drills * MAX_DRILLS_MULTIPLIER))
    )


def assess(secret: Secret, progress: SecretProgress, kinds_passed: frozenset[str]) -> DrillVerdict:
    """Decide whether this secret is drilled enough."""
    needed_kinds = required_kinds(secret)
    floor = floor_attempts(secret)
    ceiling = ceiling_attempts(secret)

    has_streak = progress.consecutive_correct >= FLUENCY_STREAK
    has_breadth = len(kinds_passed) >= needed_kinds
    past_floor = progress.drills_seen >= floor

    if has_streak and has_breadth and past_floor:
        return DrillVerdict(
            fluent=True,
            exhausted=False,
            remaining_estimate=0,
            reason=(
                f"{progress.consecutive_correct} in a row across {len(kinds_passed)} kinds of drill"
            ),
        )

    if progress.drills_seen >= ceiling:
        # Not fluent, but grinding further is not working. Move on and let
        # spaced repetition bring it back rather than trapping the student.
        return DrillVerdict(
            fluent=False,
            exhausted=True,
            remaining_estimate=0,
            reason=f"{progress.drills_seen} attempts without fluency; this returns later",
        )

    accuracy = progress.accuracy
    struggling = (
        accuracy is not None and accuracy < STRUGGLING_ACCURACY and progress.drills_seen >= 3
    )

    if struggling:
        remaining = max(2, secret.baseline_drills - progress.drills_seen + 2)
        reason = f"accuracy {accuracy:.0%} — more repetition before the trial"
    elif not has_breadth:
        remaining = max(1, needed_kinds - len(kinds_passed))
        reason = f"needs {needed_kinds - len(kinds_passed)} more kind(s) of drill"
    elif not has_streak:
        remaining = max(1, FLUENCY_STREAK - progress.consecutive_correct)
        reason = f"{FLUENCY_STREAK - progress.consecutive_correct} more in a row"
    else:
        remaining = max(1, floor - progress.drills_seen)
        reason = "a few more to be sure"

    return DrillVerdict(fluent=False, exhausted=False, remaining_estimate=remaining, reason=reason)


def next_drill(
    secret: Secret,
    progress: SecretProgress,
    *,
    answered: frozenset[str],
    kinds_passed: frozenset[str],
    seed: int,
) -> Drill | None:
    """Choose the next drill, or ``None`` when the secret has nothing left.

    Priority, and the reasoning behind it:

    1. **An unseen drill of a kind not yet passed.** Closes the breadth gap with
       fresh material — the most informative thing we can ask.
    2. **Any unseen drill.** Fresh material beats repetition.
    3. **A seen drill of a kind not yet passed.** They failed this kind; the
       repeat is the point.
    4. **Anything.** Repetition for a student who has run out of new drills.
    """
    pool = list(secret.drills)
    if not pool:
        return None

    missing_kinds = {k for k in secret.drill_kinds if k.value not in kinds_passed}

    tiers = (
        [d for d in pool if d.id not in answered and d.kind in missing_kinds],
        [d for d in pool if d.id not in answered],
        [d for d in pool if d.kind in missing_kinds],
        pool,
    )

    rng = Random(seed)
    for tier in tiers:
        if tier:
            return tier[rng.randrange(len(tier))]
    return None


def opening_kind_order() -> tuple[DrillKind, ...]:
    """The order a master naturally teaches in.

    Compute it first, name what it means second, then the traps, then recall
    from memory, then apply it. Asking for recall before the student has
    computed the thing once is a test, not teaching.
    """
    return (
        DrillKind.EVALUATE,
        DrillKind.PROPERTY,
        DrillKind.TRAP,
        DrillKind.RECALL,
        DrillKind.APPLY,
    )


def check_answer(drill: Drill, given: str) -> bool:
    """Grade one drill answer.

    Multiple choice is exact. Free-form recall normalises whitespace and case,
    because ``n & 1`` and ``n&1`` are the same knowledge and marking one wrong
    would teach the student to fear the formatter rather than the machine.
    """
    if drill.kind.is_multiple_choice:
        return given.strip() == drill.answer.strip()

    normalise = lambda s: "".join(s.split()).lower()  # noqa: E731
    candidate = normalise(given)
    if not candidate:
        return False
    accepted = {normalise(drill.answer), *(normalise(a) for a in drill.accepts)}
    return candidate in accepted
