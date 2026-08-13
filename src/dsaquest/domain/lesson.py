"""Lessons — the master's teaching material.

The unit of teaching is a **secret**: one small observation that collapses a
class of problems. ``n & 1``. ``n & (n - 1)``. ``1 << k``. Not a topic, not a
chapter — one trick, demonstrated with concrete numbers, drilled to fluency,
then tested with nothing named.

A stage is one secret plus its drills plus its trial. A master's curriculum is
an ordered sequence of stages ending in a final test that names nothing.

The drill counts declared here are the master's *opening* judgement, not a
quota. The engine raises or lowers them from evidence — see ``lessons.plan``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DrillKind(StrEnum):
    """What a drill asks for. Each trains a different part of holding a secret."""

    EVALUATE = "evaluate"
    """Compute it. "13 & 1 = ?" — builds the mechanical reflex."""

    PROPERTY = "property"
    """Name what it reveals. "Which property does this expose?" — builds meaning."""

    RECALL = "recall"
    """Produce the idiom from memory, given only its purpose. No multiple choice."""

    TRAP = "trap"
    """Spot the bug. Trains the watch-outs before they cost a contest."""

    APPLY = "apply"
    """A small coding task with the secret named. Builds fluency, not recognition."""

    @property
    def is_multiple_choice(self) -> bool:
        return self in (DrillKind.EVALUATE, DrillKind.PROPERTY, DrillKind.TRAP)


class Demonstration(_Frozen):
    """One worked line of the master's demonstration.

    Concrete numbers only. "13 = 1101, 13 & 1 = 1, the lowest bit is 1" teaches;
    "n & 1 extracts the low bit" merely asserts.
    """

    expression: str = Field(description="e.g. '13 & 1'")
    result: str = Field(description="e.g. '1'")
    note: str = Field(default="", description="e.g. '13 = 1101, so the lowest bit is 1'")


class WatchOut(_Frozen):
    """A trap the master warns about before the student meets it in a contest."""

    warning: str
    why: str = Field(default="", description="The mechanism, not just the rule")


class Drill(_Frozen):
    """One exercise on one secret. Small, fast, and pattern-named throughout."""

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    kind: DrillKind
    prompt: str = Field(min_length=8)
    options: tuple[str, ...] = Field(
        default=(),
        description="Choices for multiple-choice kinds; empty for RECALL and APPLY",
    )
    answer: str = Field(description="The exact correct option, or the expected idiom")
    accepts: tuple[str, ...] = Field(
        default=(),
        description="Additional accepted forms for RECALL, lowercased and space-stripped",
    )
    explanation: str = Field(min_length=10, description="Shown after answering, right or wrong")

    @property
    def correct_index(self) -> int | None:
        if not self.options:
            return None
        try:
            return self.options.index(self.answer)
        except ValueError:
            return None


class Secret(_Frozen):
    """One trick the master teaches, with everything needed to teach it."""

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str = Field(description="e.g. 'The Lowest Bit'")
    idiom: str = Field(description="The C++ expression itself, e.g. 'n & 1'")
    teaches: str = Field(
        min_length=20, description="What it does and why it exists, in the master's voice"
    )
    demonstrations: tuple[Demonstration, ...] = Field(min_length=1)
    watch_out: tuple[WatchOut, ...] = ()
    memorise: bool = Field(
        default=False,
        description="The master explicitly tells the student to commit this to memory",
    )
    animation: str = Field(
        default="",
        description=(
            "Id of an animation in content/animations/. The student may watch and "
            "step through it before being drilled — teach before you test."
        ),
    )
    baseline_drills: int = Field(
        ge=1, le=12, description="Opening judgement of how many drills; the engine adapts"
    )
    drills: tuple[Drill, ...] = Field(min_length=2)

    @property
    def drill_kinds(self) -> frozenset[DrillKind]:
        return frozenset(d.kind for d in self.drills)


class Stage(_Frozen):
    """One secret, its drills, and the trial that tests it with nothing named."""

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    order: int = Field(ge=0)
    secret: Secret
    pattern: str | None = Field(
        default=None,
        description=(
            "Which of the master's patterns this secret belongs to. "
            "Defaults to the curriculum's first pattern."
        ),
    )
    trial_problem_ids: tuple[str, ...] = Field(
        default=(),
        description="Problems used as this stage's trial. Pattern is NOT revealed.",
    )


class Curriculum(_Frozen):
    """A master's full teaching plan for the pattern he governs."""

    master_id: str = Field(pattern=r"^[a-z0-9]+(_[a-z0-9]+)*$")
    patterns: tuple[str, ...] = Field(
        min_length=1,
        description=(
            "Every pattern this master governs. A Master of Search teaches both "
            "binary search and search-on-the-answer; a Master of Arrays teaches "
            "four. One pattern per master would have forced a master per pattern."
        ),
    )
    title: str
    opening: str = Field(min_length=20, description="What the master says when training begins")
    stages: tuple[Stage, ...] = Field(min_length=1)
    final_test_problem_ids: tuple[str, ...] = Field(
        default=(),
        description="The master's final test. Nothing named, drawn from all stages.",
    )

    @property
    def primary_pattern(self) -> str:
        """The pattern a stage belongs to when it does not say."""
        return self.patterns[0]

    def pattern_of(self, stage: Stage) -> str:
        return stage.pattern or self.primary_pattern

    @property
    def secrets(self) -> tuple[Secret, ...]:
        return tuple(stage.secret for stage in self.ordered_stages)

    @property
    def ordered_stages(self) -> tuple[Stage, ...]:
        return tuple(sorted(self.stages, key=lambda s: s.order))

    def stage(self, stage_id: str) -> Stage:
        for stage in self.stages:
            if stage.id == stage_id:
                return stage
        raise KeyError(f"no stage {stage_id!r} in {self.master_id}")

    @property
    def total_baseline_drills(self) -> int:
        return sum(stage.secret.baseline_drills for stage in self.stages)
