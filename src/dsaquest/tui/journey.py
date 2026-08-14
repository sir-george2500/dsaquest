"""The journey map — who is teaching, and how far you have got with each.

The player must always know where they are, what they have mastered, what
remains, and what the next challenge is. That is the whole job of this screen.

It shows progress as the masters see it — secrets taught, drilled, tested, and
whether the final test has been passed — rather than as an abstract percentage.
"Two secrets left with Ilsa Korrin" is a thing you can act on; "Arrays 61%" is
not.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from ..domain.lesson import Curriculum
from ..lessons import final_test as ft
from ..storage import repositories as repo
from ..world.character import Master
from .arena import ArenaScreen
from .card import (
    BACK,
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
    clip,
    gauge,
)
from .master import MasterScreen, safe

JOURNEY_CSS = f"""
JourneyScreen {{ background: {BACK}; }}
#journey-title {{ padding: 1 2 0 2; text-style: bold; }}
#masters {{ padding: 0 2; height: 1fr; }}
/* Four states, and only one of them is gold. Every card used to be gold, so
   eleven identical gold rectangles ran down the screen and the colour that
   means "this is the one to do" meant nothing at all. The default is the same
   quiet frame every other panel in the game uses; gold is spent on the master
   the player has reached, green on a finished one, and a locked one is
   barely there. */
