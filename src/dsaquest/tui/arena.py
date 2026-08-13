"""The boss arena.

Two health bars, a clock, and phases that name nothing. The screen owns no
rules: the gate, the damage, the enrage condition and the victory tier all come
from ``boss/``. Its job is to render them and to run the sandbox for the one
phase that needs it.

If the gate is shut the arena refuses to start and shows exactly what is
missing. A gate you can walk through is not a gate.
"""

from __future__ import annotations

from datetime import UTC, datetime

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static, TextArea

from ..art.sprite import load_sprite
from ..boss import conclude, gate_status, next_challenge, open_fight, resolve
from ..boss.fight import Fight
from ..content.exercises import samples_for
from ..content.paths import read_template
from ..domain.boss import Boss, PhaseKind
from ..domain.enums import GameMode
from ..game.modes.complete import exercise_source, find_hole, judge_completion
from ..game.understanding import grade_understanding, remark
from ..learning.mastery import all_mastery
from ..learning.par import format_duration
from ..storage import repositories as repo
from .card import accent_for
from .editor import code_editor
from .master import safe
from .stage import stage_text
from .understanding import UnderstandingPanel

ARENA_CSS = """
#arena-title { padding: 1 2 0 2; text-style: bold; }
#bars { padding: 0 2 1 2; height: auto; }
#arena-mid { layout: horizontal; height: 18; padding: 0 1; }
#arena-left, #arena-right { width: 30; height: 18; padding: 0 1; }
.arena-panel { border: round #2b2822; padding: 0 1; height: 18; }
.panel-head { color: #8a7f6d; text-style: bold; }
#arena-stage { width: 1fr; height: 18; }
#boss-say { padding: 1 2; margin: 0 2; border: round $error; height: auto; }
#arena-clock { padding: 0 2; text-style: bold; }
#arena-clock.urgent { color: $error; }
#arena-body { padding: 1 2; margin: 1 2; border: round $primary; height: auto; }
#arena-choices { padding: 0 2; height: auto; }
#arena-choices Button { width: 100%; margin: 0 0 1 0; }
#arena-verdict { padding: 1 2; margin: 1 2; border: round $success; height: auto; }
#arena-verdict.lost { border: round $error; }
"""


def _bar(current: int, total: int, width: int = 28) -> str:
    filled = max(0, int(round(current / total * width))) if total else 0
    return "█" * filled + "░" * (width - filled)


