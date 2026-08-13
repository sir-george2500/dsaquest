"""The pattern knowledge model — the heart of the content system.

A ``Pattern`` is not a topic label. It is a structured answer to the question
this whole application exists to train:

    "Given a statement that does not tell me what to use, how do I know?"

So the model is built around **signals** (what in the statement points here),
**anti-signals** (what rules this out), and **confusions** (which patterns this
gets mistaken for, and how to tell them apart). Those three fields drive the
Pattern Hunter distractors, the Duel pairings, and the recall rubric — they are
load-bearing, not documentation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import MistakeCode


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Signal(_Frozen):
    """A textual cue in a problem statement that points toward this pattern."""

    cue: str = Field(description="The phrase or property to notice, e.g. 'contiguous subarray'")
    strength: int = Field(
        ge=1,
        le=3,
        default=2,
        description=(
            "1 = weak (consistent with many patterns), "
            "2 = moderate, "
            "3 = strong (near-decisive on its own)"
        ),
    )
    note: str = Field(default="", description="Why this cue implies the pattern")


class AntiSignal(_Frozen):
    """A cue that *rules this pattern out*.

    Recognition is as much elimination as it is recall, and beginners almost
    never learn the elimination half explicitly.
    """

    cue: str
    instead: str = Field(description="Pattern id that the cue points to instead")
    note: str = ""


class Confusion(_Frozen):
    """A pattern this one is genuinely mistaken for, plus the discriminator.

    ``tell`` is the single question that separates them. It is shown as feedback
    when the user picks ``pattern_id`` on a problem that was actually this one.

    ``mistake_code`` is **optional and usually omitted**. Every confusion is
    already recorded losslessly by ``attempt.chosen_pattern_id``, from which
    ``repositories.confusion_pairs()`` derives the full ordered matrix. A code
    per ordered pair would duplicate that data by hand, and hand-maintained
    duplicates drift. Set it only where the confusion has a *named* narrative
    worth surfacing in analytics prose — "you chose DP when greedy would do" —
    and read the direction as ``<chosen>_OVER_<actual>``: the code on
    ``sliding-window``'s confusion with ``prefix-sum`` describes picking prefix
    sums on a problem that was really a window.
    """

    pattern_id: str
    tell: str = Field(description="The one question that discriminates, phrased for recall")
    mistake_code: MistakeCode | None = Field(
        default=None,
        description=(
            "Optional. Only for confusions with a named narrative; the raw pair is "
            "already captured by attempt.chosen_pattern_id. Direction: CHOSEN_OVER_ACTUAL."
        ),
    )


class Trap(_Frozen):
    """A way to get the pattern right but the implementation wrong."""

    description: str
    mistake_code: MistakeCode
    symptom: str = Field(default="", description="How it shows up: which test fails, and how")


class RubricPoint(_Frozen):
    """One checkable point in a Mode B (Pattern Recall) self-grade.

    Self-grading is honest precisely because these are concrete: you are not
    asked "did you know it?" but "did you mention the shrink condition?".
    """

    key: str
    prompt: str = Field(description="What the answer must contain, phrased as a checkbox")
    essential: bool = Field(
        default=False,
        description="Missing an essential point caps the review at Rating.AGAIN",
    )
    accepts: tuple[str, ...] = Field(
        default=(),
        description="Lowercase substrings that count as hitting this point during auto-matching",
    )


class Complexity(_Frozen):
    time: str = Field(description="Canonical time complexity, e.g. 'O(n)'")
    space: str = Field(description="Canonical extra space, e.g. 'O(k)'")
    note: str = ""


class Pattern(_Frozen):
    """A single trainable pattern. One YAML file in ``content/patterns/``."""

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", description="Stable slug; never rename")
    name: str
    world: int = Field(ge=1, le=8)
    order: int = Field(ge=0, description="Position within the world, for display")
    tagline: str = Field(description="One line: what this pattern buys you")

    prerequisites: tuple[str, ...] = Field(
        default=(),
        description="Pattern ids that must reach the unlock threshold first (a DAG, not a list)",
    )

    signals: tuple[Signal, ...] = Field(min_length=1)
    anti_signals: tuple[AntiSignal, ...] = ()
    confusable_with: tuple[Confusion, ...] = ()

    invariant: str = Field(
        description="The loop/recursion invariant in one sentence — the thing you must hold true"
    )
    complexity: Complexity
    data_structures: tuple[str, ...] = ()
    cpp_facilities: tuple[str, ...] = Field(
        default=(),
        description="STL/language features this pattern teaches, e.g. 'std::unordered_map'",
    )

    traps: tuple[Trap, ...] = ()
    recall_rubric: tuple[RubricPoint, ...] = Field(min_length=1)

    template_file: str = Field(
        description="Path relative to content/templates/ holding the canonical C++ template"
    )
    template_notes: str = ""

    related: tuple[str, ...] = Field(
        default=(),
        description="Pattern ids that compose well with this one (not confusions)",
    )

    def confusion_with(self, pattern_id: str) -> Confusion | None:
        for c in self.confusable_with:
            if c.pattern_id == pattern_id:
                return c
        return None

    @property
    def strong_signals(self) -> tuple[Signal, ...]:
        return tuple(s for s in self.signals if s.strength == 3)

    @property
    def essential_rubric(self) -> tuple[RubricPoint, ...]:
        return tuple(r for r in self.recall_rubric if r.essential)
