"""Bosses — the climax of a training arc.

A boss is not simply a harder exercise. It is a **sequence of phases over a
region's patterns with nothing named**, and it composes the modes the learner
has already met rather than inventing a new kind of question:

    RECOGNISE   which pattern is this?          (Mode A, pattern hidden)
    EXPLAIN     state its invariant and cost    (Mode B, objectively graded)
    IMPLEMENT   write the load-bearing lines    (Mode C, differentially judged)
    SURVIVE     a second pattern, unannounced   (Mode A on a different pattern)

Two rules carried from the design document, both enforced in the engine rather
than left to content:

* **The gate is checked before the fight unlocks, not during it.** If HP alone
  decided victory a weak learner could grind attempts until they got lucky, so
  the mastery requirements must already be satisfied. HP is tension and scoring.
* **Enrage removes safety, never time.** Accelerating a clock punishes careful
  thought, which is the opposite of what the timer exists to teach.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BossTier(IntEnum):
    TRAINING = 1
    """One foundational pattern. Introduces the boss system."""

    PATTERN = 2
    """A family, pattern hidden. Gates the next region."""

    ALGORITHM = 3
    """Several concepts composed. Gates the next arc."""

    ELITE = 4
    """Multi-pattern, traps, tight constraints. Gates the legendary path."""

    LEGENDARY = 5
    """A whole discipline at depth. Gates the Final Gate."""

    FINAL = 6
    """The Elite Coder. Nothing familiar."""

    @property
    def label(self) -> str:
        return {
            BossTier.TRAINING: "Training Boss",
            BossTier.PATTERN: "Pattern Boss",
            BossTier.ALGORITHM: "Algorithm Master",
            BossTier.ELITE: "Elite Warrior",
            BossTier.LEGENDARY: "Legendary Boss",
            BossTier.FINAL: "The Elite Coder",
        }[self]


class PhaseKind(StrEnum):
    RECOGNISE = "recognise"
    EXPLAIN = "explain"
    IMPLEMENT = "implement"
    SURVIVE = "survive"

    @property
    def label(self) -> str:
        return {
            PhaseKind.RECOGNISE: "Identify the pattern",
            PhaseKind.EXPLAIN: "Explain the approach",
            PhaseKind.IMPLEMENT: "Implement it",
            PhaseKind.SURVIVE: "Survive the unfamiliar",
        }[self]


class BossPhase(_Frozen):
    kind: PhaseKind
    damage: int = Field(
        ge=1,
        le=100,
        description="Boss HP removed when this phase is cleared",
    )
    pattern: str | None = Field(
        default=None,
        description="Pattern this phase draws from. None means the engine picks one.",
    )
    title: str = ""


class Gate(_Frozen):
    """What must already be true before the fight is offered at all."""

    recognition: float = Field(default=0.0, ge=0.0, le=1.0)
    understanding: float = Field(default=0.0, ge=0.0, le=1.0)
    implementation: float = Field(default=0.0, ge=0.0, le=1.0)
    retention: float = Field(default=0.0, ge=0.0, le=1.0)
    master_final_test: bool = Field(
        default=True,
        description="Whether the governing master's final test must be passed first",
    )

    def as_pairs(self) -> tuple[tuple[str, float], ...]:
        return (
            ("recognition", self.recognition),
            ("understanding", self.understanding),
            ("implementation", self.implementation),
            ("retention", self.retention),
        )


class Boss(_Frozen):
    """One boss. A YAML file in ``content/bosses/``."""

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str = Field(description="Shown in caps at the top of the arena")
    title: str = Field(description="Its epithet")
    tier: BossTier
    master_id: str = Field(description="The master whose region this boss guards")
    patterns: tuple[str, ...] = Field(
        min_length=1, description="Patterns the fight draws from. Never revealed."
    )

    boss_hp: int = Field(default=100, ge=10, le=999)
    player_hp: int = Field(default=100, ge=10, le=999)
    damage_taken: int = Field(
        default=25, ge=1, le=100, description="Player HP lost per failed phase"
    )

    gate: Gate = Field(default_factory=Gate)
    phases: tuple[BossPhase, ...] = Field(min_length=2)

    enrage_after: int = Field(
        default=2,
        ge=1,
        description=(
            "Failed phases before the boss enrages. Enrage removes hints and "
            "doubles the respect at stake; it never touches the clock."
        ),
    )

    dialogue: dict[str, tuple[str, ...]] = Field(
        description="Pools keyed by outcome, same convention as a master's"
    )

    @property
    def total_damage(self) -> int:
        return sum(phase.damage for phase in self.phases)

    def pool(self, name: str) -> tuple[str, ...]:
        return self.dialogue.get(name, ())


#: Pools every boss must define.
REQUIRED_BOSS_POOLS: frozenset[str] = frozenset(
    {
        "intro",
        "phase_won",
        "phase_lost",
        "enrage",
        "victory",
        "perfect",
        "defeat",
        "gate_locked",
        "rematch",
    }
)
