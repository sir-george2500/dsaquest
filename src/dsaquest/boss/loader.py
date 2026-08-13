"""Loading and cross-validating bosses."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import yaml

from ..content.lessons import CurriculumSet
from ..content.loader import ContentError, PatternLibrary
from ..content.paths import content_root
from ..content.problems import ProblemBank
from ..domain.boss import REQUIRED_BOSS_POOLS, Boss, PhaseKind


def bosses_dir():
    return content_root() / "bosses"


# NB: no slots=True — cached_property needs a __dict__.
@dataclass(frozen=True)
class BossSet:
    bosses: dict[str, Boss]

    def __getitem__(self, boss_id: str) -> Boss:
        try:
            return self.bosses[boss_id]
        except KeyError:
            raise KeyError(f"unknown boss {boss_id!r}") from None

    def __contains__(self, boss_id: object) -> bool:
        return boss_id in self.bosses

    def __len__(self) -> int:
        return len(self.bosses)

    def __iter__(self):
        return iter(self.ordered)

    @cached_property
    def ordered(self) -> tuple[Boss, ...]:
        return tuple(sorted(self.bosses.values(), key=lambda b: (b.tier, b.id)))

    def for_master(self, master_id: str) -> tuple[Boss, ...]:
        return tuple(b for b in self.ordered if b.master_id == master_id)


def load_bosses(
    library: PatternLibrary,
    curricula: CurriculumSet | None = None,
    bank: ProblemBank | None = None,
    *,
    strict: bool = True,
) -> BossSet:
    directory = bosses_dir()
    if not directory.is_dir():
        return BossSet(bosses={})

    bosses: dict[str, Boss] = {}
    problems: list[str] = []

    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw is None:
            continue
        try:
            boss = Boss.model_validate(raw)
        except Exception as exc:
            problems.append(f"{path.name}: {exc}")
            continue
        if path.stem != boss.id:
            problems.append(f"{path.name}: file name must match id {boss.id!r}")
        bosses[boss.id] = boss

    if strict:
        problems.extend(_cross_validate(bosses, library, curricula, bank))

    if problems:
        raise ContentError(problems)
    return BossSet(bosses=bosses)


def _cross_validate(
    bosses: dict[str, Boss],
    library: PatternLibrary,
    curricula: CurriculumSet | None,
    bank: ProblemBank | None,
) -> list[str]:
    problems: list[str] = []

    for boss in bosses.values():
        missing_pools = REQUIRED_BOSS_POOLS - set(boss.dialogue)
        if missing_pools:
            problems.append(f"{boss.id}: missing dialogue pools {sorted(missing_pools)}")
        empty = [k for k, v in boss.dialogue.items() if not v]
        if empty:
            problems.append(f"{boss.id}: empty dialogue pools {sorted(empty)}")

        for pattern in boss.patterns:
            if pattern not in library:
                problems.append(f"{boss.id}: unknown pattern {pattern!r}")
            elif bank is not None and not bank.for_pattern(pattern):
                # A recognition phase needs a statement to show.
                problems.append(
                    f"{boss.id}: pattern {pattern!r} has no problems, so a "
                    f"recognition phase would have nothing to present"
                )

        if curricula is not None and boss.master_id not in curricula:
            problems.append(f"{boss.id}: unknown master {boss.master_id!r}")
        elif curricula is not None:
            governed = set(curricula[boss.master_id].patterns)
            stray = [p for p in boss.patterns if p not in governed]
            if stray:
                problems.append(
                    f"{boss.id}: draws on {stray} which {boss.master_id} does not teach"
                )

        for phase in boss.phases:
            if phase.pattern and phase.pattern not in boss.patterns:
                problems.append(
                    f"{boss.id}: phase pattern {phase.pattern!r} is not one this boss draws from"
                )

        # A boss whose phases cannot remove all its health is unwinnable.
        if boss.total_damage < boss.boss_hp:
            problems.append(
                f"{boss.id}: phases deal {boss.total_damage} but it has {boss.boss_hp} HP — "
                f"clearing every phase would still leave it standing"
            )

        # And one the learner cannot survive is a coin flip, not a test.
        survivable = boss.player_hp > boss.damage_taken
        if not survivable:
            problems.append(f"{boss.id}: a single failed phase ends the fight; that is not a fight")

        kinds = {p.kind for p in boss.phases}
        if PhaseKind.RECOGNISE not in kinds and PhaseKind.SURVIVE not in kinds:
            problems.append(f"{boss.id}: no phase asks the learner to recognise anything")

    return problems
