"""The Textual application.

Two screens carry the MVP: a campaign map and a session runner. The session
runner drives whatever the planner queued, switching between recognition and
code completion without the learner choosing a mode — interleaving is the point,
and asking "which mode?" every time invites picking the comfortable one.

Judging runs on a worker thread. Compiling and executing C++ takes a second or
two, and doing it on the UI thread freezes the terminal mid-keystroke.
"""

from __future__ import annotations

from datetime import UTC, datetime

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static, TextArea

from ..content.exercises import samples_for
from ..content.paths import read_template
from ..context import AppContext
from ..domain.enums import GameMode
from ..game.levels import progress
from ..game.modes import build_round_for, judge_round
from ..game.modes.complete import exercise_source, find_hole, judge_completion, parse_holes
from ..game.session import ExerciseResult, begin_exercise, complete_exercise
from ..learning.mastery import all_mastery
from ..learning.planner import PlannedItem, build_session
from ..storage import repositories as repo
from .master import MASTER_CSS, MasterScreen

CSS = (
    """
Screen { background: $surface; }

#banner {
    height: auto; padding: 1 2; background: $panel;
    border: round $primary; margin: 1 2 0 2;
}
#xpbar { color: $success; }

.world { color: $accent; text-style: bold; padding: 1 0 0 0; }
.locked { color: $text-disabled; }
.done { color: $success; }
.active { color: $warning; }

#statement {
    padding: 1 2; border: round $primary; margin: 1 2;
    height: auto; max-height: 60%;
}
#prompt { padding: 0 2; color: $text-muted; }
#options { padding: 0 2; height: auto; }
#options Button { width: 100%; margin: 0 0 1 0; }

#feedback {
    padding: 1 2; margin: 1 2; border: round $success; height: auto;
}
#feedback.wrong { border: round $error; }

#editor { height: 1fr; margin: 1 2; border: round $primary; }
#verdict { padding: 1 2; height: auto; }

.dim { color: $text-muted; }
.good { color: $success; text-style: bold; }
.bad { color: $error; text-style: bold; }
"""
    + MASTER_CSS
)


