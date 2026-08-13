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
from .master import MasterScreen, safe

JOURNEY_CSS = """
#journey-title { padding: 1 2 0 2; text-style: bold; }
#masters { padding: 0 2; height: 1fr; }
.master-card { padding: 1 2; margin: 1 0; border: round $primary; height: auto; }
.master-card.done { border: round $success; }
.master-card.locked { border: round $panel; color: $text-disabled; }
#masters Button { width: 100%; margin: 0 0 1 0; }
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
        #: remove_children() is deferred, so rebuilding reuses ids that still
        #: exist for a frame. Buttons carry a generation, and are addressed by
        #: row index rather than by master id so nothing has to be parsed back.
        self._generation = 0
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

    def refresh_view(self) -> None:
        container = self.query_one("#masters", Vertical)
        container.remove_children()
        context = self.app.context

        self._generation += 1
        for index, master in enumerate(self.masters):
            curriculum = context.curricula[master.id]
            container.mount(Static(self._card(master, curriculum), classes="master-card"))
            container.mount(
                Button(
                    f"{index + 1}.  Train under {master.title}",
                    id=f"mrow-{index}-{self._generation}",
                )
            )

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

        bar = "█" * tested + "▓" * (fluent - tested) + "░" * (total - fluent)
        names = ", ".join(library[p].name for p in master.patterns if p in library)

        if exam.passed:
            status = f"[green]final test passed  {exam.best_score}/{exam.best_total}[/]"
        elif ft.available(conn, curriculum):
            status = "[b yellow]final test available[/]"
        elif tested:
            status = f"[dim]{total - tested} secret(s) left[/]"
        else:
            status = "[dim]not started[/]"

        return (
            f"[b]{safe(master.name)}[/]\n"
            f"[i]{safe(master.title)}[/]\n\n"
            f"  {bar}  {tested}/{total} secrets    respect {respect}\n"
            f"  [dim]{safe(names)}[/]\n"
            f"  {status}"
        )

    # ---------------------------------------------------------------- input

    @on(Button.Pressed)
    def on_button(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("mrow-"):
            self.action_enter(int(event.button.id.split("-")[1]))

    def action_enter(self, index: int) -> None:
        found = self.masters
        if index < len(found):
            context = self.app.context
            self.app.push_screen(MasterScreen(context.masters[found[index].id], context.curricula))
