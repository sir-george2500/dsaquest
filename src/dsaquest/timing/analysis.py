"""The time analysis — turning a clock into a diagnosis.

The report exists to answer one question the learner cannot answer alone:

    "When should I stop thinking and start coding?"

It names a single bottleneck rather than listing everything that was slow.
Telling someone four things to fix tells them nothing; the point is the one
change that would have mattered most.

Nothing here punishes. A slow, correct, well-understood solution is progress,
and the report says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.enums import Difficulty, GameMode
from ..learning.par import format_duration, phase_targets
from .phases import PHASE_ORDER, Phase, PhaseTiming

#: A phase must exceed its target by this much before it can be the bottleneck.
#: Without a margin, noise picks the winner and the advice becomes random.
BOTTLENECK_MARGIN = 1.35


@dataclass(frozen=True, slots=True)
class PhaseLine:
    phase: Phase
    actual_ms: int
    target_ms: int

    @property
    def over(self) -> bool:
        return self.actual_ms > self.target_ms

    @property
    def ratio(self) -> float:
        return self.actual_ms / self.target_ms if self.target_ms else 0.0

    def render(self) -> str:
        mark = "✗" if self.over else "✓"
        return (
            f"  {self.phase.label:<22}{format_duration(self.actual_ms):>7}"
            f"   target {format_duration(self.target_ms):>6}  {mark}"
        )


@dataclass(frozen=True, slots=True)
class TimeAnalysis:
    lines: tuple[PhaseLine, ...]
    total_ms: int
    target_ms: int
    bottleneck: Phase | None
    assessment: str
    advice: str

    @property
    def within_target(self) -> bool:
        return self.total_ms <= self.target_ms

    def render(self) -> str:
        out = ["TIME ANALYSIS", ""]
        out += [line.render() for line in self.lines]
        out += [
            "",
            f"  {'Total':<22}{format_duration(self.total_ms):>7}"
            f"   target {format_duration(self.target_ms):>6}",
            "",
            f"  {self.assessment}",
        ]
        if self.advice:
            out.append(f"  → {self.advice}")
        return "\n".join(out)


def analyse(
    timing: PhaseTiming,
    mode: GameMode,
    difficulty: Difficulty = Difficulty.MEDIUM,
) -> TimeAnalysis:
    targets = phase_targets(mode, difficulty)
    total_target = sum(targets.values())

    lines = tuple(
        PhaseLine(phase=phase, actual_ms=timing.breakdown[phase], target_ms=targets[phase.value])
        for phase in PHASE_ORDER
        if phase in timing.breakdown
    )

    bottleneck = _bottleneck(lines)
    return TimeAnalysis(
        lines=lines,
        total_ms=timing.total_ms,
        target_ms=total_target,
        bottleneck=bottleneck,
        assessment=_assess(timing, lines, bottleneck, total_target),
        advice=_advise(bottleneck),
    )


def _bottleneck(lines: tuple[PhaseLine, ...]) -> Phase | None:
    """The single phase most worth fixing, or None if nothing stands out."""
    over = [line for line in lines if line.ratio >= BOTTLENECK_MARGIN]
    if not over:
        return None
    # Rank by absolute time lost, not by ratio: being 3x over on a 20-second
    # phase matters far less than being 1.5x over on a ten-minute one.
    return max(over, key=lambda line: line.actual_ms - line.target_ms).phase


def _assess(
    timing: PhaseTiming,
    lines: tuple[PhaseLine, ...],
    bottleneck: Phase | None,
    total_target: int,
) -> str:
    if timing.total_ms <= total_target and bottleneck is None:
        return "On target throughout."

    if bottleneck is None:
        return "Over target overall, but evenly — no single phase is the problem."

    recognition = next((x for x in lines if x.phase is Phase.RECOGNISE), None)

    if bottleneck is Phase.IMPLEMENT and recognition and not recognition.over:
        return (
            f"Your bottleneck is implementation, not recognition. You knew the pattern in "
            f"{format_duration(recognition.actual_ms)} and then spent "
            f"{format_duration(next(x.actual_ms for x in lines if x.phase is Phase.IMPLEMENT))} "
            f"writing it."
        )

    if bottleneck is Phase.DEBUG:
        return (
            "Your bottleneck is debugging. Time spent here is time you did not spend "
            "planning — you are coding before the approach is settled."
        )

    if bottleneck is Phase.RECOGNISE:
        return (
            "Your bottleneck is recognition. The pattern took longer to see than to use, "
            "which is the gap this training exists to close."
        )

    return "Your bottleneck is planning. You saw the pattern but hesitated over the approach."


def _advise(bottleneck: Phase | None) -> str:
    return {
        Phase.RECOGNISE: "Pattern Hunter rounds on this family",
        Phase.PLAN: "state the invariant aloud before typing anything",
        Phase.IMPLEMENT: "Code Completion drills on this template",
        Phase.DEBUG: "write the invariant down first; most of these bugs violate it",
        None: "",
    }[bottleneck]


def timeout_report(elapsed_ms: int, limit_ms: int, timing: PhaseTiming) -> str:
    """What to say when the clock runs out.

    Never "you failed". A timeout is a speed result, not a knowledge result, and
    the report says which part consumed the time.
    """
    if not timing.breakdown:
        return f"Time. {format_duration(limit_ms)} elapsed with nothing committed."

    worst = max(timing.breakdown.items(), key=lambda item: item[1])
    return (
        f"Time. {format_duration(elapsed_ms)} of {format_duration(limit_ms)}, "
        f"most of it in {worst[0].label.lower()}."
    )
