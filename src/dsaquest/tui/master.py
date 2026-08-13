"""Training under a master — the teach → drill → judge screen.

The screen is a small state machine:

    GREET  ->  TEACH  ->  DRILL  ->  FEEDBACK  ->  DRILL | FLUENT

Nothing here decides pedagogy. The screen asks ``lessons`` what to show and
``world`` what the master says; its only job is to render them and collect a
keystroke.
"""

from __future__ import annotations

from datetime import UTC, datetime

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.markup import escape
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static

from ..content.lessons import CurriculumSet
from ..domain.lesson import Drill, Stage
from ..learning.par import format_duration
from ..lessons import current_stage, deal, grade, greet, teach
from ..lessons.session import progress_summary
from ..lessons.trial import Trial, judge_trial, open_trial, pending_trial
from ..storage import repositories as repo
from ..world.character import Master


def safe(text: str) -> str:
    """Escape content before it is interpolated into markup.

    Authored content is full of C++, and C++ is full of square brackets.
    Unescaped, ``a[i] & 1`` renders as ``a & 1`` because ``[i]`` is parsed as an
    italic tag — the learner is shown a *different expression* from the one they
    were asked about, and the rest of the line silently turns italic. Every
    string that comes from content goes through this.
    """
    return escape(text)


MASTER_CSS = """
#portrait { width: 26; padding: 0 1; color: $text-muted; }
#say { padding: 1 2; border: round $accent; margin: 1 2; height: auto; }
#lesson { padding: 1 2; margin: 0 2; height: auto; }
#drill { padding: 1 2; margin: 1 2; border: round $primary; height: auto; }
#choices { padding: 0 2; height: auto; }
#choices Button { width: 100%; margin: 0 0 1 0; }
#reply { margin: 0 2; }
#verdict { padding: 1 2; margin: 1 2; border: round $success; height: auto; }
#verdict.wrong { border: round $error; }
#track { padding: 0 2; color: $text-muted; }
#clock { padding: 0 2; text-style: bold; }
#clock.urgent { color: $error; }
#statement { padding: 1 2; margin: 1 2; border: round $warning; height: auto; }
"""


