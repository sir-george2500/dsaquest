"""Loading the masters' curricula.

Pydantic validates each curriculum in isolation. The checks that matter for a
*teaching* system are cross-file and live here:

* a curriculum teaching a pattern that does not exist cannot be played;
* a trial pointing at a missing problem strands the student mid-stage;
* a multiple-choice drill whose answer is not among its options is unanswerable,
  and would tell a learner they were wrong when they were right — the single
  worst failure mode a teacher can have.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import yaml

from ..domain.lesson import Curriculum
from .loader import ContentError, PatternLibrary
from .paths import content_root
from .problems import ProblemBank


def curricula_dir():
    return content_root() / "curricula"


# NB: no slots=True — cached_property needs a __dict__.
@dataclass(frozen=True)
class CurriculumSet:
    """Every master's teaching plan, validated against patterns and problems."""

    curricula: dict[str, Curriculum]

    def __getitem__(self, master_id: str) -> Curriculum:
        try:
            return self.curricula[master_id]
        except KeyError:
            raise KeyError(f"unknown master {master_id!r}") from None

    def __contains__(self, master_id: object) -> bool:
        return master_id in self.curricula

    def __len__(self) -> int:
        return len(self.curricula)

    def __iter__(self):
        return iter(self.ordered)

    @cached_property
    def ordered(self) -> tuple[Curriculum, ...]:
        return tuple(sorted(self.curricula.values(), key=lambda c: c.master_id))

    @cached_property
    def by_pattern(self) -> dict[str, Curriculum]:
        return {c.pattern: c for c in self.curricula.values()}

    def for_pattern(self, pattern_id: str) -> Curriculum | None:
        """The master who teaches this pattern, if one does.

        Patterns without a curriculum are still playable — they simply have no
        lesson phase yet, which is the state of everything authored before the
        master system existed.
        """
        return self.by_pattern.get(pattern_id)


def load_curricula(
    library: PatternLibrary,
    bank: ProblemBank | None = None,
    *,
    strict: bool = True,
) -> CurriculumSet:
    directory = curricula_dir()
    if not directory.is_dir():
        return CurriculumSet(curricula={})

    files = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
    curricula: dict[str, Curriculum] = {}
    problems: list[str] = []

    for path in files:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw is None:
            continue
        try:
            curriculum = Curriculum.model_validate(raw)
        except Exception as exc:  # pydantic ValidationError
            problems.append(f"{path.name}: {exc}")
            continue

        if curriculum.master_id in curricula:
            problems.append(f"{path.name}: duplicate master {curriculum.master_id!r}")
            continue
        if path.stem != curriculum.master_id:
            problems.append(f"{path.name}: file name must match master_id {curriculum.master_id!r}")
        curricula[curriculum.master_id] = curriculum

    if strict:
        problems.extend(_cross_validate(curricula, library, bank))

    if problems:
        raise ContentError(problems)

    return CurriculumSet(curricula=curricula)


def _cross_validate(
    curricula: dict[str, Curriculum],
    library: PatternLibrary,
    bank: ProblemBank | None,
) -> list[str]:
    problems: list[str] = []
    taught: dict[str, str] = {}

    for curriculum in curricula.values():
        where = curriculum.master_id

        if curriculum.pattern not in library:
            problems.append(f"{where}: teaches unknown pattern {curriculum.pattern!r}")

        # Two masters teaching one pattern would give the student contradictory
        # instruction and make "who do I train under?" ambiguous.
        if curriculum.pattern in taught:
            problems.append(
                f"{where}: pattern {curriculum.pattern!r} is already taught by "
                f"{taught[curriculum.pattern]!r}"
            )
        else:
            taught[curriculum.pattern] = where

        orders = [stage.order for stage in curriculum.stages]
        if len(set(orders)) != len(orders):
            problems.append(f"{where}: duplicate stage orders {sorted(orders)}")

        drill_ids: set[str] = set()
        secret_ids: set[str] = set()

        for stage in curriculum.ordered_stages:
            secret = stage.secret
            if secret.id in secret_ids:
                problems.append(f"{where}: duplicate secret id {secret.id!r}")
            secret_ids.add(secret.id)

            if len(secret.drills) < secret.baseline_drills:
                problems.append(
                    f"{where}/{secret.id}: {len(secret.drills)} drills authored but "
                    f"baseline_drills is {secret.baseline_drills}; the engine cannot "
                    f"deal more drills than exist"
                )

            for drill in secret.drills:
                if drill.id in drill_ids:
                    problems.append(f"{where}: duplicate drill id {drill.id!r}")
                drill_ids.add(drill.id)

                if drill.kind.is_multiple_choice:
                    if len(drill.options) < 2:
                        problems.append(
                            f"{where}/{drill.id}: {drill.kind.value} needs at least 2 options"
                        )
                    elif drill.correct_index is None:
                        # The worst possible teaching bug: a correct student
                        # marked wrong because the key is not on the menu.
                        problems.append(
                            f"{where}/{drill.id}: answer {drill.answer!r} is not among "
                            f"its options {list(drill.options)}"
                        )
                elif drill.options:
                    problems.append(
                        f"{where}/{drill.id}: {drill.kind.value} must not offer options"
                    )

            problems.extend(
                _check_problem_ids(where, f"stage {stage.id}", stage.trial_problem_ids, bank)
            )

        problems.extend(
            _check_problem_ids(where, "final test", curriculum.final_test_problem_ids, bank)
        )

    return problems


def _check_problem_ids(
    where: str, label: str, ids: tuple[str, ...], bank: ProblemBank | None
) -> list[str]:
    if bank is None:
        return []
    return [
        f"{where}: {label} refers to unknown problem {problem_id!r}"
        for problem_id in ids
        if problem_id not in bank.problems
    ]
