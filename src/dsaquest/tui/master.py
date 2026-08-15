"""Training under a master — the teach → drill → judge screen.

The screen is a small state machine:

    GREET  ->  TEACH  ->  DRILL  ->  FEEDBACK  ->  DRILL | FLUENT

Nothing here decides pedagogy. The screen asks ``lessons`` what to show and
``world`` what the master says; its only job is to render them and collect a
keystroke.
"""

from __future__ import annotations

import textwrap
from datetime import UTC, datetime

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static

from ..art.sprite import load_sprite, sprite_text
from ..codex import read_student
from ..content.lessons import CurriculumSet
from ..domain.lesson import Drill, Stage
from ..learning.par import format_duration
from ..lessons import current_stage, deal, grade, greet, teach
from ..lessons import final_test as ft
from ..lessons.session import progress_summary
from ..lessons.trial import Trial, judge_trial, open_trial, pending_trial
from ..storage import repositories as repo
from ..world.character import Master, speak
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
    letterspace,
)


def safe(text: str) -> str:
    """Escape content before it is interpolated into markup.

    Authored content is full of C++, and C++ is full of square brackets.
    Unescaped, ``a[i] & 1`` renders as ``a & 1`` because ``[i]`` is parsed as an
    italic tag — the learner is shown a *different expression* from the one they
    were asked about, and the rest of the line silently turns italic. Every
    string that comes from content goes through this.

    Not ``textual.markup.escape``: that escapes only bracket *runs* that look
    like a tag, so a nested subscript desynchronises it. ``freq[a[r]]++;`` came
    out as ``freq[a\\[r]]++;`` — the escape character itself printed inside the
    expression. Eight lines across the shipped templates rendered wrong.

    Escaping every ``[`` is what round-trips. Backslashes are deliberately left
    alone: a backslash is only an escape when it precedes ``[``, so doubling
    them corrupts the ``#define`` continuations and character literals that C++
    templates are full of. Measured over 2494 lines of shipped content —
    templates, statements, constraints, hints, invariants, rubric phrases —
    this is the only variant with zero failures.
    """
    return text.replace("[", r"\[")


def _quoted(line: str) -> str:
    """Put a line in quotation marks, unless the author already did.

    The dialogue pools are written bare and the lore's diagnosis lines are
    written with their own quotes around them, because in the Codex they are
    set as a quotation on their own. Wrapping unconditionally printed
    ``""Stop. You can write all four of these...""``.
    """
    text = safe(line.strip())
    if text.startswith('"') and text.endswith('"'):
        return text
    return f'"{text}"'


def hang(text: str, indent: int, width: int = MEASURE) -> str:
    """Wrap ``text`` to ``width`` with every line indented by ``indent``.

    Textual wraps a long line back to column nought, so an indented note's
    second line landed under the table's own left edge — "is correct. Compare
    with -3 % 2, which is -1." began four columns left of the sentence it
    continued, and read as a new item. A hanging indent has to be baked into the
    string; there is no CSS for it.
    """
    pad = " " * indent
    return "\n".join(pad + line for line in textwrap.wrap(text, max(20, width - indent)))


