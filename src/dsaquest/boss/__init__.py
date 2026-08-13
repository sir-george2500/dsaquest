"""Boss fights: gates, phases, health, enrage and victory tiers."""

from .fight import (
    Challenge,
    Fight,
    FightVerdict,
    GateStatus,
    PhaseOutcome,
    Requirement,
    conclude,
    gate_status,
    next_challenge,
    open_fight,
    resolve,
    target_ms,
    victory_grade,
)
from .loader import BossSet, load_bosses

__all__ = [
    "BossSet",
    "Challenge",
    "Fight",
    "FightVerdict",
    "GateStatus",
    "PhaseOutcome",
    "Requirement",
    "conclude",
    "gate_status",
    "load_bosses",
    "next_challenge",
    "open_fight",
    "resolve",
    "target_ms",
    "victory_grade",
]