class HomeScreen(Screen):
    BINDINGS = [
        Binding("p", "practice", "Practice"),
        Binding("r", "review", "Review due"),
        Binding("t", "train", "Train under a master"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="banner")
        yield VerticalScroll(Static(id="map"))
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        context: AppContext = self.app.context
        profile = context.refresh_profile()
        level = progress(profile.xp)
        streak = repo.get_streak(context.conn, "daily")
        plan = build_session(
            context.conn, context.library, context.bank, scheduler=context.scheduler
        )

        banner = (
            f"[b cyan]DSA QUEST[/]\n"
            f"[b]Level {level.level}[/] {level.title}   "
            f"[green]{level.bar(28)}[/] "
            f"{level.xp_into_level:,}/{level.xp_for_level:,} XP\n"
            f"[yellow]{streak.current} day streak[/]   "
            f"{'[b green]' if plan.due_count else '[dim]'}{plan.due_count} due[/]\n\n"
            f"[dim]{plan.recommendation}[/]"
        )
        self.query_one("#banner", Static).update(banner)

        mastery = all_mastery(context.conn, context.library, scheduler=context.scheduler)
        unlocked = repo.unlocked_patterns(context.conn)

        lines: list[str] = []
        world = None
        for pattern in context.library:
            if pattern.world != world:
                world = pattern.world
                lines.append(f"\n[b magenta]WORLD {world}[/]")
            record = mastery[pattern.id]
            playable = pattern.id in unlocked or not pattern.prerequisites
            if not playable:
                mark, style = "[🔒]", "dim"
            elif record.overall >= 0.65:
                mark, style = "[✓]", "green"
            elif record.started:
                mark, style = "[★]", "yellow"
            else:
                mark, style = "[ ]", "white"
            lines.append(
                f"  [{style}]{mark} {pattern.name:<32}[/] "
                f"[{style}]{'█' * int(record.overall * 12):<12}[/] {record.overall:>4.0%}"
            )
        self.query_one("#map", Static).update("\n".join(lines))

    def action_practice(self) -> None:
        self.app.push_screen(SessionScreen(review_only=False))

    def action_review(self) -> None:
        self.app.push_screen(SessionScreen(review_only=True))

    def action_train(self) -> None:
        """Train under whichever master has unfinished teaching."""
        context = self.app.context
        if not context.masters:
            self.notify("No masters are teaching yet.", severity="warning")
            return
        master = next(iter(context.masters.values()))
        self.app.push_screen(MasterScreen(master, context.curricula))


class SessionScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("1", "pick(0)", "A", show=False),
        Binding("2", "pick(1)", "B", show=False),
        Binding("3", "pick(2)", "C", show=False),
        Binding("4", "pick(3)", "D", show=False),
        Binding("ctrl+s", "submit_code", "Submit", show=False),
        Binding("space", "advance", "Next", show=False),
    ]

    def __init__(self, *, review_only: bool) -> None:
        super().__init__()
        self.review_only = review_only
        self.queue: list[PlannedItem] = []
        self.index = 0
        self.awaiting_advance = False
        self.attempt_id: int | None = None
        self.started_at = datetime.now(UTC)
        self.current: object | None = None
        self.xp_earned = 0
        self.correct_count = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="prompt")
        yield VerticalScroll(Static(id="statement"))
        yield Vertical(id="options")
        yield Static(id="feedback")
        yield Footer()

    def on_mount(self) -> None:
        context: AppContext = self.app.context
        plan = build_session(
            context.conn,
            context.library,
            context.bank,
            scheduler=context.scheduler,
            size=self.app.session_size,
        )
        items = list(plan.items)
        if self.review_only:
            items = [i for i in items if i.reason == "due for review"]
        self.queue = items
        self.query_one("#feedback", Static).display = False
        self.present()

    # ---------------------------------------------------------------- flow

    def present(self) -> None:
        if self.index >= len(self.queue):
            self.finish()
            return

        item = self.queue[self.index]
        self.awaiting_advance = False
        self.query_one("#feedback", Static).display = False
        self.query_one("#options", Vertical).remove_children()

        if item.mode is GameMode.HUNTER:
            self.present_hunter(item)
        else:
            self.present_completion(item)

    def present_hunter(self, item: PlannedItem) -> None:
        context: AppContext = self.app.context
        seed = int(datetime.now(UTC).timestamp() * 1000) % 2**31
        round_ = build_round_for(
            context.conn, context.library, context.bank, item.pattern_id, seed=seed
        )
        self.current = round_
        self.attempt_id = begin_exercise(
            context.conn,
            pattern_id=item.pattern_id,
            mode=GameMode.HUNTER,
            seed=seed,
            difficulty=item.difficulty,
            problem_id=round_.problem.id,
        )
        self.started_at = datetime.now(UTC)

        self.query_one("#prompt", Static).update(
            f"[dim]{self.index + 1}/{len(self.queue)}  ·  {item.reason}  ·  "
            f"{round_.problem.difficulty.value}[/]"
        )
        self.query_one("#statement", Static).update(
            f"[b]{round_.problem.title}[/]\n\n{round_.problem.statement.strip()}\n\n"
            f"[dim]{round_.problem.constraints.strip()}[/]\n\n"
            f"[b]Which pattern should you use?[/]"
        )
        options = self.query_one("#options", Vertical)
        for position, (label, option) in enumerate(round_.labelled()):
            options.mount(Button(f"{label}.  {option.name}", id=f"opt{position}"))

    def present_completion(self, item: PlannedItem) -> None:
        context: AppContext = self.app.context
        pattern = context.library[item.pattern_id]
        source = read_template(pattern.template_file)
        holes = parse_holes(source)
        seed = int(datetime.now(UTC).timestamp() * 1000) % 2**31
        hole = holes[seed % len(holes)]

        self.current = (pattern.template_file, hole.id)
        self.attempt_id = begin_exercise(
            context.conn,
            pattern_id=item.pattern_id,
            mode=GameMode.COMPLETE,
            seed=seed,
            difficulty=item.difficulty,
        )
        self.started_at = datetime.now(UTC)

        self.query_one("#prompt", Static).update(
            f"[dim]{self.index + 1}/{len(self.queue)}  ·  {item.reason}  ·  "
            f"{pattern.name}[/]\n[b]TODO: {hole.prompt}[/]   [dim](ctrl+s to submit)[/]"
        )
        self.query_one("#statement", Static).update(f"[dim]{exercise_source(source, hole.id)}[/]")
        editor = TextArea(
            "", language="cpp", id="editor", show_line_numbers=True, tab_behavior="indent"
        )
        self.query_one("#options", Vertical).mount(editor)
        self.set_timer(0.1, editor.focus)

    # ------------------------------------------------------------- answers

    @on(Button.Pressed)
    def on_button(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("opt"):
            self.answer_hunter(int(event.button.id.removeprefix("opt")))

    def action_pick(self, index: int) -> None:
        if self.awaiting_advance:
            return
        from ..game.modes.hunter import HunterRound

        if isinstance(self.current, HunterRound) and index < len(self.current.options):
            self.answer_hunter(index)

    def answer_hunter(self, chosen: int) -> None:
        from ..game.modes.hunter import HunterRound

        if self.awaiting_advance or not isinstance(self.current, HunterRound):
            return
        context: AppContext = self.app.context
        round_ = self.current
        feedback = judge_round(context.library, round_, chosen)
        elapsed = int((datetime.now(UTC) - self.started_at).total_seconds() * 1000)

        outcome = complete_exercise(
            context.conn,
            self.attempt_id,
            ExerciseResult(
                correct=feedback.correct,
                duration_ms=elapsed,
                chosen_pattern_id=feedback.chosen_pattern_id,
            ),
            library=context.library,
            scheduler=context.scheduler,
            pattern_id=round_.problem.pattern,
            mode=GameMode.HUNTER,
            difficulty=round_.problem.difficulty,
        )
        self.record(outcome, feedback.correct)

        body = []
        if feedback.correct:
            body.append(f"[b green]Correct.[/] {context.library[feedback.actual_pattern_id].name}")
        else:
            body.append(
                f"[b red]No.[/] That was "
                f"[b]{context.library[feedback.actual_pattern_id].name}[/], "
                f"not {context.library[feedback.chosen_pattern_id].name}."
            )
            if feedback.has_tell:
                body.append(f"\n[b]How to tell:[/]\n{feedback.tell}")
        body.append(f"\n[b]Why:[/]\n{feedback.why.strip()}")
        if feedback.signals:
            body.append("\n[b]Cues present:[/] " + ", ".join(feedback.signals))
        if feedback.classic_ref:
            body.append(f"\n[dim]Drills: {feedback.classic_ref}[/]")
        body.append(f"\n[dim]{outcome.xp.explain()}[/]")

        self.show_feedback("\n".join(body), correct=feedback.correct)

    def action_submit_code(self) -> None:
        if self.awaiting_advance or not isinstance(self.current, tuple):
            return
        try:
            editor = self.query_one("#editor", TextArea)
        except Exception:
            return
        self.query_one("#prompt", Static).update("[yellow]Compiling and running…[/]")
        self.judge_code(editor.text)

    @work(thread=True)
    def judge_code(self, answer: str) -> None:
        template_file, hole_id = self.current  # type: ignore[misc]
        source = read_template(template_file)
        report = judge_completion(source, hole_id, answer, list(samples_for(template_file)))
        self.app.call_from_thread(self.finish_code, report, answer)

    def finish_code(self, report, answer: str) -> None:
        context: AppContext = self.app.context
        item = self.queue[self.index]
        elapsed = int((datetime.now(UTC) - self.started_at).total_seconds() * 1000)
        accepted = report.accepted

        outcome = complete_exercise(
            context.conn,
            self.attempt_id,
            ExerciseResult(
                correct=accepted,
                duration_ms=elapsed,
                verdict=report.report.verdict,
                source=answer,
                tests_passed=report.report.passed,
                tests_total=report.report.total,
                compile_log=report.report.compile_log,
            ),
            library=context.library,
            scheduler=context.scheduler,
            pattern_id=item.pattern_id,
            mode=GameMode.COMPLETE,
            difficulty=item.difficulty,
        )
        self.record(outcome, accepted)

        if accepted:
            body = [f"[b green]Accepted.[/] {report.report.passed}/{report.report.total} tests"]
        else:
            failure = report.report.first_failure
            body = [f"[b red]{report.report.verdict.label}[/]"]
            if report.report.compile_log.strip():
                body.append(f"\n{report.report.compile_log.strip()[:800]}")
            elif failure is not None:
                body.append(f"\n{failure.name}: {failure.diff_hint}")
            template_file, hole_id = self.current  # type: ignore[misc]
            hole = find_hole(read_template(template_file), hole_id)
            body.append(f"\n[dim]Reference answer:[/]\n{hole.body}")
        body.append(f"\n[dim]{outcome.xp.explain()}[/]")
        self.show_feedback("\n".join(body), correct=accepted)

    # ------------------------------------------------------------- helpers

    def record(self, outcome, correct: bool) -> None:
        self.xp_earned += outcome.xp.total
        self.correct_count += int(correct)
        extras = []
        for pattern_id in outcome.newly_unlocked:
            extras.append(f"[b magenta]Unlocked: {pattern_id}[/]")
        for achievement in outcome.achievements:
            extras.append(f"[b yellow]Achievement: {achievement.name}[/]")
        for level in outcome.levels_gained:
            extras.append(f"[b cyan]Level {level}![/]")
        if extras:
            self.notify("\n".join(extras), timeout=6)

    def show_feedback(self, markup: str, *, correct: bool) -> None:
        panel = self.query_one("#feedback", Static)
        panel.set_class(not correct, "wrong")
        panel.update(markup + "\n\n[dim]space — next[/]")
        panel.display = True
        self.query_one("#options", Vertical).remove_children()
        self.awaiting_advance = True

    def action_advance(self) -> None:
        if not self.awaiting_advance:
            return
        self.index += 1
        self.present()

    def finish(self) -> None:
        total = len(self.queue)
        self.app.pop_screen()
        self.app.notify(
            f"Session complete — {self.correct_count}/{total} correct, {self.xp_earned} XP earned",
            timeout=8,
        )
        home = self.app.screen
        if isinstance(home, HomeScreen):
            home.refresh_view()


class DsaQuestApp(App):
    CSS = CSS
    TITLE = "DSA Quest"
    BINDINGS = [Binding("ctrl+q", "quit", "Quit")]

    def __init__(
        self, context: AppContext, *, review_only: bool = False, session_size: int = 8
    ) -> None:
        super().__init__()
        self.context = context
        self.review_only = review_only
        self.session_size = session_size
        self.pending_screen = None

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())
        if self.pending_screen is not None:
            self.push_screen(self.pending_screen)
        elif self.review_only:
            self.push_screen(SessionScreen(review_only=True))
