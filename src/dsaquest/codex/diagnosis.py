"""What the master can see that the student cannot.

A master who says "you are weak" is worthless. A master who says *"you can
write it, you cannot spot it, so we will work on spotting it"* is the reason
you keep coming back — and this product already records everything needed to
say the second thing.

Three dimensions are scheduled independently per pattern: can you name it from
an unlabelled statement, can you produce its structure from memory, can you
write it. They come apart in characteristic ways, and each way has a different
remedy:

* **Recognition** low, implementation high — the commonest and most
  discouraging shape. The student is not bad at algorithms. They are bad at the
  one thing this whole product exists to train, and nobody has ever told them
  that is a separate skill.
* **Understanding** low, implementation high — the memorised template. The code
  runs and the model is missing.
* **Implementation** low, recognition high — they know exactly what to do and
  their hands do not know how to say it.
* **Retention** low, everything else high — they had it, and it has gone. That
  is not a failure of intelligence, it is the calendar, and saying so plainly
  matters.

The diagnosis is refused rather than guessed when the evidence is thin. A
master who confidently mis-diagnoses a student on four attempts does more
damage than one who says nothing, because the student will believe them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..learning.mastery import PatternMastery

#: Below this many recorded attempts on a pattern there is nothing to read.
#: A master who diagnoses from two attempts is guessing in an authoritative
#: voice, which is the worst combination available.
MIN_EVIDENCE = 6

#: How far one dimension must fall below the best of the others before it is
#: called *the* weakness. Two dimensions within this of each other are not
#: meaningfully different, and picking one would be noise dressed as insight.
GAP = 0.18


class Weakness(StrEnum):
    RECOGNITION = "recognition"
    """Can write it, cannot spot it."""

    UNDERSTANDING = "understanding"
    """Can write it, cannot say why it works."""

    IMPLEMENTATION = "implementation"
    """Knows what to do, cannot get it onto the screen."""

    RETENTION = "retention"
    """Held it once. The calendar took it."""

    NONE = "none"
    """Nothing stands out — either strong across the board, or too early to say."""


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """A reading of one pattern, with the numbers that produced it."""

    pattern_id: str
    weakness: Weakness
    recognition: float
    understanding: float
    implementation: float
    retention: float
    evidence: int

    @property
    def confident(self) -> bool:
        return self.weakness is not Weakness.NONE and self.evidence >= MIN_EVIDENCE

    @property
    def strongest(self) -> float:
        return max(self.recognition, self.understanding, self.implementation)

    @property
    def gap(self) -> float:
        """How far the weak dimension sits below the best one."""
        if self.weakness is Weakness.NONE:
            return 0.0
        return self.strongest - getattr(self, str(self.weakness), self.strongest)


def diagnose(mastery: PatternMastery, *, attempts: int) -> Diagnosis:
    """Read one pattern's three dimensions and name what is holding it back.

    Retention is considered first and separately. A student whose recall has
    decayed does not have a *skill* problem at all, and telling them to drill
    implementation when what they need is review would send them the wrong way
    with the master's authority behind it.
    """
    recognition = mastery.recognition.score if mastery.recognition.seen else 0.0
    understanding = mastery.recall.score if mastery.recall.seen else 0.0
    implementation = mastery.implementation.score if mastery.implementation.seen else 0.0
    retention = mastery.retention

    reading = Diagnosis(
        pattern_id=mastery.pattern_id,
        weakness=Weakness.NONE,
        recognition=recognition,
        understanding=understanding,
        implementation=implementation,
        retention=retention,
        evidence=attempts,
    )
    if attempts < MIN_EVIDENCE:
        return reading

    trained = [
        (Weakness.RECOGNITION, recognition, mastery.recognition.seen),
        (Weakness.UNDERSTANDING, understanding, mastery.recall.seen),
        (Weakness.IMPLEMENTATION, implementation, mastery.implementation.seen),
    ]
    seen = [(name, score) for name, score, was_seen in trained if was_seen]
    if len(seen) < 2:
        # One dimension trained tells you nothing about which is weakest; it
        # tells you the student has only done one kind of exercise.
        return reading

    best = max(score for _, score in seen)
    if retention < best - GAP and retention < 0.6:
        return _with(reading, Weakness.RETENTION)

    weakest_name, weakest_score = min(seen, key=lambda pair: pair[1])
    if best - weakest_score >= GAP:
        return _with(reading, weakest_name)
    return reading


def _with(reading: Diagnosis, weakness: Weakness) -> Diagnosis:
    return Diagnosis(
        pattern_id=reading.pattern_id,
        weakness=weakness,
        recognition=reading.recognition,
        understanding=reading.understanding,
        implementation=reading.implementation,
        retention=reading.retention,
        evidence=reading.evidence,
    )


#: What a master says when their own lore does not supply a line. Deliberately
#: plain: a fallback that tries to sound legendary and fails is worse than one
#: that simply tells the student the truth.
FALLBACK: dict[Weakness, str] = {
    Weakness.RECOGNITION: (
        "You can write these. You cannot yet see them coming. That is a "
        "different skill and it is the one we are here for."
    ),
    Weakness.UNDERSTANDING: (
        "Your code runs and you cannot tell me why. That is memorised, not "
        "understood, and it will not survive a problem shaped differently."
    ),
    Weakness.IMPLEMENTATION: (
        "You know what to do. Your hands do not yet know how to say it. That "
        "is the easier half to fix, and it is fixed by writing, not reading."
    ),
    Weakness.RETENTION: (
        "You held this once. Nothing is wrong with you — this is the calendar, "
        "not your ability. Go back over it before we go on."
    ),
    Weakness.NONE: "",
}
