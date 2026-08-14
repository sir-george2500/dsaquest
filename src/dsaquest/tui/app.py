"""The Textual application.

Two screens carry the MVP: a campaign map and a session runner. The session
runner drives whatever the planner queued, switching between recognition and
code completion without the learner choosing a mode — interleaving is the point,
and asking "which mode?" every time invites picking the comfortable one.

Judging runs on a worker thread. Compiling and executing C++ takes a second or
two, and doing it on the UI thread freezes the terminal mid-keystroke.
"""

from __future__ import annotations

import contextlib
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
from ..game.modes.complete import (
    exercise_source,
    find_hole,
    judge_completion,
    judge_source,
    parse_holes,
)
from ..game.modes.recall import (
    auto_match,
    canonical_answer,
    expected_phrases,
)
from ..game.modes.recall import build_round as build_recall
from ..game.modes.recall import grade as grade_recall
from ..game.session import ExerciseResult, begin_exercise, complete_exercise
from ..judge import workspace
from ..learning.planner import PlannedItem, build_session
from ..storage import repositories as repo
from .arena import ARENA_CSS, ArenaScreen
from .card import (
    BAD,
    BODY,
    BUTTON_CSS,
    EMBER,
    FAINT,
    GOLD,
    GOOD,
    INK,
    MUTE,
    RULE,
    SEALED,
    clip,
    gauge,
    pack,
    printed_width,
    quest_theme,
)
from .codex import CODEX_CSS, CodexScreen
from .duel import DUEL_CSS, DuelScreen
from .editor import code_editor
from .journey import JOURNEY_CSS, JourneyScreen
from .master import MASTER_CSS, MasterScreen, safe
from .roster import ROSTER_CSS, RosterScreen
from .story import STORY_CSS, StoryScreen, load_story
from .theatre import THEATRE_CSS
from .understanding import UNDERSTANDING_CSS

#: The home screen's own measure. Wider than the prose measure because the road
#: is a five-column table and not prose, and narrower than any real terminal so
#: that the layout is the same shape everywhere.
HOME_MEASURE = 104

CSS = (
    """
Screen { background: $surface; }

/* The home screen is one column, capped. Uncapped it stretched to whatever the
   terminal was: at 160 columns the quest box drew a gold rectangle 160 cells
   wide around sixty cells of text, and the road's five columns drifted so far
   apart that a row stopped reading as a row. Capped and left-aligned, the same
   layout holds from eighty columns to a hundred and sixty. */
#home { width: 100%; max-width: """
    + str(HOME_MEASURE)
    + """; height: 1fr; }

/* One left edge. Every block begins at the same column: the banner's text, the
   quest's text, the actions and the road. */
#banner {
    height: auto; padding: 0 2; margin: 1 2 0 2;
    border-left: outer """
    + RULE
    + """;
}
/* The quest box is the loudest thing on the screen on purpose: it is the
   answer to "what do I do now", and everything else is optional. Its heading
   lives in the border rather than on a line of its own — a row saved on a
   twenty-four row terminal is a row of the road made visible. */
#quest {
    height: auto; padding: 0 2; margin: 1 2 0 2; border: round """
    + GOLD
    + """;
    border-title-color: """
    + GOLD
    + """;
    border-title-align: left;
}
#actions { height: auto; padding: 1 2 0 2; }
/* A stable gutter, so the road's column widths do not depend on whether the
   road happens to be scrolling. Without it the same eleven rows fit at 120x40
   and wrapped at 80x24, two columns over, because the scrollbar appeared and
   silently took them. */
#map-wrap { height: 1fr; scrollbar-gutter: stable; }
#map { padding: 1 2 0 2; }

/* Scoped to the session runner. Unscoped, these ids are not unique in the
   application: `#statement` and `#verdict` also exist on the master screen and
   `#editor` inside the arena, so a rule written for a practice round was
   silently styling a boss fight. `max-height: 60%` was the expensive one — it
   applied to the *master's* statement panel, where it clipped a trial's problem
   statement to five rows, bottom border and all, with no scrollbar and no
   indication that seventeen rows of the problem were missing. The player was
   timed on a question they could not read. */
SessionScreen #statement {
    padding: 1 2; border: round $primary; margin: 1 2;
    height: auto; max-height: 60%;
}
SessionScreen #prompt { padding: 0 2; color: $text-muted; }
SessionScreen #options { padding: 0 2; height: auto; }

SessionScreen #feedback {
    padding: 1 2; margin: 1 2; border: round $success; height: auto;
}
SessionScreen #feedback.wrong { border: round $error; }

SessionScreen #editor { height: 1fr; margin: 1 2; border: round $primary; }
SessionScreen #verdict { padding: 1 2; height: auto; }

.dim { color: $text-muted; }
.good { color: $success; text-style: bold; }
.bad { color: $error; text-style: bold; }
"""
    + BUTTON_CSS
    + MASTER_CSS
    + JOURNEY_CSS
    + ARENA_CSS
    + DUEL_CSS
    + UNDERSTANDING_CSS
    + ROSTER_CSS
    + THEATRE_CSS
    + STORY_CSS
    + CODEX_CSS
)