#: Every block on this screen begins at column 5. Bordered boxes sit at margin
#: 2 and spend one column on the border and two on padding; unbordered blocks
#: are padded 5 directly. Before this the say box's text started at column 5,
#: the lesson's at 4 and the track's at 2, so three panels that belong to one
#: master had three left edges.
#:
#: `max-width` on the prose is the other half of it: at 160 columns an
#: unconstrained lesson ran 150 characters to the line.
MASTER_CSS = f"""
/* Fifteen rows, not fourteen. The head reserved exactly the frame's height and
   then spent one of those rows on its own top padding, so the portrait's bottom
   border was cropped off on every master in the game — a framed picture with
   three sides. */
#master-head {{ layout: horizontal; height: 15; padding: 1 2 0 2; max-width: {MEASURE + 10}; }}
#portrait-frame {{ width: 28; height: 14; border: round {FRAME}; padding: 0 1; }}
#portrait {{ width: 24; height: 12; color: {MUTE}; }}
/* Padding-top one, so the dossier's first line sits level with the top of the
   art rather than with the frame's border a row above it. */
#master-meta {{ width: 1fr; height: 14; padding: 1 0 0 3; }}
/* A left bar, not a box. `card.py` had already settled the game's way of
   setting a quotation — an accent rule and italics — and a second, boxed way of
   doing the same thing on the screen the player spends most of their time on
   made the two screens look like two products. The bar is recoloured to the
   master's own accent at mount. */
#say {{
    padding: 0 2; margin: 1 2; height: auto; max-width: {MEASURE + 6};
    border-left: outer {FRAME};
}}
#master-scroll {{ height: 1fr; scrollbar-gutter: stable; }}
#lesson {{ padding: 1 0; margin: 0 5; height: auto; max-width: {MEASURE}; }}
#drill {{
    padding: 1 2; margin: 1 2; border: round {GOLD}; height: auto;
    max-width: {MEASURE + 6};
}}
#choices {{ padding: 0 5; height: auto; max-width: {MEASURE + 6}; }}

#reply {{ margin: 0 4; max-width: {MEASURE + 2}; }}
#verdict {{
    padding: 1 2; margin: 1 2; border: round {GOOD}; height: auto;
    max-width: {MEASURE + 6};
}}
#verdict.wrong {{ border: round {BAD}; }}
#track {{ color: {MUTE}; height: auto; }}
#clock {{ padding: 0 5; text-style: bold; }}
#clock.urgent {{ color: {BAD}; }}
#statement {{
    padding: 1 2; margin: 1 2; border: round {FRAME}; height: auto;
    max-width: {MEASURE + 6};
}}
"""