class ArenaScreen(Screen):
    """One boss fight."""

    BINDINGS = [
        Binding("escape", "leave", "Leave"),
        Binding("1", "pick(0)", "", show=False),
        Binding("2", "pick(1)", "", show=False),
        Binding("3", "pick(2)", "", show=False),
        Binding("4", "pick(3)", "", show=False),
        Binding("ctrl+s", "submit", "Submit", show=False),
        Binding("space", "advance", "Continue", show=False),
    ]

    def __init__(self, boss: Boss, *, seed: int | None = None) -> None:
        super().__init__()
        self.boss = boss
        self.fight: Fight | None = None
        self.phase = "gate"
        self._pinned_seed = seed
        self._seed_counter = 0
        self._generation = 0
        self._ticker = None
        self.checking = False
        self.pending_code: str | None = None
        self.check_answer = None
        self.check_verdict = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="arena-title")
        yield Static(id="bars")
        with Horizontal(id="arena-mid"):
            with Vertical(id="arena-left", classes="arena-panel"):
                yield Static(id="trial-panel")
            yield Static(id="arena-stage")
            with Vertical(id="arena-right", classes="arena-panel"):
                yield Static(id="blows-panel")
        yield Static(id="boss-say")
        yield Static(id="arena-clock")
        yield VerticalScroll(Static(id="arena-body"))
        yield Vertical(id="arena-choices")
        yield Static(id="arena-verdict")
        yield Footer()

    # ---------------------------------------------------------------- setup

    def on_mount(self) -> None:
        self.title = self.boss.name
        self.sub_title = self.boss.title
        self.query_one("#arena-clock", Static).display = False
        self.query_one("#arena-verdict", Static).display = False

        self.refresh_bars()

        context = self.app.context
        mastery = all_mastery(context.conn, context.library, scheduler=context.scheduler)
        status = gate_status(context.conn, self.boss, mastery)

        if not status.open:
            self.show_gate(status)
            return
        self.begin()

    def _seed(self) -> int:
        if self._pinned_seed is not None:
            self._seed_counter += 1
            return self._pinned_seed + self._seed_counter
        return int(datetime.now(UTC).timestamp() * 1000) % 2**31

    def _option_id(self, index: int) -> str:
        return f"arena-{index}-{self._generation}"

    def say(self, pool: str) -> None:
        from random import Random

        lines = self.boss.pool(pool) or ("...",)
        line = lines[Random(self._seed()).randrange(len(lines))]
        blockers = getattr(self, "_blockers", "")
        self.query_one("#boss-say", Static).update(
            f'[i]"{safe(line.replace("{blockers}", blockers))}"[/]'
        )

    def show_gate(self, status) -> None:
        self._blockers = ", ".join(status.blockers)
        self.say("gate_locked")
        lines = ["[b]IT WILL NOT FIGHT YOU YET[/]", ""]
        for requirement in status.requirements:
            colour = "green" if requirement.met else "red"
            lines.append(f"  [{colour}]{safe(requirement.describe())}[/]")
        if status.final_test_needed:
            mark = "✓" if status.final_test_passed else "✗"
            colour = "green" if status.final_test_passed else "red"
            lines.append(f"  [{colour}]{'master final test':<16}{'passed':>14}  {mark}[/]")
        lines += ["", "[dim]escape — leave[/]"]
        self.query_one("#arena-body", Static).update("\n".join(lines))
        self.refresh_bars()
        self.phase = "locked"

    def begin(self) -> None:
        self.fight = open_fight(self.boss)
        self.say("intro")
        self.refresh_bars()
        self.next_phase()

    # ------------------------------------------------------------ rendering

    def refresh_bars(self) -> None:
        """The boss's health as one wide bar, and yours as the blows you have left.

        A second bar for the player would be symmetrical and less useful. What
        a player needs to know is not a percentage but a count: how many more
        times can I be wrong. Blows are exactly that — player health divided by
        what a mistake costs — and three ticks going to two is legible at a
        glance in a way 75 going to 50 is not.
        """
        fight = self.fight
        boss_hp = fight.boss_hp if fight else self.boss.boss_hp
        player_hp = fight.player_hp if fight else self.boss.player_hp
        width = max(20, self.size.width - 6)

        filled = int(round(boss_hp / self.boss.boss_hp * width)) if self.boss.boss_hp else 0
        accent = accent_for(self.boss.id)
        enraged = "   [b red]ENRAGED[/]" if fight and fight.enraged else ""

        # Name left, health right, on one line — the reference's arrangement,
        # and the two things you look at first.
        count = f"{boss_hp} / {self.boss.boss_hp}"
        gap = max(1, width - len(self.boss.name) - len(count))
        self.query_one("#arena-title", Static).update(
            f"[b #ece5d6]{safe(self.boss.name)}[/]{' ' * gap}[#8a7f6d]{count}[/]{enraged}\n"
            f"[{accent}]{safe(self.boss.title)}[/]   [dim]TIER {self.boss.tier.name}[/]"
        )

        blows = max(0, -(-player_hp // self.boss.damage_taken))
        total_blows = max(1, -(-self.boss.player_hp // self.boss.damage_taken))
        ticks = " ".join(
            f"[{accent}]▬▬▬[/]" if i < blows else "[#3a352c]▬▬▬[/]" for i in range(total_blows)
        )
        self.query_one("#bars", Static).update(
            f"[#c04a3a]{'█' * filled}[/][#2b2822]{'░' * (width - filled)}[/]\n{ticks}"
        )
        self.refresh_portrait()

    def on_resize(self, event) -> None:
        """The stage is painted to the widget's size, so it must be repainted."""
        self.refresh_portrait()

    def refresh_portrait(self) -> None:
        """The room, with the boss standing in it."""
        from ..tui.roster import sprite_for

        stage = self.query_one("#arena-stage", Static)
        path = sprite_for(self.boss.id)
        sprite = load_sprite(path) if path.is_file() else None
        size = stage.size
        beaten = self.fight is not None and self.fight.boss_hp <= 0
        stage.update(
            stage_text(
                sprite,
                width=max(40, size.width or 60),
                height=max(16, size.height or 18),
                lit=not beaten,
            )
        )
        self.refresh_panels()

    def refresh_panels(self) -> None:
        """The two side panels: what is being asked, and what has landed."""
        accent = accent_for(self.boss.id)
        challenge = self.fight.current if self.fight else None

        trial = ["[#8a7f6d]THE TRIAL[/]", ""]
        if challenge is not None:
            trial.append(f"[b #ece5d6]{safe(challenge.phase.title)}[/]")
            trial.append("")
            trial.append(f"[#a89e8d]{safe(challenge.phase.kind.label)}[/]")
            trial.append("")
            trial.append(f"[#6b6459]phase[/]   {challenge.number} of {challenge.total}")
        else:
            trial.append(f"[#a89e8d]{safe(self.boss.title)}[/]")
        self.query_one("#trial-panel", Static).update("\n".join(trial))

        blows = ["[#8a7f6d]SCROLL OF BLOWS[/]", ""]
        outcomes = list(self.fight.outcomes) if self.fight else []
        if not outcomes:
            blows.append("[#6b6459]The ring is drawn; no blow has landed.[/]")
        for outcome in outcomes[-6:]:
            mark = f"[{accent}]landed[/]" if outcome.cleared else "[#c04a3a]taken[/]"
            blows.append(f"{mark}  [#a89e8d]{safe(outcome.challenge.phase.title)}[/]")
        self.query_one("#blows-panel", Static).update("\n".join(blows))

    def next_phase(self) -> None:
        assert self.fight is not None
        context = self.app.context
        challenge = next_challenge(
            context.conn, context.library, context.bank, self.fight, seed=self._seed()
        )
        if challenge is None:
            self.finish()
            return

        self.query_one("#arena-verdict", Static).display = False
        choices = self.query_one("#arena-choices", Vertical)
        choices.remove_children()
        self._generation += 1

        head = (
            f"[b]PHASE {challenge.number}/{challenge.total}[/]   "
            f"[dim]{challenge.phase.kind.label}[/]\n"
            f"[b yellow]{safe(challenge.phase.title)}[/]\n\n"
        )

        if challenge.kind in (PhaseKind.RECOGNISE, PhaseKind.SURVIVE):
            problem = challenge.problem
            assert problem is not None and challenge.hunter is not None
            self.query_one("#arena-body", Static).update(
                head
                + f"[b]{safe(problem.title)}[/]\n\n{safe(problem.statement.strip())}\n\n"
                + f"[dim]{safe(problem.constraints.strip())}[/]\n\n"
                + "[b]Which pattern?[/]   [dim]nothing here will tell you[/]"
            )
            for index, (label, option) in enumerate(challenge.hunter.labelled()):
                choices.mount(Button(f"{label}.  {safe(option.name)}", id=self._option_id(index)))
        elif challenge.kind is PhaseKind.EXPLAIN:
            # The pattern MUST be named here. An explain phase is Mode B, and
            # Mode B is defined by naming the pattern and hiding everything
            # else. Withholding it does not make the phase harder, it makes it
            # unanswerable: a four-face boss picks one of its patterns at
            # random, so the player would be reciting the invariant of
            # something they have no way to identify, and losing health for it.
            assert challenge.recall is not None
            self.query_one("#arena-body", Static).update(
                head
                + f"[b cyan]{safe(challenge.recall.pattern.name)}[/]\n\n"
                + "State it from memory: the signals that reveal it, the invariant\n"
                + "that makes it correct, and what it costs.\n\n"
                + "[dim]ctrl+s to commit[/]"
            )
            editor = code_editor("", id="arena-editor", show_line_numbers=False)
            choices.mount(editor)
            self.set_timer(0.05, editor.focus)
        else:
            assert challenge.template_file and challenge.hole_id
            source = read_template(challenge.template_file)
            hole = find_hole(source, challenge.hole_id)
            self.query_one("#arena-body", Static).update(
                head
                + f"[b]TODO: {safe(hole.prompt)}[/]\n\n"
                + f"[dim]{safe(exercise_source(source, challenge.hole_id))}[/]\n\n"
                + "[dim]ctrl+s to strike[/]"
            )
            editor = code_editor("", id="arena-editor")
            choices.mount(editor)
            self.set_timer(0.05, editor.focus)

        self.phase = "fighting"
        self.start_clock()

    # --------------------------------------------------------------- clock

    def start_clock(self) -> None:
        clock = self.query_one("#arena-clock", Static)
        clock.display = True
        self.tick()
        self._ticker = self.set_interval(1.0, self.tick)

    def stop_clock(self) -> None:
        if self._ticker is not None:
            self._ticker.stop()
            self._ticker = None
        self.query_one("#arena-clock", Static).display = False

    def tick(self) -> None:
        if self.fight is None or self.fight.current is None or self.phase != "fighting":
            return
        challenge = self.fight.current
        elapsed = challenge.watch.elapsed_ms
        remaining = challenge.budget.remaining_ms(elapsed)
        if remaining is None:
            return
        clock = self.query_one("#arena-clock", Static)
        clock.set_class(remaining <= 30_000, "urgent")
        clock.update(f"{format_duration(remaining)}  {challenge.budget.bar(elapsed)}")
        if challenge.budget.expired(elapsed):
            self.answer(None)

    # -------------------------------------------------------------- answers

    @on(Button.Pressed)
    def on_button(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("arena-"):
            self.answer(int(event.button.id.split("-")[1]))

    def action_pick(self, index: int) -> None:
        if self.phase != "fighting" or self.fight is None or self.fight.current is None:
            return
        hunter = self.fight.current.hunter
        if hunter is not None and index < len(hunter.options):
            self.answer(index)

    def action_submit(self) -> None:
        if self.phase != "fighting" or self.fight is None or self.fight.current is None:
            return
        if self.checking:
            return
        challenge = self.fight.current
        try:
            text = self.query_one("#arena-editor", TextArea).text
        except Exception:
            return

        if challenge.kind is PhaseKind.EXPLAIN:
            self.answer(text)
            return

        # The code is frozen *here*, before the three questions are asked, so
        # no amount of time spent stating your reasoning can improve what gets
        # judged. That is what lets the clock stop instead of running: a check
        # that eats your solve time is a check people learn to skip.
        self.pending_code = text
        self.stop_clock()
        self.checking = True
        choices = self.query_one("#arena-choices", Vertical)
        choices.remove_children()
        choices.mount(
            UnderstandingPanel(note="Say it before it is judged. Nothing here costs you health.")
        )

    @on(UnderstandingPanel.Submitted)
    def on_understanding(self, event: UnderstandingPanel.Submitted) -> None:
        if not self.checking or self.fight is None or self.fight.current is None:
            return
        self.checking = False
        context = self.app.context
        self.check_answer = event.answer
        self.check_verdict = grade_understanding(
            context.library[self.fight.current.pattern_id], event.answer
        )
        self.query_one("#arena-choices", Vertical).remove_children()
        self.query_one("#arena-clock", Static).update("[yellow]Compiling and running…[/]")
        self.judge_strike(self.pending_code or "")

    @work(thread=True)
    def judge_strike(self, answer: str) -> None:
        """The implement phase is the only one that needs the sandbox."""
        challenge = self.fight.current  # type: ignore[union-attr]
        report = judge_completion(
            read_template(challenge.template_file),
            challenge.hole_id,
            answer,
            list(samples_for(challenge.template_file)),
        )
        self.app.call_from_thread(self.answer, report.accepted)

    def answer(self, given: object) -> None:
        if self.fight is None or self.fight.current is None:
            return
        context = self.app.context
        self.stop_clock()

        outcome = resolve(
            context.conn, context.library, self.fight, given, scheduler=context.scheduler
        )
        self.query_one("#arena-choices", Vertical).remove_children()
        self.refresh_bars()

        was_enraged = self.fight.enraged
        self.say("phase_won" if outcome.cleared else "phase_lost")

        panel = self.query_one("#arena-verdict", Static)
        panel.set_class(not outcome.cleared, "lost")
        lines = [
            f"[b green]-{outcome.challenge.phase.damage} to the beast[/]"
            if outcome.cleared
            else f"[b red]-{self.boss.damage_taken} to you[/]"
        ]
        if outcome.timed_out:
            lines.append("[dim]the clock ran out[/]")
        if outcome.detail:
            lines += ["", safe(outcome.detail)]
        if self.check_verdict is not None:
            lines += ["", self.record_understanding(outcome)]
        if was_enraged and self.fight.failures == self.boss.enrage_after:
            lines += ["", "[b red]IT IS ENRAGED[/]  [dim]no hints; everything is doubled[/]"]
        lines += ["", "[dim]space — continue[/]"]
        panel.update("\n".join(lines))
        panel.display = True

        self.phase = "between"

    def record_understanding(self, outcome) -> str:
        """Store the check against this phase's attempt, and say what it showed.

        Recorded whatever the code did — the pair is the evidence. A check kept
        only when the code passed would answer a different question.
        """
        context = self.app.context
        verdict = self.check_verdict
        answer = self.check_answer
        assert verdict is not None and answer is not None
        # The challenge from the *outcome*, not fight.current — resolving a
        # phase advances the fight, so by now fight.current is the next phase
        # (or None) and its attempt id is not the one this check belongs to.
        code_correct = outcome.cleared
        repo.record_understanding(
            context.conn,
            attempt_id=outcome.challenge.attempt_id,
            pattern_id=verdict.pattern_id,
            mode=GameMode.BOSS,
            key_idea=answer.key_idea,
            complexity=answer.complexity,
            invariant=answer.invariant,
            key_idea_ok=verdict.part("key_idea").sound,
            complexity_ok=verdict.part("complexity").sound,
            invariant_ok=verdict.part("invariant").sound,
            answered=verdict.answered,
            code_correct=code_correct,
        )
        context.conn.commit()
        said = remark(verdict, code_correct=code_correct)
        self.check_verdict = None
        self.check_answer = None
        self.pending_code = None
        style = "green" if verdict.sound else "yellow"
        return f"[{style}]{safe(said)}[/]"

    def action_advance(self) -> None:
        if self.phase == "between":
            if self.fight is not None and self.fight.over:
                self.finish()
            else:
                self.next_phase()

    # -------------------------------------------------------------- the end

    def finish(self) -> None:
        assert self.fight is not None
        context = self.app.context
        self.stop_clock()
        verdict = conclude(context.conn, self.fight, seed=self._seed())

        self.query_one("#arena-choices", Vertical).remove_children()
        self.query_one("#boss-say", Static).update(f'[i]"{safe(verdict.line)}"[/]')
        self.refresh_bars()

        if verdict.won:
            head = f"[b green]DEFEATED[/]   [b]{(verdict.grade or '').upper()}[/]"
        else:
            head = "[b red]IT STANDS[/]"

        lines = [
            head,
            "",
            f"  {format_duration(verdict.duration_ms)}  "
            f"[dim]target {format_duration(verdict.target_ms)}[/]",
            f"  {verdict.player_hp} health remaining",
            f"  respect {verdict.respect_delta:+d} → {verdict.respect_total}",
        ]
        if verdict.weakest:
            lines += ["", "[b]Train before you return[/]", "  " + ", ".join(verdict.weakest)]
        record = verdict.record
        if record.best_grade:
            lines += ["", f"[dim]best: {record.best_grade} in {record.attempts} attempt(s)[/]"]
        lines += ["", "[dim]escape — leave[/]"]

        panel = self.query_one("#arena-verdict", Static)
        panel.set_class(not verdict.won, "lost")
        panel.update("\n".join(lines))
        panel.display = True

        self.query_one("#arena-body", Static).update("")
        self.phase = "done"

    def action_leave(self) -> None:
        self.stop_clock()
        self.app.pop_screen()
