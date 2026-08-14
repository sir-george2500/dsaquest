"""Where Delta-X is, and what he does next.

The game used to open on a menu, which made it software rather than a journey.
This module answers one question — *what happens now* — and the interface's
only job is to show that answer and offer to do it.

**The state is derived, never stored.** There is no `story_state` table. What
chapter Delta-X is on is a fact about which secrets he holds, which final tests
he has passed and which guardians are down, and all three are already recorded
because the learning system records them. A second store would be a second
truth, and the two would disagree the first time a player did something out of
order — which they may, because nothing here forces the road.

The order of the chapters is teaching order, taken from
``content/story/chapters.yaml``. It is not world number and it is not the
guardian's tier: Elder Vhast guards world 5 and comes first, because nothing
else in the game means anything until you can read a constraint and say what
will fit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..boss import gate_status
from ..learning.mastery import all_mastery
from ..lessons import final_test, session, trial
from ..storage import repositories as repo
from .chapters import Chapter, load_chapters


class Objective(StrEnum):
    """What the next action actually is. The UI maps these to screens."""

    PROLOGUE = "prologue"
    """Delta-X has done nothing at all. Tell him who he is first."""

    MEET_MASTER = "meet_master"
    """A chapter he has not begun. The master introduces themselves."""

    TRAIN = "train"
    """Secrets left to be taught and drilled."""

    TRIAL = "trial"
    """A secret is fluent and untested. The pattern gets hidden."""

    FINAL_TEST = "final_test"
    """Every secret held. The master tests all of them with nothing named."""

    BOSS = "boss"
    """The gate is open and the guardian is standing."""

    GATE_SHUT = "gate_shut"
    """Final test passed, guardian refuses. Almost always retention."""

    ELITE_CODER = "elite_coder"
    """Every guardian down. The final gate."""

    COMPLETE = "complete"
    """The road is walked."""


@dataclass(frozen=True, slots=True)
class Step:
    """The one thing to do next, and enough context to say why."""

    objective: Objective
    title: str
    detail: str
    chapter: Chapter | None = None
    master_id: str = ""
    boss_id: str = ""
    blockers: tuple[str, ...] = ()
    long_term: str = "Reach the Elite Coder."

    @property
    def is_action(self) -> bool:
        """Whether Continue Journey can actually do this, or merely explain it."""
        return self.objective not in (Objective.GATE_SHUT, Objective.COMPLETE)


@dataclass(frozen=True, slots=True)
class ChapterStatus:
    """One chapter's standing, for the map."""

    chapter: Chapter
    secrets_held: int
    secrets_total: int
    final_passed: bool
    boss_defeated: bool
    reachable: bool

    @property
    def started(self) -> bool:
        return self.secrets_held > 0

    @property
    def complete(self) -> bool:
        return self.final_passed and self.boss_defeated

    @property
    def mark(self) -> str:
        if self.complete:
            return "✓"
        if self.started or self.final_passed:
            return "→"
        return "·" if self.reachable else "🔒"

    @property
    def fraction(self) -> float:
        """Three equal thirds: the teaching, the test, the guardian."""
        teaching = self.secrets_held / self.secrets_total if self.secrets_total else 0.0
        return (teaching + float(self.final_passed) + float(self.boss_defeated)) / 3.0


def _secrets_held(conn, master_id: str, curriculum) -> int:
    states = {p.secret_id: p.state for p in repo.all_secret_progress(conn, master_id)}
    return sum(1 for stage in curriculum.stages if states.get(stage.secret.id) == "tested")


def chapter_statuses(context) -> list[ChapterStatus]:
    """Every chapter, in road order, with how far Delta-X got.

    A chapter is reachable when the one before it is complete. Reachability is
    narrative rather than enforced — nothing stops a player training wherever
    they like — so it is shown on the map and never used to refuse anything.
    """
    conn = context.conn
    down = repo.bosses_defeated(conn)
    out: list[ChapterStatus] = []
    reachable = True

    for chapter in load_chapters().chapters:
        curriculum = _curriculum(context, chapter.master)
        if curriculum is None:
            continue
        held = _secrets_held(conn, chapter.master, curriculum)
        status = ChapterStatus(
            chapter=chapter,
            secrets_held=held,
            secrets_total=len(curriculum.stages),
            final_passed=repo.get_master_progress(conn, chapter.master).passed,
            boss_defeated=(lambda b: b is not None and b.id in down)(boss_for(context, chapter)),
            reachable=reachable,
        )
        out.append(status)
        reachable = status.complete
    return out


def boss_for(context, chapter) -> object | None:
    """The guardian of a chapter's region.

    Derived from the master rather than named in the story file. Naming it
    twice is two places to be wrong, and the boss already records which
    master's region it guards — so a guardian reassigned in content follows
    its chapter automatically.
    """
    if context.bosses is None:
        return None
    if chapter.boss and chapter.boss in context.bosses:
        return context.bosses[chapter.boss]
    for boss in context.bosses:
        if boss.master_id == chapter.master:
            return boss
    return None