#: A lock emoji is two terminal cells wide and every other mark is one, so a
#: sealed chapter pushed its whole row a column to the right of an open one:
#: eleven rows, two different left edges, alternating. The journey layer is
#: right to hand out a mark; choosing a *monospaced* one is presentation.
MARKS = {"🔒": "×", "→": "▸", "✓": "✓", "·": "·"}


def _mark(mark: str) -> str:
    return MARKS.get(mark, mark)


class HomeScreen(Screen):
    BINDINGS = [
        Binding("enter", "continue_journey", "Continue Journey"),
        Binding("1", "continue_journey", "", show=False),
        Binding("2", "map", "Journey map"),
        Binding("3", "practice", "Training grounds"),
        Binding("4", "review", "Review due"),
        Binding("5", "duel", "Duel"),
        Binding("6", "roster", "Roster"),
        Binding("7", "codex", "Codex"),
        Binding("8", "strength", "Strength", show=False),
        Binding("s", "story", "Story", show=False),
        Binding("p", "practice", "", show=False),
        Binding("r", "review", "", show=False),
        Binding("t", "train", "", show=False),
        Binding("d", "duel", "", show=False),
        Binding("c", "roster", "", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="home"):
            yield Static(id="banner")
            yield Static(id="quest")
            yield Static(id="actions")
            yield VerticalScroll(Static(id="map"), id="map-wrap")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#quest", Static).border_title = "CURRENT QUEST"
        self.refresh_view()

    def on_resize(self, event) -> None:
        """Every block on this screen is sized to the terminal, so redraw.

        The banner's gauge, the road's five column widths and how many optional
        actions fit on a line are all computed from the width available. Without
        this they keep whatever they were built with, and a terminal resized
        from 160 to 80 shows a road whose rows are twenty columns too wide.
        """
        self.refresh_view()

    def on_screen_resume(self) -> None:
        """Redraw whenever the player comes back to it.

        The home screen is mounted once and lives underneath everything else,
        so without this it shows whatever was true when the app started — the
        quest would not advance after a lesson, the road would not fill in
        after a guardian fell, and a warrior who had just named themselves
        would still be greeted as someone else.
        """
        self.refresh_view()

    # ------------------------------------------------------------- the quest

    def action_continue_journey(self) -> None:
        """The one action that always knows what to do.

        Everything else on this screen is optional. This is the road.
        """
        from ..journey import Objective, next_step

        context: AppContext = self.app.context
        step = next_step(context)

        if step.objective is Objective.PROLOGUE:
            story = load_story()
            if story is not None:
                repo.set_flag(context.conn, "prologue_read")
                context.conn.commit()
                self.app.push_screen(StoryScreen(story))
            return

        if step.objective in (
            Objective.MEET_MASTER,
            Objective.TRAIN,
            Objective.TRIAL,
            Objective.FINAL_TEST,
        ):
            master = context.masters.get(step.master_id)
            if master is not None and context.curricula is not None:
                self.app.push_screen(MasterScreen(master, context.curricula))
            return

        if step.objective in (Objective.BOSS, Objective.ELITE_CODER, Objective.GATE_SHUT):
            # A shut gate still opens the arena: the guardian's own refusal,
            # naming what it wants, is a better answer than a message box.
            if context.bosses and step.boss_id in context.bosses:
                self.app.push_screen(ArenaScreen(context.bosses[step.boss_id]))
            return

        self.app.push_screen(RosterScreen())

    def action_map(self) -> None:
        self.app.push_screen(JourneyScreen())

    def action_codex(self) -> None:
        self.app.push_screen(CodexScreen())

    def action_strength(self) -> None:
        self.app.push_screen(RosterScreen())

    def refresh_view(self) -> None:
        context: AppContext = self.app.context
        profile = context.refresh_profile()
        level = progress(profile.xp)
        streak = repo.get_streak(context.conn, "daily")
        plan = build_session(
            context.conn, context.library, context.bank, scheduler=context.scheduler
        )

        from ..journey import boss_for, chapter_statuses, load_chapters, next_step

        story = load_chapters()
        step = next_step(context)
        road = chapter_statuses(context)
        walked = sum(s.fraction for s in road) / len(road) if road else 0.0

        # Everything below is sized off this, not off the terminal: `#home` is
        # capped, so past 104 columns the layout stops growing rather than
        # spreading its columns until a row no longer reads as a row.
        column = min(self.size.width or HOME_MEASURE, HOME_MEASURE)
        self._breathe()

        # Each block loses a different amount to its own border, padding and
        # margin. Measured once against the rendered widgets rather than
        # derived: guessing put the road's header row one column over its
        # container, and "0 of 11 cleared" wrapped to a line of its own.
        self._draw_banner(context, story, level, streak, plan, column - 9)
        self._draw_quest(step, story, walked, column - 10)
        self._draw_actions(step, column - 8)
        self._draw_road(context, story, road, step, boss_for, column - 10)

    #: Under this many rows the screen drops every blank separator. The road is
    #: the point of the screen and at eighty by twenty-four the airy version
    #: showed two of its twelve chapters; the tight one shows eleven.
    TIGHT_HEIGHT = 32

    def _breathe(self) -> None:
        gap = 0 if self.size.height < self.TIGHT_HEIGHT else 1
        self.query_one("#banner").styles.margin = (gap, 2, 0, 2)
        self.query_one("#quest").styles.margin = (gap, 2, 0, 2)
        self.query_one("#actions").styles.padding = (gap, 2, 0, 2)
        # The road keeps its top rule of space whatever happens. Butted straight
        # against the actions it stopped being a separate block and the heading
        # read as a sixth menu item.
        self.query_one("#map").styles.padding = (1, 2, 0, 2)

    def _draw_banner(self, context, story, level, streak, plan, width: int) -> None:
        """Who you are, and where you stand. Two lines, both flush at both ends.

        The identity goes left and the two volatile numbers go hard right, so
        the block has an edge on both sides instead of trailing off wherever the
        streak count happened to end.
        """
        name = safe(repo.warrior_name(context.conn, story.hero or "DELTA-X"))
        due = (
            f"[b {GOLD}]{plan.due_count} due[/]" if plan.due_count else f"[{SEALED}]nothing due[/]"
        )
        left = f"[b {GOLD}]{name}[/]  [{MUTE}]THE ALGORITHM WARRIOR[/]"
        right = f"[{FAINT}]{streak.current} day streak[/]  [{SEALED}]·[/]  {due}"

        standing = f"[{BODY}]Level {level.level}[/]  [{MUTE}]{safe(level.title)}[/]"
        # The gauge takes what the two labels leave. Fixed at twenty-four cells
        # it pushed "nothing due" onto a third line at eighty columns, and the
        # banner — three rows for two rows of content — read as a wrapping bug.
        bar_w = max(8, min(18, width - printed_width(standing) - 20))
        earned = (
            f"{gauge(level.xp_into_level / max(1, level.xp_for_level), bar_w, GOOD)} "
            f"[{FAINT}]{level.xp_into_level:,}/{level.xp_for_level:,} XP[/]"
        )

        # Both rows are flush at both ends. Ragged, the identity ran to the far
        # right and the level line stopped halfway, so the block had one edge
        # and one frayed side.
        self.query_one("#banner", Static).update(
            f"{left}{' ' * max(3, width - printed_width(left) - printed_width(right))}{right}\n"
            f"{standing}{' ' * max(3, width - printed_width(standing) - printed_width(earned))}"
            f"{earned}"
        )

    def _draw_quest(self, step, story, walked: float, width: int) -> None:
        chapter = step.chapter
        where = safe(
            clip(
                f"Chapter {chapter.number} — {chapter.name}" if chapter else story.title, width - 24
            )
        )
        pct = f"{walked:.0%} of the road"
        bar = max(10, min(24, width - len(where) - len(pct) - 4))

        self.query_one("#quest", Static).update(
            f"[b {INK}]{safe(step.title)}[/]\n"
            f"[{BODY}]{safe(step.detail)}[/]\n\n"
            f"[{FAINT}]{where}[/]   {gauge(walked, bar, GOLD)} [{MUTE}]{pct}[/]"
            + (
                f"\n\n[{BAD}]" + safe("  ·  ".join(step.blockers[:4])) + "[/]"
                if step.blockers
                else ""
            )
        )

    def _draw_actions(self, step, width: int) -> None:
        primary = "Continue Journey" if step.is_action else "See what it wants"
        # The primary action sits on its own line, in the quest's own gold, and
        # the five optional ones share the line below it. Six equal keys in a
        # row made the one that matters indistinguishable from the rest.
        rest = [
            f"[{FAINT}]\\[{key}][/] [{MUTE}]{label}[/]"
            for key, label in (
                (2, "Journey map"),
                (3, "Training grounds"),
                (4, "Review due"),
                (5, "Duel"),
                (6, "Roster"),
                (7, "Codex"),
            )
        ]
        self.query_one("#actions", Static).update(
            f"[b {GOLD}]\\[1][/] [b {INK}]{primary}[/]   [{FAINT}](enter)[/]\n"
            + "\n".join(pack(rest, width, gap=4))
        )

    def _draw_road(self, context, story, road, step, boss_for, width: int) -> None:
        """Where Delta-X has been and where he is going.

        Five columns, all sized from the width available, because a table whose
        columns are fixed either overflows a narrow terminal — at a hundred
        columns every one of the eleven rows wrapped, and the road became
        twenty-two ragged half-lines — or drifts apart on a wide one.

        The status word is gone and a per-chapter gauge stands in its place.
        Ten rows reading "sealed" in the same grey is ten rows of nothing; the
        gauge says the same thing about a sealed chapter (empty) and something
        no word said about an open one (how far in).
        """
        # 1 mark + 1 + 4 number + 1 + name + 1 + master + 1 + 8 gauge + 1 + guardian
        spare = max(36, width - 18)
        # Seventy columns will not hold four text columns. Rather than clip all
        # three — "Adjudicator Sevr…" beside "The Halving" beside "THE SEARCH
        # WARDEN" wrapping onto a second line — the guardian is dropped at
        # narrow widths. It is the one column the chapter's own name already
        # implies: chapter III, The Halving, is guarded by The Search Warden.
        wide = spare >= 64
        if wide:
            name_w = max(14, min(28, spare * 36 // 100))
            master_w = max(12, min(30, spare * 33 // 100))
            guard_w = spare - name_w - master_w
        else:
            name_w = max(14, spare * 45 // 100)
            master_w = spare - name_w
            guard_w = 0

        here = step.chapter.number if step.chapter else None
        cleared = sum(1 for s in road if s.complete)
        count = f"{cleared} of {len(road)} cleared"
        lines = [f"[{FAINT}]THE ROAD[/]{' ' * max(2, width - 8 - len(count))}[{SEALED}]{count}[/]"]
        if self.size.height >= self.TIGHT_HEIGHT:
            lines.append("")

        for status in road:
            chapter = status.chapter
            master = context.masters.get(chapter.master)
            # The name, never the epithet. Nine of eleven epithets *are* the
            # chapter's own name — "Warden Ilsa Korrin, the Straight Line"
            # against a chapter called The Straight Line — and keeping whichever
            # ones happened to fit gave a column where two rows out of eleven
            # ran long for no reason a reader could see.
            who = (master.title if master else chapter.master).split(",")[0]

            current = chapter.number == here
            if status.complete:
                style = GOOD
            elif current:
                style = GOLD
            elif status.started:
                style = BODY
            else:
                style = MUTE if status.reachable else SEALED
            mark = "▸" if current else _mark(status.mark)

            boss = boss_for(context, chapter)
            guardian = safe(clip(boss.name, guard_w)) if (boss and guard_w) else ""
            # A guardian you cannot reach must not out-shout the chapter that
            # names it: "Grandmaster Ragine" sat in dead grey while THE
            # THIRTY-TWO burned warm brown two columns away.
            if status.boss_defeated:
                colour = GOOD
            elif status.reachable:
                colour = EMBER
            else:
                colour = SEALED

            teacher = FAINT if status.reachable else SEALED
            # A sealed chapter gets no track at all. Drawn for every row the
            # eight-cell gauges stacked into a solid grey column that was the
            # second loudest shape on a fresh save while saying nothing; drawn
            # only where the road is walkable, the one lit track is exactly
            # where the player is.
            bar = (
                gauge(status.fraction, 8, GOOD if status.complete else GOLD)
                if status.reachable
                else " " * 8
            )
            lines.append(
                f"[{style}]{mark} {chapter.number:<4} "
                f"{safe(clip(chapter.name, name_w)):<{name_w}}[/] "
                f"[{teacher}]{safe(clip(who, master_w)):<{master_w}}[/] "
                f"{bar} [{colour}]{guardian}[/]"
            )

        if story.final is not None:
            felled = story.final.boss in repo.bosses_defeated(context.conn)
            style = GOOD if felled else SEALED
            lines += [
                "",
                f"[{style}]{'✓' if felled else '·'} {story.final.number:<4} "
                f"{safe(clip(story.final.name, name_w)):<{name_w}}[/] "
                f"[{SEALED}]{'THE ELITE CODER' if not guard_w else '':<{master_w}}[/] "
                f"{gauge(1.0, 8, GOOD) if felled else ' ' * 8} "
                f"[{GOOD if felled else SEALED}]{'THE ELITE CODER' if guard_w else ''}[/]",
            ]

        self.query_one("#map", Static).update("\n".join(lines))

    def action_practice(self) -> None:
        self.app.push_screen(SessionScreen(review_only=False))

    def action_duel(self) -> None:
        self.app.push_screen(DuelScreen())

    def action_roster(self) -> None:
        self.app.push_screen(RosterScreen())

    def action_story(self) -> None:
        story = load_story()
        if story is not None:
            self.app.push_screen(StoryScreen(story))

    def action_review(self) -> None:
        self.app.push_screen(SessionScreen(review_only=True))

    def action_train(self) -> None:
        """Open the journey map so the student chooses their master."""
        context = self.app.context
        teaching = [
            m for m in context.masters.values() if context.curricula and m.id in context.curricula
        ]
        if not teaching:
            self.notify("No masters are teaching yet.", severity="warning")
            return
        if len(teaching) == 1:
            # One master is not a choice; skip the menu.
            self.app.push_screen(MasterScreen(teaching[0], context.curricula))
        else:
            self.app.push_screen(JourneyScreen())


class SessionScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("1", "pick(0)", "A", show=False),
        Binding("2", "pick(1)", "B", show=False),
        Binding("3", "pick(2)", "C", show=False),
        Binding("4", "pick(3)", "D", show=False),
        Binding("ctrl+s", "submit_code", "Submit", show=False),
        Binding("e", "edit_externally", "Edit in $EDITOR", show=False),
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
        self.workspace = None
        self.edited_source: str | None = None

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
        elif item.mode is GameMode.RECALL:
            self.present_recall(item)
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
            f"[b]{safe(round_.problem.title)}[/]\n\n{safe(round_.problem.statement.strip())}\n\n"
            f"[dim]{safe(round_.problem.constraints.strip())}[/]\n\n"
            f"[b]Which pattern should you use?[/]"
        )
        options = self.query_one("#options", Vertical)
        for position, (label, option) in enumerate(round_.labelled()):
            options.mount(Button(f"{label}.  {safe(option.name)}", id=f"opt{position}"))

    def present_recall(self, item: PlannedItem) -> None:
        """Mode B: the pattern is named, and everything else must come from memory."""
        context: AppContext = self.app.context
        pattern = context.library[item.pattern_id]
        round_ = build_recall(pattern)
        seed = int(datetime.now(UTC).timestamp() * 1000) % 2**31

        self.current = round_
        self.attempt_id = begin_exercise(
            context.conn,
            pattern_id=item.pattern_id,
            mode=GameMode.RECALL,
            seed=seed,
            difficulty=item.difficulty,
        )
        self.started_at = datetime.now(UTC)

        self.query_one("#prompt", Static).update(
            f"[dim]{self.index + 1}/{len(self.queue)}  ·  {item.reason}  ·  recall[/]\n"
            f"[b]{safe(pattern.name)}[/]   [dim](ctrl+s when you have written it)[/]"
        )
        self.query_one("#statement", Static).update(
            "From memory:\n\n"
            "  · what signals in a statement reveal it\n"
            "  · the invariant that makes it correct\n"
            "  · its time and space complexity\n"
            "  · what usually goes wrong\n\n"
            "[dim]Nothing is checked until you commit.[/]"
        )
        editor = code_editor("", id="editor", show_line_numbers=False)
        self.query_one("#options", Vertical).mount(editor)
        self.set_timer(0.1, editor.focus)

    def submit_recall(self) -> None:
        from ..game.modes.recall import RecallRound

        if not isinstance(self.current, RecallRound):
            return
        try:
            written = self.query_one("#editor", TextArea).text
        except Exception:
            return

        context: AppContext = self.app.context
        item = self.queue[self.index]
        outcome = grade_recall(self.current, written, auto_match(self.current, written))
        elapsed = int((datetime.now(UTC) - self.started_at).total_seconds() * 1000)

        recorded = complete_exercise(
            context.conn,
            self.attempt_id,
            ExerciseResult(
                correct=outcome.correct,
                duration_ms=elapsed,
                self_grade=outcome.self_grade,
                essential_missed=outcome.essential_missed,
            ),
            library=context.library,
            scheduler=context.scheduler,
            pattern_id=item.pattern_id,
            mode=GameMode.RECALL,
            difficulty=item.difficulty,
        )
        self.record(recorded, outcome.correct)

        body = []
        if outcome.correct:
            body.append(f"[b $success]Held.[/]  {outcome.credited}/{outcome.total} points")
        else:
            body.append(
                f"[b $error]Not held.[/]  {outcome.credited}/{outcome.total} points — "
                f"an essential one is missing"
            )
        body.append("")
        for result in outcome.results:
            mark = "[$success]+[/]" if result.credited else "[$error]-[/]"
            star = "[b]*[/]" if result.point.essential else " "
            body.append(f"  {mark}{star} {safe(result.point.prompt)}")
            if not result.credited and result.point.essential:
                phrases = expected_phrases(result.point)
                if phrases:
                    body.append(f"      [dim]looked for {safe(phrases)}[/]")

        body += ["", "[b]What the master would have said[/]", ""]
        body.append(
            f"[dim]{safe(canonical_answer(self.current.pattern, library=context.library))}[/]"
        )
        body.append(f"\n[dim]{recorded.xp.explain()}[/]")

        self.show_feedback("\n".join(body), correct=outcome.correct)

    def present_completion(self, item: PlannedItem) -> None:
        context: AppContext = self.app.context
        pattern = context.library[item.pattern_id]
        source = read_template(pattern.template_file)
        holes = parse_holes(source)
        seed = int(datetime.now(UTC).timestamp() * 1000) % 2**31
        hole = holes[seed % len(holes)]

        self.current = (pattern.template_file, hole.id)
        self.workspace = None
        self.edited_source = None
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
            f"{pattern.name}[/]\n[b]TODO: {safe(hole.prompt)}[/]   "
            f"[dim](ctrl+s submit · e edit in $EDITOR)[/]"
        )
        self.query_one("#statement", Static).update(
            f"[dim]{safe(exercise_source(source, hole.id))}[/]"
        )
        editor = code_editor("", id="editor")
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
            body.append(
                f"[b $success]Correct.[/] {context.library[feedback.actual_pattern_id].name}"
            )
        else:
            body.append(
                f"[b $error]No.[/] That was "
                f"[b]{context.library[feedback.actual_pattern_id].name}[/], "
                f"not {context.library[feedback.chosen_pattern_id].name}."
            )
            if feedback.has_tell:
                body.append(f"\n[b]How to tell:[/]\n{safe(feedback.tell)}")
        body.append(f"\n[b]Why:[/]\n{safe(feedback.why.strip())}")
        if feedback.signals:
            body.append("\n[b]Cues present:[/] " + ", ".join(safe(s) for s in feedback.signals))
        if feedback.classic_ref:
            body.append(f"\n[dim]Drills: {feedback.classic_ref}[/]")
        body.append(f"\n[dim]{outcome.xp.explain()}[/]")

        self.show_feedback("\n".join(body), correct=feedback.correct)

    def action_edit_externally(self) -> None:
        """Hand the whole exercise file to $EDITOR.

        The point of leaving the app is that you practise in the environment you
        compete in — your keybinds, your snippets, your clangd. The generated
        compile_commands.json uses the judge's own flags, so what the editor
        tells you and what the judge does cannot disagree.
        """
        if self.awaiting_advance or not isinstance(self.current, tuple):
            return

        template_file, hole_id = self.current
        source = read_template(template_file)
        hole = find_hole(source, hole_id)

        try:
            self.workspace = workspace.create(
                attempt_id=self.attempt_id or 0,
                starter=exercise_source(source, hole_id),
                statement=(
                    f"# {template_file}\n\n"
                    f"Fill in the TODO.\n\n"
                    f"    {hole.prompt}\n\n"
                    f"About {hole.line_count} line(s). Save and quit to submit.\n"
                ),
            )
        except Exception as exc:  # pragma: no cover - environment dependent
            self.notify(f"Could not prepare a workspace: {exc}", severity="error")
            return

        with self.app.suspend():
            try:
                workspace.open_in_editor(self.workspace)
            except Exception as exc:  # pragma: no cover - no editor installed
                self.app.notify(f"Editor failed: {exc}", severity="error")
                return

        self.edited_source = self.workspace.read_source()
        # Mirror it into the inline editor when one is mounted, so the two
        # views never disagree about what is about to be submitted.
        with contextlib.suppress(Exception):
            self.query_one("#editor", TextArea).text = self.edited_source
        self.query_one("#prompt", Static).update(
            "[$success]Edited externally.[/]  [dim]ctrl+s to submit, e to go back[/]"
        )

    def action_submit_code(self) -> None:
        if self.awaiting_advance:
            return
        from ..game.modes.recall import RecallRound

        if isinstance(self.current, RecallRound):
            self.submit_recall()
            return
        if not isinstance(self.current, tuple):
            return
        if self.edited_source is not None:
            self.query_one("#prompt", Static).update("[$warning]Compiling and running…[/]")
            self.judge_whole(self.edited_source)
            return
        try:
            editor = self.query_one("#editor", TextArea)
        except Exception:
            return
        self.query_one("#prompt", Static).update("[$warning]Compiling and running…[/]")
        self.judge_code(editor.text)

    @work(thread=True)
    def judge_whole(self, candidate: str) -> None:
        template_file, _ = self.current  # type: ignore[misc]
        report = judge_source(
            read_template(template_file), candidate, list(samples_for(template_file))
        )
        self.app.call_from_thread(self.finish_code, report, candidate)

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
            body = [f"[b $success]Accepted.[/] {report.report.passed}/{report.report.total} tests"]
        else:
            failure = report.report.first_failure
            body = [f"[b $error]{report.report.verdict.label}[/]"]
            # The compiler's own words, and the judge's, go through safe():
            # an error about `undefined_thing[q]` was being shown as an error
            # about `undefined_thing`, which sends the learner hunting for a
            # symbol that is not what the compiler complained about.
            if report.report.compile_log.strip():
                body.append(f"\n{safe(report.report.compile_log.strip()[:800])}")
            elif failure is not None:
                body.append(f"\n{safe(failure.name)}: {safe(failure.diff_hint)}")
            template_file, hole_id = self.current  # type: ignore[misc]
            hole = find_hole(read_template(template_file), hole_id)
            body.append(f"\n[dim]Reference answer:[/]\n{safe(hole.body)}")
        body.append(f"\n[dim]{outcome.xp.explain()}[/]")
        self.show_feedback("\n".join(body), correct=accepted)

    # ------------------------------------------------------------- helpers

    def record(self, outcome, correct: bool) -> None:
        self.xp_earned += outcome.xp.total
        self.correct_count += int(correct)
        extras = []
        for pattern_id in outcome.newly_unlocked:
            extras.append(f"[b $secondary]Unlocked: {pattern_id}[/]")
        for achievement in outcome.achievements:
            extras.append(f"[b $warning]Achievement: {achievement.name}[/]")
        for level in outcome.levels_gained:
            extras.append(f"[b $secondary]Level {level}![/]")
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
        self.register_theme(quest_theme())
        self.theme = "quest"
        self.push_screen(HomeScreen())
        if self.pending_screen is not None:
            self.push_screen(self.pending_screen)
        elif self.review_only:
            self.push_screen(SessionScreen(review_only=True))
        elif self.auto_story and self.first_run():
            # A profile with nothing recorded has never been played. Read the
            # premise once, unasked; afterwards it is on `s` for anyone who
            # comes back after a month and wants reminding what this is.
            story = load_story()
            if story is not None:
                self.push_screen(StoryScreen(story))

    #: Whether a never-played profile is shown the prologue unasked. True for
    #: real players. The test suite turns it off in conftest, because every
    #: test builds a fresh database and would otherwise land on the prologue
    #: instead of the screen it came to exercise — the tests that are ABOUT the
    #: prologue turn it back on for themselves.
    auto_story = True

    def first_run(self) -> bool:
        """True when this profile has never answered anything."""
        try:
            row = self.context.conn.execute("SELECT COUNT(*) FROM attempt").fetchone()
        except Exception:
            return False
        return bool(row) and row[0] == 0