class MasterScreen(Screen):
    """One training session with one master."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Leave"),
        Binding("1", "pick(0)", "A", show=False),
        Binding("2", "pick(1)", "B", show=False),
        Binding("3", "pick(2)", "C", show=False),
        Binding("4", "pick(3)", "D", show=False),
        Binding("w", "watch", "Watch it", show=False),
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
        #: Buttons carry a generation because remove_children() is deferred:
        #: advancing synchronously would mount opt0 while the old opt0 still
        #: exists, and Textual rejects duplicate ids.
        self._generation = 0
        self.master = master
        self.curriculum = curricula[master.id]
        self.stage: Stage | None = None
        self.drill: Drill | None = None
        self.trial: Trial | None = None
        self.exam: ft.FinalTest | None = None
        self._ticker = None
        self.phase = "greet"
        #: What the master noticed about the player on this visit. Shown
        #: under whatever they are saying until the player starts work.
        self._note = ""
        self.started = datetime.now(UTC)
        self.drills_done = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="master-head"):
            with Vertical(id="portrait-frame"):
                yield Static(self.portrait(), id="portrait")
            # Two widgets, not eight. The dossier and the track are both blocks
            # of lines whose *blank* lines have to change with the terminal's
            # height, and a blank line that is its own widget cannot be given or
            # taken back without mounting and unmounting.
            with Vertical(id="master-meta"):
                yield Static(id="master-dossier")
                yield Static(id="track")
        yield Static(id="say")
        yield Static(id="clock")
        # The answer scrolls with the question. Outside the scroll, `#choices`
        # and `#reply` were laid out after a container that had taken every
        # remaining row, so the four options and the text field sat welded to
        # the footer with nine blank rows between them and the drill they
        # answered — and the trial's problem statement, squeezed into what was
        # left, was clipped to two rows. The player could not read the problem
        # they were being timed on.
        yield VerticalScroll(
            Static(id="lesson"),
            Static(id="statement"),
            Static(id="drill"),
            Vertical(id="choices"),
            Input(placeholder="type the idiom, then Enter", id="reply"),
            Static(id="verdict"),
            id="master-scroll",
        )
        yield Footer()

    def portrait(self):
        """The master's pixel portrait, or their ASCII one if none is drawn yet.

        The sprite is the art this game is supposed to look like. The ASCII
        block was the placeholder and it stayed on this screen long after the
        sprites existed, because only the roster had been wired to them — so a
        player pressing `t` met the placeholder and never the art.
        """
        from ..tui.roster import sprite_for

        path = sprite_for(self.master.id)
        if path.is_file():
            return sprite_text(load_sprite(path))
        return self.master.portrait

    def on_mount(self) -> None:
        self.query_one("#reply", Input).display = False
        self.query_one("#verdict", Static).display = False
        self.query_one("#statement", Static).display = False
        self.query_one("#clock", Static).display = False
        # The person first and the office second, matching the dossier below:
        # the header read "MASTER OF BIT MANIPULATION — Grandmaster Ragine"
        # while three rows under it the same two strings appeared the other way
        # up, so the screen disagreed with itself about which was the name.
        self.title = self.master.title
        self.sub_title = self.master.name

        self.query_one("#say").styles.border_left = ("outer", accent_for(self.master.id))

        conn = self.app.context.conn
        # The greeting, then what they have noticed since you were last
        # here. Arrival is the moment a mentor says it; interrupting a
        # drill to deliver a verdict would be the same words at the worst
        # possible time.
        self._note = self.diagnosis()
        self.say(greet(conn, self.master, seed=self._seed()))
        self.stage = current_stage(conn, self.curriculum)
        self.fit_head()

        self.resume()

    #: Under this many rows the portrait goes. At eighty by twenty-four the head
    #: and the greeting took nineteen of the twenty-two rows available and the
    #: lesson — the entire reason the screen exists — was below the fold, with
    #: nothing on screen to say so. A face is worth a lot; it is not worth the
    #: whole terminal.
    PORTRAIT_NEEDS = 34

    def on_resize(self, event) -> None:
        self.fit_head()

    def fit_head(self) -> None:
        self._room = self.size.height >= self.PORTRAIT_NEEDS
        self.query_one("#portrait-frame").display = self._room
        head = self.query_one("#master-head")
        meta = self.query_one("#master-meta")
        head.styles.height = 15 if self._room else 7
        meta.styles.height = 14 if self._room else 6
        meta.styles.padding = (1, 0, 0, 3) if self._room else (0, 0, 0, 3)
        # A short terminal cannot afford two blank rows between the greeting and
        # the lesson; a tall one looks cramped without them.
        self.query_one("#lesson").styles.padding = (1, 0) if self._room else (0, 0)
        self.refresh_dossier()
        self.refresh_track()

    def meta_width(self) -> int:
        """Columns inside the dossier column, to the cell.

        Derived from ``#master-head``'s own cap rather than from the terminal:
        taken from the terminal the rule came out twenty-five cells too long,
        wrapped, and the dossier showed *two* horizontal rules of different
        lengths one row apart.
        """
        outer = min(self.size.width or 100, MEASURE + 10)
        return max(20, outer - (35 if getattr(self, "_room", True) else 8))

    def refresh_dossier(self) -> None:
        """Region, name, office, rule — spaced to the height of the portrait.

        The blank rows are not decoration: the dossier has to reach the bottom
        of a fourteen-row frame or the column beside the face is a third empty,
        which is what it was. Spread, the four lines land on the art's own
        thirds and the block reads as one piece with the picture. On a short
        terminal there is no picture to reach the bottom of and every blank line
        is a line of the lesson, so they all go.
        """
        accent = accent_for(self.master.id)
        region = self.master.region.replace("-", " ").replace("_", " ").upper()
        width = self.meta_width()
        air = "\n" if getattr(self, "_room", True) else ""
        gap = "\n\n\n" if getattr(self, "_room", True) else "\n"
        self.query_one("#master-dossier", Static).update(
            f"[{MUTE}]{letterspace(region, width)}[/]\n{air}"
            f"[b {INK}]{safe(clip(self.master.title, width))}[/]\n{air}"
            f"[{accent}]{safe(clip(self.master.name, width))}[/]"
            f"{gap}[{RULE}]{'─' * width}[/]"
        )

    # ------------------------------------------------------------ rendering

    def _option_id(self, index: int) -> str:
        return f"opt{index}-{self._generation}"

    def _new_generation(self) -> None:
        self._generation += 1

    def _seed(self) -> int:
        if self._pinned_seed is not None:
            self._seed_counter += 1
            return self._pinned_seed + self._seed_counter
        return int(datetime.now(UTC).timestamp() * 1000) % 2**31

    def say(self, line: str) -> None:
        """What the master says, plus anything they noticed on your way in.

        The remark rides along rather than being said once and lost. Mounting
        greets the player and then immediately opens the first lesson, which
        says something else — so a diagnosis delivered only in the greeting was
        overwritten before a single frame was drawn, and the whole feature was
        invisible while every test of the engine underneath it passed.

        It is set as speech, with a blank line for the beat. A second panel, or
        a heading over it, would turn a remark into an interface element and
        lose the only thing that makes it land: that the person teaching you
        said it.
        """
        said = [_quoted(line)]
        if self._note:
            # The remark comes first: the master stops you at the door with what
            # they have noticed, and only then begins the lesson. After the
            # lesson line it reads as an afterthought about what was just said.
            said.insert(0, _quoted(self._note))
        self.query_one("#say", Static).update("\n\n".join(f"[i]{s}[/]" for s in said))

    def start_work(self) -> None:
        """The player has begun. The remark has been read; stop repeating it."""
        self._note = ""

    def diagnosis(self) -> str:
        """What this master can see in the player that the player cannot.

        Empty most visits, and that is the point. It is gated on six recorded
        attempts and on one dimension standing clear of the others, so a master
        who remarks on your work has actually got something — and one who
        remarks every single time is wallpaper.
        """
        reading = read_student(self.app.context, self.master.id, seed=self._seed())
        return reading.line if reading else ""

    def refresh_track(self) -> None:
        """Seven pips and the one idiom you are on — not seven idioms.

        This line used to print every secret's C++ in full, side by side. Seven
        fragments of code at 120 columns wrapped to three lines, broke mid
        expression (``if (a[l] +`` / ``a[r] < S) ++l;``), and left "respect 0"
        stranded at the end of the third. It was a progress indicator that
        could not be read as one and could not be read as code either. The
        state of seven things is seven marks; the thing you are working on is
        the only one whose text you need.
        """
        conn = self.app.context.conn
        summary = list(progress_summary(conn, self.curriculum))
        pips: list[str] = []
        first_untaught = ""
        for stage, progress in summary:
            if progress.is_fluent:
                pips.append(f"[{GOOD}]●[/]")
            elif progress.is_taught:
                pips.append(f"[{GOLD}]●[/]")
            else:
                pips.append(f"[{SEALED}]○[/]")
                if not first_untaught:
                    first_untaught = stage.secret.idiom
        # The secret the screen is *on*, not the first one not yet taught. Since
        # teaching marks a secret taught the moment it is shown, the track said
        # "working on n & (n - 1)" three rows above a lesson headed `n & 1`.
        current = self.stage.secret.idiom if self.stage is not None else first_untaught
        if not current and summary:
            current = summary[-1][0].secret.idiom
        done = sum(1 for _, p in summary if p.is_fluent)
        respect = repo.get_respect(conn, self.master.id)
        width = max(20, self.meta_width() - 12)
        air = "\n" if getattr(self, "_room", True) else ""
        # The idiom is labelled. Unlabelled and alone on a line below the pips
        # it read as a fragment of something that had failed to render — a bare
        # `n & 1` floating in the dossier with nothing to say what it was.
        self.query_one("#track", Static).update(
            f"{air}{''.join(pips)}   [{FAINT}]{done}/{len(summary)} held[/]   "
            f"[{FAINT}]respect[/] [{MUTE}]{respect}[/]\n{air}"
            f"[{FAINT}]working on[/]  [{accent_for(self.master.id)}]{safe(clip(current, width))}[/]"
        )

    def show_lesson(self) -> None:
        assert self.stage is not None
        conn = self.app.context.conn
        teaching = teach(conn, self.master, self.curriculum, self.stage, seed=self._seed())
        self.say(teaching.intro)

        secret = teaching.secret
        accent = accent_for(self.master.id)
        body = [
            f"[{FAINT}]SECRET {teaching.stage_number}/{teaching.stage_count}[/]",
            f"[b {INK}]{safe(secret.name.upper())}[/]",
            f"\n    [b {accent}]{safe(secret.idiom)}[/]\n",
            f"[{BODY}]{safe(secret.teaches)}[/]",
            f"\n[{FAINT}]DEMONSTRATION[/]",
        ]
        # A demonstration is a table: expression, equals, result — and then, for
        # some of them, a sentence. Set on one line the sentence pushed the row
        # past the measure and Textual broke it wherever the width ran out, so
        # "is odd." and "clear; none of them matter." sat alone at column 0
        # under a table whose columns started at column 4. The note goes under
        # its own row, indented past the equals sign, when it will not fit.
        gutter = 16
        # All the notes go inline or none of them do. Deciding row by row put
        # two of four notes beside their result and two on a line below, which
        # reads as a table that has half broken rather than as a choice.
        inline = all(
            4 + max(gutter, len(demo.expression)) + 6 + len(demo.result) + len(demo.note or "")
            <= MEASURE
            for demo in secret.demonstrations
        )
        for demo in secret.demonstrations:
            expression = safe(demo.expression)
            result = safe(demo.result)
            note = safe(demo.note) if demo.note else ""
            row = f"    [{MUTE}]{expression:<{gutter}}[/][{FAINT}]=[/]  [{INK}]{result}[/]"
            if note and inline:
                body.append(f"{row}   [{FAINT}]{note}[/]")
            elif note:
                # Indent eight, not to the results column: a note is a sentence
                # and the results column leaves it thirty cells, which wraps it
                # again and puts the tail back at column nought.
                body.append(row)
                body.append(f"[{FAINT}]{hang(note, 8)}[/]")
            else:
                body.append(row)
        if secret.watch_out:
            body.append(f"\n[{FAINT}]WATCH FOR[/]")
            for item in secret.watch_out:
                body.append(f"    [{BAD}]![/] [{BODY}]{safe(hang(item.warning, 6)[6:])}[/]")
                if item.why:
                    body.append(f"[{FAINT}]{safe(hang(item.why, 6))}[/]")
        if teaching.memorise_line:
            body.append(f'\n[i {MUTE}]"{safe(teaching.memorise_line)}"[/]')
        # Teach before you test: if the secret has an animation, the student is
        # told so here, while the concept is being explained and before a single
        # drill has judged them.
        if self.animation() is not None:
            body.append("\n[b #d9a441]w — watch it happen, step by step[/]")
        body.append("\n[dim]space — begin the drills[/]")

        self.query_one("#lesson", Static).update("\n".join(body))
        self.query_one("#drill", Static).display = False
        self.phase = "teach"

    def animation(self):
        """The animation for the secret being taught, if one was authored."""
        if self.stage is None:
            return None
        from ..content.animations import animation_for

        wanted = self.stage.secret.animation or self.stage.secret.id
        return animation_for(wanted, self.curriculum.pattern_of(self.stage))

    def action_watch(self) -> None:
        """Open the theatre. Available while teaching, and again during drills.

        A student who has just got a drill wrong is exactly who needs the
        picture, so this is not restricted to the teaching phase.
        """
        if self.phase not in ("teach", "drill"):
            return
        animation = self.animation()
        if animation is None:
            return
        from .theatre import TheatreScreen

        self.app.push_screen(TheatreScreen(animation))

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
        self._new_generation()
        reply = self.query_one("#reply", Input)

        if self.drill.options:
            reply.display = False
            for index, option in enumerate(self.drill.options):
                choices.mount(
                    Button(f"{chr(65 + index)}.  {safe(option)}", id=self._option_id(index))
                )
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
        index = int(event.button.id.removeprefix("opt").split("-")[0])
        if self.phase == "exam":
            self.answer_exam(index)
        elif self.phase == "trial":
            self.answer_trial(index)
        else:
            self.answer(index)

    @on(Input.Submitted)
    def on_submitted(self, event: Input.Submitted) -> None:
        if self.phase == "drill":
            self.answer(event.value)

    def action_pick(self, index: int) -> None:
        self.start_work()
        if self.phase == "exam" and self.exam and self.exam.current:
            if index < len(self.exam.current.round.options):
                self.answer_exam(index)
        elif self.phase == "trial" and self.trial and index < len(self.trial.round.options):
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
        head = "[b $success]Correct.[/]" if outcome.correct else "[b $error]No.[/]"
        if not outcome.correct:
            head += f"  The answer is [b]{safe(self.drill.answer)}[/]"
        lines = [head, "", safe(outcome.explanation)]
        if outcome.became_fluent:
            lines += [
                "",
                f"[b $warning]★ FLUENT[/] — {safe(outcome.verdict.reason)}",
                f"[$success]+{outcome.respect_delta} respect[/]",
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
        self.start_work()
        if self.phase == "teach" or self.phase == "feedback":
            self.show_drill()
        elif self.phase in ("fluent", "trial_done"):
            self.finish_stage()
        elif self.phase == "gate":
            self.start_final_test()

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
            progress = repo.get_master_progress(conn, self.master.id)
            self.say(speak(conn, self.master, "gate_open", seed=self._seed()))
            panel = self.query_one("#lesson", Static)
            panel.display = True

            lines = ["[b $success]Every secret is fluent, and every trial is passed.[/]", ""]
            if progress.passed:
                lines += [
                    f"[b $warning]His final test is behind you.[/]  "
                    f"best {progress.best_score}/{progress.best_total}",
                    "",
                    "[dim]space — sit it again[/]",
                ]
            else:
                lines += [
                    "[b]THE FINAL TEST[/]",
                    "",
                    "[dim]Every secret at once. Nothing will be named. No hints.[/]",
                    "",
                    "[dim]space — begin[/]",
                ]
            lines += ["[dim]escape — leave[/]"]
            panel.update("\n".join(lines))
            self.phase = "gate"
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
            f"[b $warning]TRIAL — {safe(trial.stage.secret.name)}[/]   "
            f"[dim]{trial.problem.difficulty.value}[/]\n\n"
            f"[b]{safe(trial.problem.title)}[/]\n\n"
            f"{safe(trial.problem.statement.strip())}\n\n"
            f"[dim]{safe(trial.problem.constraints.strip())}[/]\n\n"
            f"[b]Which pattern should you use?[/]   [dim]nothing here will tell you[/]"
        )

        choices = self.query_one("#choices", Vertical)
        choices.remove_children()
        self._new_generation()
        for index, (label, option) in enumerate(trial.round.labelled()):
            choices.mount(Button(f"{label}.  {safe(option.name)}", id=self._option_id(index)))

        self.phase = "trial"
        self.start_clock()

    @staticmethod
    def _clock_bar(budget, elapsed: int) -> str:
        """The time budget in the game's one bar language.

        ``Budget.bar`` returns ``█`` and ``░``, and ``░`` is a fifty-per-cent
        hatch: rendered next to the clock it read as static rather than as a
        track, and it was the only bar in the game drawn that way. The timing
        layer keeps its own string for the CLI; the screen draws the fraction.
        """
        used = budget.fraction_used(elapsed)
        return gauge(used, 24, BAD if used >= 0.75 else GOLD)

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
        if self.phase == "exam":
            self.tick_exam()
            return
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
            f"{format_duration(remaining)}  {self._clock_bar(trial.budget, elapsed)}   "
            f"[{FAINT}]target {format_duration(trial.budget.target_ms)}[/]"
        )

        if trial.budget.expired(elapsed):
            self.answer_trial(None)

    def tick_exam(self) -> None:
        if self.exam is None or self.exam.current is None:
            return
        live = self.exam.current
        elapsed = live.watch.elapsed_ms
        remaining = live.budget.remaining_ms(elapsed)
        if remaining is None:
            return
        clock = self.query_one("#clock", Static)
        clock.set_class(remaining <= 30_000, "urgent")
        clock.update(
            f"{format_duration(remaining)}  {self._clock_bar(live.budget, elapsed)}   "
            f"[{FAINT}]{live.number}/{live.total}[/]"
        )
        if live.budget.expired(elapsed):
            self.answer_exam(None)

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
            head = "[b $success]PASSED.[/]"
        elif verdict.timed_out:
            head = "[b $warning]TIME.[/]  [dim]a speed result, not a knowledge one[/]"
        else:
            actual = context.library[verdict.actual_pattern_id].name
            head = f"[b $error]No.[/]  That was [b]{safe(actual)}[/]."

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

    # ------------------------------------------------------------ final test

    def start_final_test(self) -> None:
        """The gate is checked here, not assumed by the caller."""
        context = self.app.context
        if not ft.available(context.conn, self.curriculum):
            self.notify("Every secret must be drilled and tested first.", severity="warning")
            return
        self.exam = ft.open_test(context.conn, context.bank, self.curriculum, seed=self._seed())
        self.say(
            speak(
                context.conn,
                self.master,
                "final_test_intro",
                seed=self._seed(),
                total=self.exam.total,
                required=self.exam.required,
            )
        )
        self.next_exam_round()

    def next_exam_round(self) -> None:
        assert self.exam is not None
        context = self.app.context
        live = ft.next_round(context.conn, context.library, self.exam, seed=self._seed())

        if live is None:
            self.finish_final_test()
            return

        self.query_one("#lesson", Static).display = False
        self.query_one("#drill", Static).display = False
        self.query_one("#verdict", Static).display = False

        statement = self.query_one("#statement", Static)
        statement.display = True
        statement.update(
            f"[b $error]FINAL TEST[/]  [dim]{live.number}/{live.total} · "
            f"{live.problem.difficulty.value} · no hints[/]\n\n"
            f"[b]{safe(live.problem.title)}[/]\n\n"
            f"{safe(live.problem.statement.strip())}\n\n"
            f"[dim]{safe(live.problem.constraints.strip())}[/]\n\n"
            f"[b]Which pattern should you use?[/]"
        )

        choices = self.query_one("#choices", Vertical)
        choices.remove_children()
        self._new_generation()
        for index, (label, option) in enumerate(live.round.labelled()):
            choices.mount(Button(f"{label}.  {safe(option.name)}", id=self._option_id(index)))

        self.phase = "exam"
        self.start_clock()

    def answer_exam(self, chosen_index: int | None) -> None:
        assert self.exam is not None
        self.stop_clock()
        ft.answer_round(
            self.app.context.conn,
            self.app.context.library,
            self.exam,
            chosen_index,
            scheduler=self.app.context.scheduler,
        )
        # No feedback between rounds: a final test does not coach.
        self.next_exam_round()

    def finish_final_test(self) -> None:
        assert self.exam is not None
        context = self.app.context
        verdict = ft.conclude(context.conn, self.master, self.exam, seed=self._seed())

        self.stop_clock()
        self.query_one("#choices", Vertical).remove_children()
        self.query_one("#statement", Static).display = False
        self.say(verdict.master_line)

        panel = self.query_one("#verdict", Static)
        panel.set_class(not verdict.passed, "wrong")
        head = (
            "[b $success]THE MASTER IS SATISFIED.[/]" if verdict.passed else "[b $error]NOT YET.[/]"
        )
        lines = [
            head,
            "",
            f"score [b]{verdict.score}/{verdict.total}[/]   needed {verdict.required}",
            "",
        ]
        for index, outcome in enumerate(self.exam.outcomes, start=1):
            mark = "[$success]✓[/]" if outcome.correct else "[$error]✗[/]"
            note = " [dim](time)[/]" if outcome.timed_out else ""
            lines.append(f"  {mark} {index}. {safe(outcome.problem.title)}{note}")
        lines += ["", f"respect {verdict.respect_delta:+d} → {verdict.respect_total}"]
        if not verdict.passed:
            lines += ["", "[dim]Train, then return. Nothing is lost.[/]"]
        lines += ["", "[dim]escape — leave[/]"]
        panel.update("\n".join(lines))
        panel.display = True

        self.exam = None
        self.refresh_track()
        self.phase = "done"
