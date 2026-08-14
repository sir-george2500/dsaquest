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
from .card import (
    BAD,
    BODY,
    FAINT,
    FRAME,
    GOLD,
    GOOD,
    INK,
    MEASURE,
    MUTE,
    RULE,
    SEALED,
    accent_for,
    clip,
    gauge,
)
from .editor import code_editor
from .master import safe
from .stage import stage_text
from .understanding import UnderstandingPanel

#: The room needs a gutter. `#arena-mid` used to put the side panels flush
#: against the stage, so the leftmost pillar was painted hard against the
#: panel's own border — one continuous run of box-drawing and stone that read
#: as a single broken widget rather than as a room seen between two dossiers.
#:
#: The panels also collapse below 100 columns. At 80 they took 60 of the 80
#: available and left 20 for a stage whose minimum is 40, so the room
#: overflowed its widget, was cropped, and the boss was painted off centre.
#: A narrow terminal gets the room and drops the dossiers.
ARENA_CSS = f"""
#arena-title {{ padding: 1 2 0 2; text-style: bold; }}
#bars {{ padding: 0 2 1 2; height: auto; }}
#arena-mid {{ layout: horizontal; height: 18; padding: 0 2; }}
#arena-left {{ width: 30; height: 18; padding: 0 1; margin: 0 2 0 0; }}
#arena-right {{ width: 30; height: 18; padding: 0 1; margin: 0 0 0 2; }}
.arena-panel {{ border: round {RULE}; padding: 0 1; height: 18; }}
.panel-head {{ color: {MUTE}; text-style: bold; }}
#arena-stage {{ width: 1fr; height: 18; }}
/* A left bar, as on the master screen and on a warden card. Boxed, the
   guardian's line cost six rows — two of border, two of padding, one of margin
   and one of speech — which at eighty by twenty-four is a quarter of the
   terminal spent framing one sentence. */
/* A margin below as well as above. Without it the clock sat on the row under
   the guardian's last word and read as part of what it was saying. */
#boss-say {{
    padding: 0 2; margin: 1 2; height: auto;
    border-left: outer {FRAME}; max-width: {MEASURE + 6};
}}
#arena-clock {{ padding: 0 5; text-style: bold; }}
#arena-clock.urgent {{ color: {BAD}; }}
#arena-scroll {{ height: 1fr; scrollbar-gutter: stable; }}
#arena-body {{
    padding: 1 2; margin: 1 2; border: round {FRAME}; height: auto;
    max-width: {MEASURE + 6};
}}
#arena-choices {{ padding: 0 5; height: auto; max-width: {MEASURE + 6}; }}

#arena-verdict {{
    padding: 1 2; margin: 1 2; border: round {GOOD}; height: auto;
    max-width: {MEASURE + 6};
}}
#arena-verdict.lost {{ border: round {BAD}; }}
"""


#: A sentinel distinguishing "not looked for yet" from "looked for, absent" —
#: eight of the twelve guardians have no sprite drawn, and `None` is a real
#: answer for them that must not send us back to the filesystem every redraw.
_UNLOADED = object()


