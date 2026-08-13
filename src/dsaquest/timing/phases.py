"""Where the time actually went.

One total duration tells you a student was slow. It does not tell you *why*,
and "why" is the only part that can be trained. So a solve is instrumented at
four transitions the learner makes anyway:

    RECOGNISE   until they commit to a pattern
    PLAN        until they start typing
    IMPLEMENT   until the first submission
    DEBUG       from the first failed submission until acceptance

``DEBUG`` only exists once something has failed, which makes it the sharpest
signal available: a large debug share means the student codes before they think.

The clock is injectable so tests are not at the mercy of wall time.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class Phase(StrEnum):
    RECOGNISE = "recognise"
    PLAN = "plan"
    IMPLEMENT = "implement"
    DEBUG = "debug"

    @property
    def label(self) -> str:
        return {
            Phase.RECOGNISE: "Pattern recognition",
            Phase.PLAN: "Planning",
            Phase.IMPLEMENT: "Implementation",
            Phase.DEBUG: "Debugging",
        }[self]


#: The order phases are reported in. Not the order they must occur — a student
#: may return to planning after a failed submission, and that is worth seeing.
PHASE_ORDER: tuple[Phase, ...] = (Phase.RECOGNISE, Phase.PLAN, Phase.IMPLEMENT, Phase.DEBUG)


def _monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


@dataclass(slots=True)
class Stopwatch:
    """Accumulates elapsed time per phase across an exercise.

    Re-entering a phase adds to it rather than restarting it, so a student who
    goes back to planning after a failure has both stretches counted.
    """

    clock: Callable[[], int] = _monotonic_ms
    _totals: dict[Phase, int] = field(default_factory=dict)
    _current: Phase | None = None
    _entered_at: int = 0
    _started_at: int | None = None
    _stopped_at: int | None = None

    def start(self, phase: Phase = Phase.RECOGNISE) -> None:
        now = self.clock()
        self._started_at = now
        self._stopped_at = None
        self._current = phase
        self._entered_at = now

    def enter(self, phase: Phase) -> None:
        """Move to ``phase``, banking whatever the current one has accrued."""
        if self._started_at is None:
            self.start(phase)
            return
        if self._stopped_at is not None:
            return
        self._bank()
        self._current = phase
        self._entered_at = self.clock()

    def stop(self) -> None:
        if self._started_at is None or self._stopped_at is not None:
            return
        self._bank()
        self._stopped_at = self.clock()
        self._current = None

    def _bank(self) -> None:
        if self._current is None:
            return
        elapsed = max(0, self.clock() - self._entered_at)
        self._totals[self._current] = self._totals.get(self._current, 0) + elapsed

    @property
    def running(self) -> bool:
        return self._started_at is not None and self._stopped_at is None

    @property
    def current(self) -> Phase | None:
        return self._current

    @property
    def elapsed_ms(self) -> int:
        """Wall time since start, whether or not the watch is still running."""
        if self._started_at is None:
            return 0
        end = self._stopped_at if self._stopped_at is not None else self.clock()
        return max(0, end - self._started_at)

    def breakdown(self) -> dict[Phase, int]:
        """Milliseconds per phase, including the phase still in progress."""
        totals = dict(self._totals)
        if self.running and self._current is not None:
            live = max(0, self.clock() - self._entered_at)
            totals[self._current] = totals.get(self._current, 0) + live
        return {phase: totals.get(phase, 0) for phase in PHASE_ORDER if totals.get(phase, 0)}

    @property
    def total_ms(self) -> int:
        return sum(self.breakdown().values())


@dataclass(frozen=True, slots=True)
class PhaseTiming:
    """A finished breakdown, ready to persist or analyse."""

    breakdown: dict[Phase, int]
    total_ms: int

    @classmethod
    def from_stopwatch(cls, watch: Stopwatch) -> PhaseTiming:
        breakdown = watch.breakdown()
        return cls(breakdown=breakdown, total_ms=sum(breakdown.values()))

    def share(self, phase: Phase) -> float:
        if not self.total_ms:
            return 0.0
        return self.breakdown.get(phase, 0) / self.total_ms

    @property
    def reached_debugging(self) -> bool:
        """True only if something failed — debugging cannot happen otherwise."""
        return self.breakdown.get(Phase.DEBUG, 0) > 0
