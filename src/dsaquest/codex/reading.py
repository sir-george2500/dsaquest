"""What a master sees when they look at the student in front of them.

`diagnosis.py` reads *one* pattern. A master teaches six or eight, and the
question they are actually asked — "so what is wrong with me?" — is about the
student, not about a pattern. This picks the one thing worth saying.

Two rules make the difference between a mentor and a nag:

**One thing at a time.** A master who lists four weaknesses has told you
nothing you can act on this evening. The clearest gap wins and the rest wait.

**Silence is allowed.** With too little evidence, or with everything within
noise of everything else, the master says nothing about your weaknesses. That
is the honest answer, and it also means that when they *do* say something, it
lands — a mentor who comments every single visit is wallpaper.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..learning.mastery import pattern_mastery
from ..storage import repositories as repo
from .diagnosis import Diagnosis, Weakness, diagnose
from .lore import diagnosis_line


@dataclass(frozen=True, slots=True)
class Reading:
    """One master's verdict on one student, ready to be spoken."""

    master_id: str
    diagnosis: Diagnosis
    line: str

    @property
    def weakness(self) -> Weakness:
        return self.diagnosis.weakness


def read_student(context, master_id: str, *, seed: int = 0) -> Reading | None:
    """The clearest thing this master can tell this student, or nothing.

    ``None`` is a real answer and callers must treat it as one: it means the
    evidence does not support a verdict yet, and inventing one anyway is how a
    student ends up drilling the wrong thing on a master's authority.
    """
    curriculum = None
    if context.curricula is not None:
        try:
            curriculum = context.curricula[master_id]
        except (KeyError, LookupError):
            curriculum = None
    if curriculum is None:
        return None

    best: Diagnosis | None = None
    for pattern_id in curriculum.patterns:
        try:
            mastery = pattern_mastery(context.conn, pattern_id, scheduler=context.scheduler)
        except LookupError:
            # No cards yet: the student has not begun this pattern, which is
            # not a weakness and must not be reported as one.
            continue
        reading = diagnose(mastery, attempts=repo.attempts_at(context.conn, pattern_id))
        if not reading.confident:
            continue
        if best is None or reading.gap > best.gap:
            best = reading

    if best is None:
        return None
    return Reading(
        master_id=master_id,
        diagnosis=best,
        line=diagnosis_line(master_id, str(best.weakness), seed=seed),
    )
