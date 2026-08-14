"""Mode D — the Pattern Duel.

Two statements, side by side, that are deliberately easy to confuse. Two
patterns on offer. The learner assigns one to each.

The screen keeps both statements visible the entire time, because the whole
exercise is *comparison* — the discriminator only exists between them. Hunter
asks "what is this?"; the duel asks "what is this, **rather than** that?", and
that is a different and harder question.

Two things this screen deliberately does not do:

**It does not force a permutation.** Assigning the same pattern to both
statements is allowed, and the engine has a name for it — ``collapsed``. If the
UI silently prevented it by flipping the other side, a learner who cannot
discriminate at all would be handed a 50% score by the interface and we would
never see the failure. Letting them collapse is what makes the failure visible.

**It credits both patterns only when the whole duel is right.** Being
accidentally correct on one side while failing to separate the pair is not
evidence of recognition — it is a coin landing well. The scheduler hears the
joint verdict, not the two halves.
"""

from __future__ import annotations

from datetime import UTC, datetime

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from ..domain.enums import GameMode
from ..game.modes.duel import Duel, DuelError, build_duel, build_duel_for, judge_duel
from ..game.session import ExerciseResult, complete_exercise
from ..storage import repositories as repo
from .card import BACK, BAD, BODY, FAINT, FRAME, GOLD, GOOD, MEASURE, MUTE, RULE
from .master import safe

#: Same rules as everywhere else: one left edge at column 5, a bounded
#: measure, and the palette. Two problem statements set 115 characters to the
#: line, side by side, is the hardest reading task in the game — and the duel
#: is the one screen where the reading *is* the exercise.
DUEL_CSS = f"""
DuelScreen {{ background: {BACK}; }}
#duel-title {{ padding: 1 2 0 2; text-style: bold; }}
#duel-progress {{ padding: 0 2 1 2; color: {MUTE}; }}
#duel-statements {{
    padding: 1 2; margin: 0 2; border: round {FRAME}; height: auto;
    max-width: {MEASURE + 6};
}}
#duel-scroll {{ height: 1fr; scrollbar-gutter: stable; }}
#duel-ask {{ padding: 1 2 0 2; text-style: bold; }}
#duel-choices {{ padding: 1 2; height: auto; max-width: {MEASURE + 6}; }}

#duel-verdict {{
    padding: 1 2; margin: 1 2; border: round {GOOD}; height: auto;
    max-width: {MEASURE + 6};
}}
#duel-verdict.wrong {{ border: round {BAD}; }}
"""

ROUNDS = 5
"""Duels per visit. Short on purpose — this mode is concentrated work."""