.master-card {{
    padding: 1 2; margin: 1 0; border: round {FRAME}; height: auto;
    max-width: {MEASURE + 6};
}}
.master-card.here {{ border: round {GOLD}; }}
.master-card.done {{ border: round {GOOD}; }}
.master-card.locked {{ border: round {RULE}; color: {SEALED}; }}
#masters Button {{ margin: 0 0 1 0; }}
"""


class JourneyScreen(Screen):
    """Pick a master to train under."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("1", "enter(0)", "", show=False),
        Binding("2", "enter(1)", "", show=False),
        Binding("3", "enter(2)", "", show=False),
        Binding("4", "enter(3)", "", show=False),
        Binding("5", "enter(4)", "", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        #: (master, card, train button, [(boss, button)]) per row, mounted once.
        #: Nothing carries a generation any more: the ids that made one
        #: necessary were the ones handed out afresh on every rebuild, and there
        #: are no rebuilds.
        self._rows: list[tuple[Master, Static, Button, list[tuple[object, Button]]]] = []
        self._mounted = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("THE PATH OF THE WARRIOR", id="journey-title")
        yield VerticalScroll(Vertical(id="masters"))
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Journey"
        self._mounted = True
        self.refresh_view()

    def on_screen_resume(self) -> None:
        """Returning from a master must show what just changed.

        Skipped on the first activation, which arrives immediately after
        on_mount and would otherwise rebuild the list twice.
        """
        if self._mounted:
            self.refresh_view()

    @property
    def masters(self) -> list[Master]:
        """Masters with a curriculum, in campaign order.

        A character with no curriculum has nothing to teach yet, so listing them
        would offer a door that opens onto nothing.
        """
        context = self.app.context
        found = [
            master
            for master in context.masters.values()
            if context.curricula and master.id in context.curricula
        ]
        return sorted(found, key=lambda m: self._campaign_position(m))

    def _campaign_position(self, master: Master) -> tuple[int, int, str]:
        """Order by the earliest world the master's patterns live in."""
        library = self.app.context.library
        slots = [(library[p].world, library[p].order) for p in master.patterns if p in library]
        world, order = min(slots) if slots else (99, 99)
        return world, order, master.id

    def build_rows(self) -> None:
        """Mount the list once. Which masters exist never changes at runtime.

        This screen used to tear its whole list down and mount it again on every
        refresh — and it refreshes on every ``on_screen_resume``, which is every
        time the player comes back from a master. Measured at 120x40: the data
        the screen reads costs 5 ms and the mount/unmount of thirty-five widgets
        cost the other 75, so returning to the map froze for about a tenth of a
        second, every time. The rows are now built once and their contents
        updated in place: the same rebuild is 18.9 ms, measured the same way.
        """
        container = self.query_one("#masters", Vertical)
        context = self.app.context
        self._rows = []
        for index, master in enumerate(self.masters):
            card = Static(classes="master-card")
            train = Button(id=f"mrow-{index}")
            bosses = [(boss, Button(id=f"boss-{boss.id}")) for boss in context.bosses_of(master.id)]
            container.mount(card, train, *(button for _, button in bosses))
            self._rows.append((master, card, train, bosses))

    def refresh_view(self) -> None:
        if not self._rows:
            self.build_rows()
        context = self.app.context
        conn = context.conn

        # Exactly one card is gold: the first master whose final test is still
        # outstanding, which is where the player is on the path. Every card used
        # to be gold — eleven identical gold rectangles, and a colour that means
        # "do this one" spent eleven times means nothing — and quieting them all
        # left a screen with no focal point at all.
        passed = [repo.get_master_progress(conn, m.id).passed for m, *_ in self._rows]
        here = next((i for i, done in enumerate(passed) if not done), None)

        for index, (master, card, train, bosses) in enumerate(self._rows):
            card.update(self._card(master, context.curricula[master.id]))
            card.set_class(passed[index], "done")
            card.set_class(index == here, "here")
            train.label = f"{index + 1}.  Train under {master.title}"
            for boss, button in bosses:
                record = repo.get_boss_record(conn, boss.id)
                mark = "defeated" if record.defeated else "waiting"
                grade = f" · {record.best_grade}" if record.best_grade else ""
                button.label = f"     ⚔  {boss.name}  [{mark}{grade}]"

    def _card(self, master: Master, curriculum: Curriculum) -> str:
        conn = self.app.context.conn
        library = self.app.context.library

        total = len(curriculum.stages)
        fluent = tested = 0
        for stage in curriculum.ordered_stages:
            progress = repo.ensure_secret(conn, master.id, stage.secret.id)
            if progress.state == "tested":
                tested += 1
            if progress.is_fluent:
                fluent += 1

        respect = repo.get_respect(conn, master.id)
        exam = repo.get_master_progress(conn, master.id)

        # `gauge` — the game's one bar. This was the third bar style in the
        # codebase: `▁` for the unlit track, which at nought secrets rendered as
        # a bare underline six columns long and read as a rule, not a gauge.
        bar = gauge(tested / total if total else 0.0, 12, GOLD)
        names = ", ".join(library[p].name for p in master.patterns if p in library)

        if exam.passed:
            status = f"[{GOOD}]final test passed  {exam.best_score}/{exam.best_total}[/]"
        elif ft.available(conn, curriculum):
            status = f"[b {GOLD}]final test available[/]"
        elif tested:
            status = f"[{FAINT}]{total - tested} secret(s) left[/]"
        else:
            status = f"[{SEALED}]not started[/]"

        # The status sits on the gauge's own line rather than orphaned three
        # rows below the patterns it has nothing to do with.
        return (
            f"[b {INK}]{safe(master.name)}[/]\n"
            f"[i {MUTE}]{safe(master.title)}[/]\n\n"
            f"{bar}  [{BODY}]{tested}/{total} secrets[/]   "
            f"[{FAINT}]respect[/] [{MUTE}]{respect}[/]   {status}\n"
            f"[{FAINT}]{safe(clip(names, MEASURE - 2))}[/]"
        )

    # ---------------------------------------------------------------- input

    @on(Button.Pressed)
    def on_button(self, event: Button.Pressed) -> None:
        if not event.button.id:
            return
        if event.button.id.startswith("mrow-"):
            self.action_enter(int(event.button.id.removeprefix("mrow-")))
        elif event.button.id.startswith("boss-"):
            # The boss id is the whole remainder — it contains dashes of its
            # own, and there is no longer a generation suffix to strip.
            boss_id = event.button.id.removeprefix("boss-")
            self.app.push_screen(ArenaScreen(self.app.context.bosses[boss_id]))

    def action_enter(self, index: int) -> None:
        found = self.masters
        if index < len(found):
            context = self.app.context
            self.app.push_screen(MasterScreen(context.masters[found[index].id], context.curricula))