def _and_list(items) -> str:
    items = list(items)
    if len(items) < 2:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


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
        #: What the room was last painted for, and the sprite it was painted
        #: with. Both are caches; see ``refresh_portrait``.
        self._stage_key: tuple[int, int, bool] | None = None
        self._sprite = _UNLOADED
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
        # One scroll region for the question, the answer and the verdict. They
        # used to be three siblings after a container that had already taken
        # every remaining row: at eighty by twenty-four the screen overflowed,
        # Textual scrolled it, and the fight opened with the boss's name, both
        # health bars and the phase title *above the top of the terminal*. You
        # could not see what you were fighting or how close it was to dying.
        yield VerticalScroll(
            Static(id="arena-body"),
            Vertical(id="arena-choices"),
            Static(id="arena-verdict"),
            id="arena-scroll",
        )
        yield Footer()

    # ---------------------------------------------------------------- setup

    def on_mount(self) -> None:
        self.title = self.boss.name
        self.sub_title = self.boss.title
        self.query_one("#arena-clock", Static).display = False
        self.query_one("#arena-verdict", Static).display = False

        self.fit_panels()
        self.refresh_bars()

        context = self.app.context
        mastery = all_mastery(context.conn, context.library, scheduler=context.scheduler)
        status = gate_status(context.conn, self.boss, mastery, context.masters)

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
        # The guardians' `gate_locked` lines are written as "Not yet.
        # {blockers}", so what goes in has to read as a clause and not as a
        # CSV. It still is not a sentence — see the note in the report — but
        # "recognition, understanding and the master's final test" is at least
        # English where "a, b, c, d, e" was not.
        self._blockers = _and_list(status.blockers)
        self.say("gate_locked")
        lines = [f"[b {INK}]IT WILL NOT FIGHT YOU YET[/]", ""]
        # `describe()` already ends in its own ✓/✗, so the rows carry no second
        # mark. They also carry no red: not having got there yet is not a
        # failure, and five crimson lines read as one.
        for requirement in status.requirements:
            lines.append(
                f"  [{BODY if requirement.met else FAINT}]{safe(requirement.describe())}[/]"
            )
        if status.final_test_needed:
            passed = status.final_test_passed
            lines.append(
                f"  [{BODY if passed else FAINT}]{'master final test':<20}"
                f"{'passed':>10}  {'✓' if passed else '✗'}[/]"
            )
        lines += ["", f"[{FAINT}]escape — leave[/]"]
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

        # A bar the width of the terminal is a banner, not a gauge. Drawn full
        # bleed in solid crimson it was by a wide margin the loudest thing in
        # the arena — louder than the boss, louder than the question — and at
        # full health that meant the screen opened on a hundred-and-fourteen
        # cell block of red. Thirty-six cells is legible and stays a gauge.
        # A third of the row, capped. Fixed at thirty-six it was forty-five per
        # cent of an eighty column terminal, and a crimson slab that wide is the
        # loudest thing on a screen whose loudest thing should be the boss.
        gauge_w = max(16, min(36, width // 3))
        share = boss_hp / self.boss.boss_hp if self.boss.boss_hp else 0.0
        accent = accent_for(self.boss.id)
        enraged = f"   [b {BAD}]ENRAGED[/]" if fight and fight.enraged else ""

        # Name left, health right, on one line — the reference's arrangement,
        # and the two things you look at first.
        count = f"{boss_hp} / {self.boss.boss_hp}"
        gap = max(1, width - len(self.boss.name) - len(count))
        self.query_one("#arena-title", Static).update(
            f"[b {INK}]{safe(self.boss.name)}[/]{' ' * gap}[{MUTE}]{count}[/]{enraged}\n"
            f"[{accent}]{safe(self.boss.title)}[/]   "
            f"[{FAINT}]tier[/] [{MUTE}]{safe(self.boss.tier.name.title())}[/]"
        )

        blows = max(0, -(-player_hp // self.boss.damage_taken))
        total_blows = max(1, -(-self.boss.player_hp // self.boss.damage_taken))
        ticks = " ".join(
            f"[{accent}]▬▬▬[/]" if i < blows else f"[{SEALED}]▬▬▬[/]" for i in range(total_blows)
        )
        # Both readouts on one line and both labelled. They used to be two
        # unlabelled rows in two different visual languages — a solid bar for
        # the boss, spaced ticks for you — with nothing saying which was which.
        self.query_one("#bars", Static).update(
            f"[{FAINT}]it[/]   {gauge(share, gauge_w, BAD)}    [{FAINT}]you[/]  {ticks}"
        )
        self.refresh_portrait()

    #: Below this the dossiers are dropped and the whole width goes to the room.
    #: Two 30-column panels out of 80 leave 20 for a stage whose minimum width
    #: is 40: the room overflowed its own widget, was cropped on both sides,
    #: and the pillars — placed relative to a width the widget did not have —
    #: marched through the middle where the boss stands.
    #: Two thirty-column dossiers, four columns of margin and four of padding
    #: cost sixty-eight. A hundred left thirty-two for a room whose minimum
    #: width is forty, so `stage_text` painted a forty-column room into a
    #: thirty-two column widget: the pillars, placed relative to a width the
    #: widget did not have, were cropped, and the boss — centred in the room
    #: rather than in the widget — came out as a sliver of shoulder against a
    #: torn wall. The room needs forty-four of its own before the panels get
    #: any, so the panels wait until a hundred and twelve.
    PANELS_NEED = 112

    #: And below this many rows the room goes entirely. A fourteen-row room is
    #: the smallest that holds a twelve-row sprite with floor under its feet and
    #: wall above its head; under thirty-two rows of terminal, fourteen for the
    #: room leaves nothing for the question.
    STAGE_NEEDS = 32

    def on_resize(self, event) -> None:
        """The stage is painted to the widget's size, so it must be repainted."""
        self.fit_panels()
        self.refresh_portrait()

    def fit_panels(self) -> None:
        """Give the room what is left over, not a fixed eighteen rows.

        Eighteen rows out of twenty-four is three quarters of a short terminal
        spent on scenery, with the question you are being asked pushed off the
        bottom. The room is the occasion; it is not the fight.

        """
        room = self.size.width >= self.PANELS_NEED
        for side in ("#arena-left", "#arena-right"):
            self.query_one(side).display = room

        # Below this the room goes entirely. Twenty-two rows of terminal cannot
        # hold a title, two gauges, a room, the guardian speaking, a clock and a
        # question: squeezed to eight rows the room cropped the boss at the
        # mouth and still left one row for the question, so the fight opened on
        # a picture of half a face and nothing to answer.
        self.query_one("#arena-mid").display = self.size.height >= self.STAGE_NEEDS

        height = max(14, min(18, self.size.height - 20))
        self.query_one("#arena-mid").styles.height = height
        for widget in ("#arena-left", "#arena-right", "#arena-stage"):
            self.query_one(widget).styles.height = height

    def refresh_portrait(self) -> None:
        """The room, with the boss standing in it.

        Painted only when what it depends on has changed. The room is a full
        text buffer — measured at 3.9 ms to build plus 3.8 ms to render for a
        120x18 stage, and 5.9 plus 7.3 at 160x32, after the run-merging in
        ``stage._to_text``; before it, 20.6 plus 31.1 and 31.2 plus 49.0 — and
        ``refresh_bars`` calls this on every answer, every phase change and
        every resize event, so it was repainting an identical picture several
        times a second and re-reading the sprite off disk each time. Nothing on
        this screen changes the room except its size and whether the torches
        are lit.
        """
        from ..tui.roster import sprite_for

        stage = self.query_one("#arena-stage", Static)
        size = stage.size
        beaten = self.fight is not None and self.fight.boss_hp <= 0
        width = max(40, size.width or 60)
        height = max(16, size.height or 18)
        key = (width, height, not beaten)
        if key == self._stage_key:
            self.refresh_panels()
            return
        self._stage_key = key

        if self._sprite is _UNLOADED:
            path = sprite_for(self.boss.id)
            self._sprite = load_sprite(path) if path.is_file() else None
        stage.update(stage_text(self._sprite, width=width, height=height, lit=not beaten))
        self.refresh_panels()

    def refresh_panels(self) -> None:
        """The two side panels: the whole trial, and what has landed.

        Both used to hold three lines in an eighteen-row box — "THE TRIAL", a
        phase title and "phase 1 of 4" on the left; on the right, the single
        sentence "The ring is drawn; no blow has landed." Two thirds of each
        panel stood empty on the most theatrical screen in the game.

        The left one now shows every phase at once, marked with what happened to
        it, which is the question a player actually has mid-fight: how much of
        this is left. The right keeps the scroll of blows and gains the
        guardian's dossier under it — tier, health, what a miss costs, and your
        own record against it. Every value is already in content or the save
        file; none of it is invented to fill the box.

        The colours here were five raw hex literals — ``#8a7f6d``, ``#ece5d6``,
        ``#a89e8d``, ``#6b6459``, ``#c04a3a`` — which are MUTE, INK, BODY, FAINT
        and BAD spelled out. They are the palette's names now, so a change to
        the palette reaches this screen like every other.
        """
        accent = accent_for(self.boss.id)
        challenge = self.fight.current if self.fight else None
        outcomes = list(self.fight.outcomes) if self.fight else []
        cleared_by_number = {o.challenge.number: o.cleared for o in outcomes}
        width = max(20, self.query_one("#arena-left").content_size.width or 26)

        trial = [f"[b {MUTE}]THE TRIAL[/]", ""]
        for number, phase in enumerate(self.boss.phases, start=1):
            here = challenge is not None and challenge.number == number
            done = cleared_by_number.get(number)
            if done is True:
                mark, style = f"[{GOOD}]✓[/]", BODY
            elif done is False:
                mark, style = f"[{BAD}]✗[/]", FAINT
            elif here:
                mark, style = f"[{accent}]▸[/]", INK
            else:
                mark, style = f"[{SEALED}]·[/]", SEALED
            trial.append(
                f"{mark} [{'b ' if here else ''}{style}]{safe(clip(phase.title, width - 2))}[/]"
            )
            trial.append(f"  [{FAINT if here else SEALED}]{safe(phase.kind.label)}[/]")
            trial.append("")
        if challenge is not None:
            trial.append(f"[{FAINT}]phase {challenge.number} of {challenge.total}[/]")
        self.query_one("#trial-panel", Static).update("\n".join(trial))

        blows = [f"[b {MUTE}]SCROLL OF BLOWS[/]", ""]
        if not outcomes:
            blows.append(f"[{SEALED}]The ring is drawn;[/]")
            blows.append(f"[{SEALED}]no blow has landed.[/]")
        for outcome in outcomes[-4:]:
            mark = f"[{GOOD}]landed[/]" if outcome.cleared else f"[{BAD}]taken[/]"
            blows.append(
                f"{mark}  [{BODY}]{safe(clip(outcome.challenge.phase.title, width - 8))}[/]"
            )

        record = repo.get_boss_record(self.app.context.conn, self.boss.id)
        rows = (
            ("TIER", self.boss.tier.name.title()),
            ("HEALTH", str(self.boss.boss_hp)),
            ("A MISS", f"-{self.boss.damage_taken}"),
            ("FOUGHT", str(record.attempts) if record.attempts else "never"),
            ("BEST", (record.best_grade or "—").upper()),
        )
        label = max(len(name) for name, _ in rows)
        blows += ["", f"[b {MUTE}]THE GUARDIAN[/]", ""]
        for name, value in rows:
            gap = max(1, width - label - len(value))
            blows.append(f"[{FAINT}]{name:<{label}}[/]{' ' * gap}[{BODY}]{value}[/]")
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
            f"[b $warning]{safe(challenge.phase.title)}[/]\n\n"
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
                + f"[b $secondary]{safe(challenge.recall.pattern.name)}[/]\n\n"
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
        # The game's one bar, not `Budget.bar`'s ``░`` hatch — see the note on
        # ``MasterScreen._clock_bar``.
        used = challenge.budget.fraction_used(elapsed)
        clock.update(
            f"{format_duration(remaining)}  {gauge(used, 24, BAD if used >= 0.75 else GOLD)}"
        )
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
        self.query_one("#arena-clock", Static).update("[$warning]Compiling and running…[/]")
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
            f"[b $success]-{outcome.challenge.phase.damage} to the beast[/]"
            if outcome.cleared
            else f"[b $error]-{self.boss.damage_taken} to you[/]"
        ]
        if outcome.timed_out:
            lines.append("[dim]the clock ran out[/]")
        if outcome.detail:
            lines += ["", safe(outcome.detail)]
        if self.check_verdict is not None:
            lines += ["", self.record_understanding(outcome)]
        if was_enraged and self.fight.failures == self.boss.enrage_after:
            lines += ["", "[b $error]IT IS ENRAGED[/]  [dim]no hints; everything is doubled[/]"]
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
            head = f"[b $success]DEFEATED[/]   [b]{(verdict.grade or '').upper()}[/]"
        else:
            head = "[b $error]IT STANDS[/]"

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