class DuelScreen(Screen):
    """A run of pattern duels."""

    BINDINGS = [
        Binding("escape", "leave", "Leave"),
        Binding("1", "pick(0)", "", show=False),
        Binding("2", "pick(1)", "", show=False),
        Binding("space", "advance", "Continue", show=False),
    ]

    def __init__(
        self,
        pattern_id: str | None = None,
        *,
        seed: int | None = None,
        rounds: int = ROUNDS,
    ) -> None:
        super().__init__()
        self.pattern_id = pattern_id
        self.rounds = rounds
        self._pinned_seed = seed
        self._seed_counter = 0
        self._generation = 0

        self.duel: Duel | None = None
        self.assignment: dict[int, str] = {}
        self.position = 0
        self.round_number = 0
        self.won = 0
        self.started_at = datetime.now(UTC)
        self.awaiting_advance = False
        self.finished = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="duel-title")
        yield Static(id="duel-progress")
        # The question and the options scroll with the statements they are
        # about. Laid out after a container that had taken the remaining rows,
        # the two options fell off the bottom of the screen — the duel asked
        # "which pattern?" and showed neither answer.
        yield VerticalScroll(
            Static(id="duel-statements"),
            Static(id="duel-ask"),
            Vertical(id="duel-choices"),
            Static(id="duel-verdict"),
            id="duel-scroll",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.title = "PATTERN DUEL"
        self.sub_title = "tell the two apart"
        self.query_one("#duel-verdict", Static).display = False
        self.query_one("#duel-title", Static).update(
            f"[b {GOLD}]PATTERN DUEL[/]\n"
            "[i]Two statements that want to be mistaken for each other.[/]"
        )
        self.pose()

    # ------------------------------------------------------------- plumbing

    def _seed(self) -> int:
        """A seed per duel, pinned when the caller wants a reproducible run."""
        if self._pinned_seed is not None:
            self._seed_counter += 1
            return self._pinned_seed + self._seed_counter
        return int(datetime.now(UTC).timestamp() * 1000) % (2**31)

    def _option_id(self, index: int) -> str:
        # The generation counter keeps ids unique across rounds: Textual defers
        # remove_children(), so last round's buttons can still be mounted when
        # this round's are added, and duplicate ids raise.
        return f"duel-opt-{self._generation}-{index}"

    # ----------------------------------------------------------------- pose

    def pose(self) -> None:
        context = self.app.context
        self.assignment = {}
        self.position = 0
        self.awaiting_advance = False

        try:
            if self.pattern_id is not None:
                duel = build_duel_for(
                    context.conn,
                    context.library,
                    context.bank,
                    self.pattern_id,
                    seed=self._seed(),
                )
            else:
                duel = build_duel(context.library, context.bank, seed=self._seed())
        except (DuelError, KeyError) as exc:
            self.refuse(str(exc))
            return

        self.duel = duel
        self.round_number += 1
        self.started_at = datetime.now(UTC)

        self.query_one("#duel-progress", Static).update(
            f"Duel {self.round_number} of {self.rounds}   [dim]{self.won} clean so far[/]"
        )

        # A rule between the two, and a blank line before the constraints. Set
        # solid, the two statements and their four lines of constraints ran
        # together as one twenty-line grey block, which on the screen whose
        # whole exercise is telling two statements apart is the wrong shape
        # entirely: the eye has to be able to find where A stops.
        width = max(20, self.query_one("#duel-statements").content_size.width or MEASURE)
        blocks = [
            f"[b {GOLD}]STATEMENT {label}[/]   [{MUTE}]{safe(problem.title)}[/]\n\n"
            f"[{BODY}]{safe(problem.statement.strip())}[/]\n\n"
            f"[{FAINT}]{safe(problem.constraints.strip())}[/]"
            for label, problem in duel.labelled()
        ]
        self.query_one("#duel-statements", Static).update(
            f"\n\n[{RULE}]{'─' * width}[/]\n\n".join(blocks)
        )
        self.ask()

    def refuse(self, reason: str) -> None:
        """No duel can be posed. Say so plainly rather than showing an empty screen."""
        self.duel = None
        self.finished = True
        self.query_one("#duel-statements", Static).update(
            f"[b $error]No duel to fight.[/]\n\n{safe(reason)}"
        )
        self.query_one("#duel-ask", Static).update("[dim]escape to leave[/]")
        self.query_one("#duel-choices", Vertical).remove_children()

    def ask(self) -> None:
        """Ask for the pattern behind the statement at ``self.position``."""
        duel = self.duel
        assert duel is not None
        # Per *ask*, not per duel: a duel asks twice, and remove_children() is
        # deferred, so the first ask's buttons are still mounted when the
        # second ask mounts its own. Same id twice raises DuplicateIds.
        self._generation += 1
        label = chr(ord("A") + self.position)
        self.query_one("#duel-ask", Static).update(
            f"Statement [b $warning]{label}[/] is which pattern?"
        )
        choices = self.query_one("#duel-choices", Vertical)
        choices.remove_children()
        for index, option in enumerate(duel.options):
            choices.mount(Button(f"{index + 1}. {option.name}", id=self._option_id(index)))

    # ---------------------------------------------------------------- answer

    @on(Button.Pressed)
    def on_button(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith(f"duel-opt-{self._generation}-"):
            self.action_pick(int(button_id.rsplit("-", 1)[1]))

    def action_pick(self, index: int) -> None:
        duel = self.duel
        if duel is None or self.awaiting_advance or index >= len(duel.options):
            return

        self.assignment[self.position] = duel.options[index].pattern_id
        self.position += 1
        if self.position < len(duel.problems):
            self.ask()
        else:
            self.judge()

    def judge(self) -> None:
        duel = self.duel
        assert duel is not None
        context = self.app.context
        feedback = judge_duel(context.library, duel, self.assignment)
        elapsed = int((datetime.now(UTC) - self.started_at).total_seconds() * 1000)

        if feedback.correct:
            self.won += 1

        # One attempt per side. Both carry the *joint* verdict — see the module
        # docstring. `chosen_pattern_id` is what they actually said for that
        # statement, so the confusion history stays truthful even when the duel
        # as a whole was correct, and feeds back into which pairs get posed.
        xp_total = 0
        for position, actual in enumerate(duel.pattern_ids):
            problem = duel.problems[position]
            attempt_id = repo.start_attempt(
                context.conn,
                pattern_id=actual,
                mode=GameMode.DUEL,
                seed=duel.seed,
                problem_id=problem.id,
                difficulty=problem.difficulty.value,
            )
            outcome = complete_exercise(
                context.conn,
                attempt_id,
                ExerciseResult(
                    correct=feedback.correct,
                    duration_ms=elapsed,
                    chosen_pattern_id=feedback.assignment[position],
                ),
                library=context.library,
                scheduler=context.scheduler,
                pattern_id=actual,
                mode=GameMode.DUEL,
                difficulty=problem.difficulty,
            )
            xp_total += outcome.xp.total
        context.conn.commit()

        self.show_verdict(feedback, xp_total)

    def show_verdict(self, feedback, xp_total: int) -> None:
        context = self.app.context
        duel = self.duel
        assert duel is not None
        name = context.library.__getitem__

        body: list[str] = []
        if feedback.correct:
            body.append("[b $success]Both right.[/] You separated them.")
        elif feedback.collapsed:
            said = name(feedback.assignment[0]).name
            body.append(
                f"[b $error]You called both of them {safe(said)}.[/]\n"
                "That is not a wrong answer so much as no answer — the two "
                "statements are different, and nothing you did distinguished them."
            )
        elif feedback.swapped:
            body.append(
                "[b $error]Swapped.[/] You named both patterns and put each on the "
                "other's statement. You know the pair; you cannot yet tell which "
                "is which."
            )
        else:
            position = feedback.wrong_positions[0]
            label = chr(ord("A") + position)
            body.append(
                f"[b $error]No.[/] Statement {label} was "
                f"[b]{safe(name(feedback.actual[position]).name)}[/], "
                f"not {safe(name(feedback.assignment[position]).name)}."
            )

        if not feedback.correct and feedback.has_tell:
            body.append(f"\n[b]How to tell:[/]\n{safe(feedback.tell)}")

        for position, (label, _) in enumerate(duel.labelled()):
            body.append(
                f"\n[b $warning]{label}[/] was "
                f"[b]{safe(name(feedback.actual[position]).name)}[/]\n"
                f"{safe(feedback.why(position).strip())}"
            )

        body.append(f"\n[dim]+{xp_total} XP[/]")

        verdict = self.query_one("#duel-verdict", Static)
        verdict.set_class(not feedback.correct, "wrong")
        verdict.update("\n".join(body))
        verdict.display = True

        self.awaiting_advance = True
        self.query_one("#duel-choices", Vertical).remove_children()
        self.query_one("#duel-ask", Static).update(
            "[dim]space to continue[/]"
            if self.round_number < self.rounds
            else "[dim]space to finish[/]"
        )

    # ---------------------------------------------------------------- finish

    def action_advance(self) -> None:
        if not self.awaiting_advance:
            return
        self.query_one("#duel-verdict", Static).display = False
        if self.round_number >= self.rounds:
            self.finish()
        else:
            self.pose()

    def finish(self) -> None:
        self.finished = True
        self.awaiting_advance = False
        self.duel = None
        verdict = self.query_one("#duel-verdict", Static)
        verdict.set_class(self.won < self.rounds, "wrong")
        verdict.update(
            f"[b]{self.won} of {self.rounds} clean.[/]\n"
            + (
                "Nothing got past you."
                if self.won == self.rounds
                else "The ones you lost are the pairs worth drilling."
            )
        )
        verdict.display = True
        self.query_one("#duel-statements", Static).update("")
        self.query_one("#duel-ask", Static).update("[dim]escape to leave[/]")

    def action_leave(self) -> None:
        self.app.pop_screen()
        home = self.app.screen
        if hasattr(home, "refresh_view"):
            home.refresh_view()
