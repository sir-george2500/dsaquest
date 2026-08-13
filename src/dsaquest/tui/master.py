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
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static

from ..content.lessons import CurriculumSet
from ..domain.lesson import Drill, Stage
from ..lessons import current_stage, deal, grade, greet, teach
from ..lessons.session import progress_summary
from ..storage import repositories as repo
from ..world.character import Master

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

    def __init__(self, master: Master, curricula: CurriculumSet) -> None:
        super().__init__()
        self.master = master
        self.curriculum = curricula[master.id]
        self.stage: Stage | None = None
        self.drill: Drill | None = None
        self.phase = "greet"
        self.started = datetime.now(UTC)
        self.drills_done = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(self.master.portrait, id="portrait")
        yield Static(id="say")
        yield Static(id="track")
        yield VerticalScroll(Static(id="lesson"), Static(id="drill"))
        yield Vertical(id="choices")
        yield Input(placeholder="type the idiom, then Enter", id="reply")
        yield Static(id="verdict")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#reply", Input).display = False
        self.query_one("#verdict", Static).display = False
        self.title = self.master.name
        self.sub_title = self.master.title

        conn = self.app.context.conn
        self.say(greet(conn, self.master, seed=self._seed()))
        self.stage = current_stage(conn, self.curriculum)
        self.refresh_track()

        if self.stage is None:
            self.query_one("#lesson", Static).update(
                "[b green]Every secret is fluent.[/]\n\n[dim]The final test is what remains.[/]"
            )
            self.phase = "done"
        else:
            self.show_lesson()

    # ------------------------------------------------------------ rendering

    def _seed(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000) % 2**31

    def say(self, line: str) -> None:
        self.query_one("#say", Static).update(f'[i]"{line}"[/]')

    def refresh_track(self) -> None:
        conn = self.app.context.conn
        marks = []
        for stage, progress in progress_summary(conn, self.curriculum):
            if progress.is_fluent:
                marks.append(f"[green]✓ {stage.secret.idiom}[/]")
            elif progress.is_taught:
                marks.append(f"[yellow]● {stage.secret.idiom}[/]")
            else:
                marks.append(f"[dim]○ {stage.secret.idiom}[/]")
        respect = repo.get_respect(conn, self.master.id)
        self.query_one("#track", Static).update("   ".join(marks) + f"     [b]respect {respect}[/]")

    def show_lesson(self) -> None:
        assert self.stage is not None
        conn = self.app.context.conn
        teaching = teach(conn, self.master, self.curriculum, self.stage, seed=self._seed())
        self.say(teaching.intro)

        secret = teaching.secret
        body = [
            f"[b]SECRET {teaching.stage_number}/{teaching.stage_count} — {secret.name.upper()}[/]",
            f"\n    [b cyan]{secret.idiom}[/]\n",
            secret.teaches,
            "\n[b]DEMONSTRATION[/]",
        ]
        for demo in secret.demonstrations:
            note = f"   [dim]{demo.note}[/]" if demo.note else ""
            body.append(f"    {demo.expression:<20} = {demo.result}{note}")
        if secret.watch_out:
            body.append("\n[b yellow]WATCH FOR[/]")
            for item in secret.watch_out:
                body.append(f"    [yellow]![/] {item.warning}")
                if item.why:
                    body.append(f"      [dim]{item.why}[/]")
        if teaching.memorise_line:
            body.append(f'\n[b]"{teaching.memorise_line}"[/]')
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
            f"[dim]drill {self.drills_done} · {self.drill.kind.value}[/]\n\n{self.drill.prompt}"
        )

        choices = self.query_one("#choices", Vertical)
        choices.remove_children()
        reply = self.query_one("#reply", Input)

        if self.drill.options:
            reply.display = False
            for index, option in enumerate(self.drill.options):
                choices.mount(Button(f"{chr(65 + index)}.  {option}", id=f"opt{index}"))
        else:
            reply.display = True
            reply.value = ""
            self.set_timer(0.05, reply.focus)

        self.phase = "drill"

    # -------------------------------------------------------------- answers

    @on(Button.Pressed)
    def on_button(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("opt"):
            self.answer(int(event.button.id.removeprefix("opt")))

    @on(Input.Submitted)
    def on_submitted(self, event: Input.Submitted) -> None:
        if self.phase == "drill":
            self.answer(event.value)

    def action_pick(self, index: int) -> None:
        if self.phase == "drill" and self.drill and index < len(self.drill.options):
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
            head += f"  The answer is [b]{self.drill.answer}[/]"
        lines = [head, "", outcome.explanation]
        if outcome.became_fluent:
            lines += [
                "",
                f"[b yellow]★ FLUENT[/] — {outcome.verdict.reason}",
                f"[green]+{outcome.respect_delta} respect[/]",
            ]
        elif outcome.verdict.exhausted:
            lines += ["", f"[dim]{outcome.verdict.reason}[/]"]
        else:
            lines += ["", f"[dim]{outcome.verdict.reason}[/]"]
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
        elif self.phase == "fluent":
            self.finish_stage()

    def finish_stage(self) -> None:
        conn = self.app.context.conn
        self.stage = current_stage(conn, self.curriculum)
        self.drills_done = 0
        self.query_one("#verdict", Static).display = False
        self.query_one("#drill", Static).display = False
        self.query_one("#lesson", Static).display = True
        self.refresh_track()

        if self.stage is None:
            from ..world.character import speak

            self.say(speak(conn, self.master, "gate_open", seed=self._seed()))
            self.query_one("#lesson", Static).update(
                "[b green]Every secret is fluent.[/]\n\n"
                "[dim]His final test is what remains — nothing will be named.[/]\n\n"
                "[dim]escape — leave[/]"
            )
            self.phase = "done"
        else:
            self.show_lesson()