def _curriculum(context, master_id: str):
    if context.curricula is None:
        return None
    try:
        return context.curricula[master_id]
    except (KeyError, LookupError):
        return None


def next_step(context) -> Step:
    """The single next thing. Walks the road and stops at the first gap."""
    conn = context.conn
    story = load_chapters()

    played = conn.execute("SELECT COUNT(*) FROM attempt").fetchone()[0]
    seen_story = repo.get_flag(conn, "prologue_read")
    if not played and not seen_story:
        return Step(
            objective=Objective.PROLOGUE,
            title="Begin",
            detail="You have not started. Learn who you are and what you came for.",
            long_term=story.title,
        )

    mastery = None
    down = repo.bosses_defeated(conn)

    for chapter in story.chapters:
        curriculum = _curriculum(context, chapter.master)
        if curriculum is None:
            continue
        master = context.masters.get(chapter.master)
        name = master.title if master else chapter.master

        held = _secrets_held(conn, chapter.master, curriculum)
        if held == 0 and not repo.get_master_progress(conn, chapter.master).passed:
            return Step(
                objective=Objective.MEET_MASTER,
                title=f"Travel to {chapter.name}",
                detail=f"{name} is waiting. You have not met them yet.",
                chapter=chapter,
                master_id=chapter.master,
            )

        if trial.pending_trial(conn, curriculum) is not None:
            return Step(
                objective=Objective.TRIAL,
                title=f"{chapter.name}: a trial",
                detail=(
                    f"{name} has taught you a secret and drilled it. Now the "
                    "technique's name comes off and the clock runs."
                ),
                chapter=chapter,
                master_id=chapter.master,
            )

        if not session.training_complete(conn, curriculum):
            stage = session.current_stage(conn, curriculum)
            secret = stage.secret.name if stage else "the next secret"
            return Step(
                objective=Objective.TRAIN,
                title=f"{chapter.name}: {secret}",
                detail=(f"{name} is mid-lesson. {held} of {len(curriculum.stages)} secrets held."),
                chapter=chapter,
                master_id=chapter.master,
            )

        progress = repo.get_master_progress(conn, chapter.master)
        if not progress.passed:
            if final_test.available(conn, curriculum):
                return Step(
                    objective=Objective.FINAL_TEST,
                    title=f"{chapter.name}: the final test",
                    detail=(
                        f"Every secret is held. {name} will now test all of "
                        "them with nothing named."
                    ),
                    chapter=chapter,
                    master_id=chapter.master,
                )
            return Step(
                objective=Objective.TRAIN,
                title=f"{chapter.name}: finish the training",
                detail=f"{name} is not ready to test you yet.",
                chapter=chapter,
                master_id=chapter.master,
            )

        boss = boss_for(context, chapter)
        if boss is not None and boss.id not in down:
            if mastery is None:
                mastery = all_mastery(conn, context.library, scheduler=context.scheduler)
            status = gate_status(conn, boss, mastery, context.masters)
            if status.open:
                return Step(
                    objective=Objective.BOSS,
                    title=f"{chapter.name}: {boss.name}",
                    detail=chapter.boss_says or f"{boss.name} guards the way on.",
                    chapter=chapter,
                    master_id=chapter.master,
                    boss_id=boss.id,
                )
            return Step(
                objective=Objective.GATE_SHUT,
                title=f"{boss.name} will not fight you yet",
                detail=(
                    "The guardian reads your record, not your intention. What it wants is below."
                ),
                chapter=chapter,
                master_id=chapter.master,
                boss_id=boss.id,
                blockers=status.blockers,
            )

    final = story.final
    if final and context.bosses and final.boss in context.bosses:
        boss = context.bosses[final.boss]
        if final.boss in down:
            return Step(
                objective=Objective.COMPLETE,
                title="The road is walked",
                detail=(
                    "Every master, every guardian, and the Elite Coder. "
                    "Go and find harder problems than his."
                ),
                long_term=story.title,
            )
        if mastery is None:
            mastery = all_mastery(conn, context.library, scheduler=context.scheduler)
        status = gate_status(conn, boss, mastery, context.masters)
        return Step(
            objective=Objective.ELITE_CODER if status.open else Objective.GATE_SHUT,
            title=f"The final gate: {boss.name}",
            detail=(
                "Nothing he sets you has been in front of you before."
                if status.open
                else "He does not fight people who are most of the way there."
            ),
            boss_id=boss.id,
            blockers=() if status.open else status.blockers,
            long_term=story.title,
        )

    return Step(
        objective=Objective.COMPLETE,
        title="The road is walked",
        detail="Every chapter behind you.",
        long_term=story.title,
    )