class MasterScreen(Screen):
    """One training session with one master."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Leave"),
        Binding("1", "pick(0)", "A", show=False),
        Binding("2", "pick(1)", "B", show=False),
        Binding("3", "pick(2)", "C", show=False),
        Binding("4", "pick(3)", "D", show=False),
        Binding("space", "advance", "Continue", show=False),
        Binding("enter", "advance", "Continue", show=False),
    ]

    def __init__(
        self, master: Master, curricula: CurriculumSet, *, seed: int | None = None
    ) -> None:
        super().__init__()
        #: Pinning the seed makes a whole session reproducible - the same
        #: drills in the same order, the same trial problem, the same dialogue.
        #: Tests rely on it; it is also what would let a session be replayed.
        self._pinned_seed = seed
        self._seed_counter = 0
        self.master = master
        self.curriculum = curricula[master.id]
        self.stage: Stage | None = None
        self.drill: Drill | None = None
        self.trial: Trial | None = None
        self._ticker = None
        self.phase = "greet"
        self.started = datetime.now(UTC)
        self.drills_done = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(self.master.portrait, id="portrait")
        yield Static(id="say")
        yield Static(id="track")
        yield Static(id="clock")
        yield VerticalScroll(Static(id="lesson"), Static(id="statement"), Static(id="drill"))
        yield Vertical(id="choices")
        yield Input(placeholder="type the idiom, then Enter", id="reply")
        yield Static(id="verdict")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#reply", Input).display = False
        self.query_one("#verdict", Static).display = False
        self.query_one("#statement", Static).display = False
        self.query_one("#clock", Static).display = False
        self.title = self.master.name
        self.sub_title = self.master.title

        conn = self.app.context.conn
        self.say(greet(conn, self.master, seed=self._seed()))
        self.stage = current_stage(conn, self.curriculum)
        self.refresh_track()

        self.resume()

    # ------------------------------------------------------------ rendering

    def _seed(self) -> int:
        if self._pinned_seed is not None:
            self._seed_counter += 1
            return self._pinned_seed + self._seed_counter
        return int(datetime.now(UTC).timestamp() * 1000) % 2**31

    def say(self, line: str) -> None:
        self.query_one("#say", Static).update(f'[i]"{safe(line)}"[/]')

    def refresh_track(self) -> None:
        conn = self.app.context.conn
        marks = []
        for stage, progress in progress_summary(conn, self.curriculum):
            if progress.is_fluent:
                marks.append(f"[green]✓ {safe(stage.secret.idiom)}[/]")
            elif progress.is_taught:
                marks.append(f"[yellow]● {safe(stage.secret.idiom)}[/]")
            else:
                marks.append(f"[dim]○ {safe(stage.secret.idiom)}[/]")
        respect = repo.get_respect(conn, self.master.id)
        self.query_one("#track", Static).update("   ".join(marks) + f"     [b]respect {respect}[/]")

    def show_lesson(self) -> None:
        assert self.stage is not None
        conn = self.app.context.conn
        teaching = teach(conn, self.master, self.curriculum, self.stage, seed=self._seed())
        self.say(teaching.intro)

        secret = teaching.secret
        body = [
            f"[b]SECRET {teaching.stage_number}/{teaching.stage_count} — "
            f"{safe(secret.name.upper())}[/]",
            f"\n    [b cyan]{safe(secret.idiom)}[/]\n",
            safe(secret.teaches),
            "\n[b]DEMONSTRATION[/]",
        ]
        for demo in secret.demonstrations:
            note = f"   [dim]{safe(demo.note)}[/]" if demo.note else ""
            body.append(f"    {safe(demo.expression):<20} = {safe(demo.result)}{note}")
        if secret.watch_out:
            body.append("\n[b yellow]WATCH FOR[/]")
            for item in secret.watch_out:
                body.append(f"    [yellow]![/] {safe(item.warning)}")
                if item.why:
                    body.append(f"      [dim]{safe(item.why)}[/]")
        if teaching.memorise_line:
            body.append(f'\n[b]"{safe(teaching.memorise_line)}"[/]')
        body.append("\n[dim]space — begin the drills[/]")

        self.query_one("#lesson", Static).update("\n".join(body))
        self.query_one("#drill", Static).display = False
        self.phase = "teach"

    def show_drill(self) -> None:
        assert self.stage is not None
        conn = self.app.context.conn
        self.drill = deal(conn, self.curriculum, self.stage, seed=self._seed())
        if self.drill is None:
            self.finish_stage()
            return

        self.query_one("#lesson", Static).display = False
        self.query_one("#verdict", Static).display = False
        panel = self.query_one("#drill", Static)
        panel.display = True
        self.drills_done += 1
        panel.update(
            f"[dim]drill {self.drills_done} · {self.drill.kind.value}[/]\n\n"
            f"{safe(self.drill.prompt)}"
        )

        choices = self.query_one("#choices", Vertical)
        choices.remove_children()
        reply = self.query_one("#reply", Input)

        if self.drill.options:
            reply.display = False
            for index, option in enumerate(self.drill.options):
                choices.mount(Button(f"{chr(65 + index)}.  {safe(option)}", id=f"opt{index}"))
        else:
            reply.display = True
            reply.value = ""
            self.set_timer(0.05, reply.focus)

        self.phase = "drill"

    # -------------------------------------------------------------- answers

    @on(Button.Pressed)
    def on_button(self, event: Button.Pressed) -> None:
        if not (event.button.id and event.button.id.startswith("opt")):
            return
        index = int(event.button.id.removeprefix("opt"))
        if self.phase == "trial":
            self.answer_trial(index)
        else:
            self.answer(index)

    @on(Input.Submitted)
    def on_submitted(self, event: Input.Submitted) -> None:
        if self.phase == "drill":
            self.answer(event.value)

    def action_pick(self, index: int) -> None:
        if self.phase == "trial" and self.trial and index < len(self.trial.round.options):
            self.answer_trial(index)
        elif self.phase == "drill" and self.drill and index < len(self.drill.options):
            self.answer(index)

    def answer(self, given: int | str) -> None:
        assert self.drill is not None and self.stage is not None
        text = self.drill.options[given] if isinstance(given, int) else given
        elapsed = int((datetime.now(UTC) - self.started).total_seconds() * 1000)

        outcome = grade(
            self.app.context.conn,
            self.master,
            self.curriculum,
            self.stage,
            self.drill,
            text,
            duration_ms=elapsed,
            seed=self._seed(),
        )

        self.query_one("#choices", Vertical).remove_children()
        self.query_one("#reply", Input).display = False
        self.say(outcome.master_line)

        panel = self.query_one("#verdict", Static)
        panel.set_class(not outcome.correct, "wrong")
        head = "[b green]Correct.[/]" if outcome.correct else "[b red]No.[/]"
        if not outcome.correct:
            head += f"  The answer is [b]{safe(self.drill.answer)}[/]"
        lines = [head, "", safe(outcome.explanation)]
        if outcome.became_fluent:
            lines += [
                "",
                f"[b yellow]★ FLUENT[/] — {safe(outcome.verdict.reason)}",
                f"[green]+{outcome.respect_delta} respect[/]",
            ]
        elif outcome.verdict.exhausted:
            lines += ["", f"[dim]{safe(outcome.verdict.reason)}[/]"]
        else:
            lines += ["", f"[dim]{safe(outcome.verdict.reason)}[/]"]
        lines += ["", "[dim]space — continue[/]"]
        panel.update("\n".join(lines))
        panel.display = True

        self.refresh_track()
        self.phase = (
            "fluent" if (outcome.became_fluent or outcome.verdict.exhausted) else "feedback"
        )

    # ---------------------------------------------------------------- flow

    def action_advance(self) -> None:
        if self.phase == "teach" or self.phase == "feedback":
            self.show_drill()
        elif self.phase in ("fluent", "trial_done"):
            self.finish_stage()

    def finish_stage(self) -> None:
        self.drills_done = 0
        self.query_one("#verdict", Static).display = False
        self.query_one("#drill", Static).display = False
        self.resume()

    def resume(self) -> None:
        """Decide what comes next: a pending trial, the next lesson, or done.

        A trial always takes priority over teaching the next secret. Moving on
        without testing would leave the loop at teach-and-drill, which is the
        half that proves nothing.
        """
        conn = self.app.context.conn
        self.refresh_track()

        trial_stage = pending_trial(conn, self.curriculum)
        if trial_stage is not None:
            self.show_trial(trial_stage)
            return

        self.stage = current_stage(conn, self.curriculum)
        self.query_one("#statement", Static).display = False
        self.stop_clock()

        if self.stage is None:
            from ..world.character import speak

            self.say(speak(conn, self.master, "gate_open", seed=self._seed()))
            panel = self.query_one("#lesson", Static)
            panel.display = True
            panel.update(
                "[b green]Every secret is fluent, and every trial is passed.[/]\n\n"
                "[dim]His final test is what remains — nothing will be named.[/]\n\n"
                "[dim]escape — leave[/]"
            )
            self.phase = "done"
        else:
            self.query_one("#lesson", Static).display = True
            self.show_lesson()

    # ----------------------------------------------------------------- trial

    def show_trial(self, stage) -> None:
        """The pattern goes hidden and a clock starts."""
        context = self.app.context
        self.trial = open_trial(
            context.conn,
            self.master,
            context.library,
            context.bank,
            self.curriculum,
            stage,
            seed=self._seed(),
        )
        trial = self.trial

        self.say(trial.intro)
        self.query_one("#lesson", Static).display = False
        self.query_one("#drill", Static).display = False
        self.query_one("#reply", Input).display = False
        self.query_one("#verdict", Static).display = False

        statement = self.query_one("#statement", Static)
        statement.display = True
        statement.update(
            f"[b yellow]TRIAL — {safe(trial.stage.secret.name)}[/]   "
            f"[dim]{trial.problem.difficulty.value}[/]\n\n"
            f"[b]{safe(trial.problem.title)}[/]\n\n"
            f"{safe(trial.problem.statement.strip())}\n\n"
            f"[dim]{safe(trial.problem.constraints.strip())}[/]\n\n"
            f"[b]Which pattern should you use?[/]   [dim]nothing here will tell you[/]"
        )

        choices = self.query_one("#choices", Vertical)
        choices.remove_children()
        for index, (label, option) in enumerate(trial.round.labelled()):
            choices.mount(Button(f"{label}.  {safe(option.name)}", id=f"opt{index}"))

        self.phase = "trial"
        self.start_clock()

    def start_clock(self) -> None:
        clock = self.query_one("#clock", Static)
        clock.display = True
        self.tick()
        self._ticker = self.set_interval(1.0, self.tick)

    def stop_clock(self) -> None:
        if self._ticker is not None:
            self._ticker.stop()
            self._ticker = None
        self.query_one("#clock", Static).display = False

    def tick(self) -> None:
        if self.trial is None or self.phase != "trial":
            return
        trial = self.trial
        elapsed = trial.watch.elapsed_ms
        remaining = trial.budget.remaining_ms(elapsed)
        if remaining is None:
            return

        clock = self.query_one("#clock", Static)
        clock.set_class(remaining <= 30_000, "urgent")
        clock.update(
            f"{format_duration(remaining)}  {trial.budget.bar(elapsed)}   "
            f"[dim]target {format_duration(trial.budget.target_ms)}[/]"
        )

        if trial.budget.expired(elapsed):
            self.answer_trial(None)

    def answer_trial(self, chosen_index: int | None) -> None:
        assert self.trial is not None
        context = self.app.context
        self.stop_clock()

        verdict = judge_trial(
            context.conn,
            self.master,
            context.library,
            self.curriculum,
            self.trial,
            chosen_index,
            scheduler=context.scheduler,
            seed=self._seed(),
        )

        self.query_one("#choices", Vertical).remove_children()
        self.say(verdict.master_line)

        panel = self.query_one("#verdict", Static)
        panel.set_class(not verdict.passed, "wrong")

        if verdict.passed:
            head = "[b green]PASSED.[/]"
        elif verdict.timed_out:
            head = "[b yellow]TIME.[/]  [dim]a speed result, not a knowledge one[/]"
        else:
            actual = context.library[verdict.actual_pattern_id].name
            head = f"[b red]No.[/]  That was [b]{safe(actual)}[/]."

        lines = [head, "", f"[dim]{format_duration(verdict.elapsed_ms)} elapsed[/]"]
        if verdict.tell:
            lines += ["", "[b]How to tell:[/]", safe(verdict.tell)]
        lines += ["", "[b]Why:[/]", safe(verdict.why.strip())]
        lines += [
            "",
            f"respect {verdict.respect_delta:+d} → {verdict.respect_total}"
            f"     xp +{verdict.outcome.xp.total}",
            "",
            "[dim]space — continue[/]",
        ]
        panel.update("\n".join(lines))
        panel.display = True

        self.trial = None
        self.refresh_track()
        self.phase = "trial_done"
