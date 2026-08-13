"""Problem statements.

A problem exists to be *recognised*, so the schema is built around what the
statement reveals rather than around its solution. ``signals_present`` records
which of the pattern's cues this particular statement actually contains, which
is what lets the feedback after a wrong answer be specific: not "this was
sliding window" but "the phrase 'longest contiguous' was the cue you missed".

``classic_ref`` is deliberately hidden until after the attempt. Seeing
"LeetCode 3" above a statement gives the answer away, and the whole point is to
practise the case where nothing tells you.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import Difficulty


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Hint(_Frozen):
    """One rung of the hint ladder.

    Ordered from a nudge to a near-solution. Taking a hint is recorded and
    downgrades the FSRS rating, so the ladder is a real cost rather than a
    free peek.
    """

    text: str
    reveals_pattern: bool = Field(
        default=False,
        description="True if this hint names the pattern; such hints end a Hunter round",
    )


class Problem(_Frozen):
    """One problem statement. Many may map to the same pattern."""

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    pattern: str = Field(description="Pattern id this problem is really about")
    title: str
    difficulty: Difficulty

    statement: str = Field(
        min_length=80,
        description="The problem as the learner sees it. Must never name the pattern.",
    )
    constraints: str = Field(
        default="",
        description="Input bounds. Often the real cue: n <= 10^5 rules out O(n^2).",
    )

    signals_present: tuple[str, ...] = Field(
        min_length=1,
        description="Which of the pattern's cues this statement actually contains",
    )
    decoy_signals: tuple[str, ...] = Field(
        default=(),
        description="Cues that point at a confusable pattern — why this one is hard",
    )

    expected_complexity: str = Field(description="e.g. 'O(n)'")
    hints: tuple[Hint, ...] = ()

    why: str = Field(
        min_length=40,
        description="Shown after answering: what in the statement gave it away",
    )
    classic_ref: str = Field(
        default="",
        description="Which well-known problem family this drills. Revealed only after.",
    )

    @property
    def names_pattern(self) -> bool:
        """A statement that names its own pattern is unusable for recognition."""
        needle = self.pattern.replace("-", " ").lower()
        return needle in self.statement.lower()
