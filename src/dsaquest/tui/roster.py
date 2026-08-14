"""The roster — every master and every warden, as cards.

Adapters turn a ``Boss`` or a ``Master`` into a :class:`CardData`. They read the
save file, so the card shows the player their own record: how many times they
have fought a boss, which grade stands, how many of a master's secrets they
hold. Nothing on a card is invented for the look of it.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..content.paths import content_root
from ..domain.boss import Boss
from ..storage import repositories as repo
from ..world.character import Master, strip_placeholders
from .card import BACK, CARD_CSS, INK, MUTE, ROMAN, CardData, Stat, WardenCard

ROSTER_CSS = (
    CARD_CSS
    + f"""
RosterScreen {{ background: {BACK}; }}
#roster-title {{ padding: 1 2 0 2; text-style: bold; }}
#roster-sub {{ padding: 0 2 1 2; color: {MUTE}; }}
#roster-body {{ padding: 0 1; }}
/* Centred, not left-hugged. A card is capped at 104 columns so its quote line
   stays readable; at 160 that left fifty-six columns of empty terminal on the
   right alone and the roster looked like it had failed to lay out. */
.roster-row {{ layout: horizontal; height: auto; align-horizontal: center; }}
"""
)

#: A card needs 80 columns for the rank line to survive letterspacing, which
#: is what gives it the small-caps look. Two of those plus margins is 168;
#: under that the roster stacks and the single card takes the extra room.
CARD_WIDTH = 80
TWO_COLUMN_WIDTH = CARD_WIDTH * 2 + 8
MAX_SINGLE_WIDTH = 104

#: The narrowest a card may be drawn. Below this the meta column beside the
#: 28-cell portrait frame is under twenty cells and a name is all ellipsis.
MIN_CARD_WIDTH = 60

ORDINALS = {1: "FIRST", 2: "SECOND", 3: "THIRD", 4: "FOURTH", 5: "FIFTH", 6: "SIXTH"}

#: Dialogue pools worth quoting on a card, best first. Falls back to any pool
#: rather than raising: a card is not worth crashing a screen over.
QUOTE_POOLS = ("intro", "greeting", "first_meeting", "gate_locked", "victory")


def sprites_dir() -> Path:
    return content_root().parent / "assets" / "sprites"


def sprite_for(identifier: str) -> Path:
    return sprites_dir() / f"{identifier.replace('_', '-')}.px"


def _first_line(pools: dict[str, tuple[str, ...]], preferred: tuple[str, ...]) -> str:
    """A line worth quoting: characterful, and whole.

    Lines with placeholders are skipped rather than stripped. Stripping
    ``{requirement}`` out of "Not yet. {requirement} is short by {shortfall}
    percent." leaves "Not yet. is short by percent." — a broken sentence in a
    character's mouth is worse than quoting them on something else. Stripping
    stays as the last resort, for a character whose every line is templated.
    """
    ordered = [name for name in preferred if name in pools]
    ordered += [name for name in pools if name not in preferred]

    for name in ordered:
        for line in pools.get(name, ()):
            if "{" not in line:
                return line
    for name in ordered:
        for line in pools.get(name, ()):
            return strip_placeholders(line)
    return ""


def boss_card(conn, boss: Boss, library, *, gate_open: bool) -> CardData:
    record = repo.get_boss_record(conn, boss.id)

    if record.defeated:
        state = "FELLED"
    elif gate_open:
        state = "UNBOUND"
    else:
        state = "SEALED"

    stats = [
        Stat("HP", str(boss.boss_hp)),
        Stat("TIER", ROMAN.get(int(boss.tier), str(int(boss.tier)))),
        Stat("PHASES", str(len(boss.phases))),
    ]
    if record.attempts:
        stats.append(
            Stat("BEST", record.best_grade.upper() if record.best_grade else "—", accented=True)
        )
    else:
        stats.append(Stat("FOUGHT", "never"))

    return CardData(
        identifier=boss.id,
        sprite=sprite_for(boss.id),
        rank=f"{ORDINALS.get(int(boss.tier), 'WARDEN')} WARDEN · {state}",
        name=boss.name,
        domain=" · ".join(library[p].name for p in boss.patterns),
        blurb=boss.title,
        stats=tuple(stats),
        quote=_first_line(boss.dialogue, QUOTE_POOLS),
    )


def master_card(conn, master: Master, curriculum) -> CardData:
    respect = repo.get_respect(conn, master.id)
    progress = repo.get_master_progress(conn, master.id)

    held = 0
    total = 0
    if curriculum is not None:
        total = len(curriculum.stages)
        states = {p.secret_id: p.state for p in repo.all_secret_progress(conn, master.id)}
        held = sum(1 for stage in curriculum.stages if states.get(stage.secret.id) == "tested")

    stats = (
        Stat("SECRETS", f"{held}/{total}" if total else "—"),
        Stat("RESPECT", str(respect), accented=respect > 0),
        Stat("PATTERNS", str(len(master.patterns))),
        Stat(
            "FINAL",
            "passed" if progress.passed else ("failed" if progress.attempts else "untaken"),
            accented=progress.passed,
        ),
    )

    return CardData(
        identifier=master.id,
        sprite=sprite_for(master.id),
        rank=master.region.replace("-", " ").replace("_", " ").upper(),
        name=master.title,
        domain=master.name,
        blurb=" · ".join(master.patterns),
        stats=stats,
        quote=_first_line(master.dialogue, QUOTE_POOLS),
    )


class RosterScreen(Screen):
    """Every character in the game, as a wall of cards."""

    BINDINGS = [
        Binding("escape", "leave", "Back"),
        Binding("m", "show('masters')", "Masters"),
        Binding("w", "show('wardens')", "Wardens"),
        Binding("a", "show('all')", "All"),
    ]

    def __init__(self, which: str = "all") -> None:
        super().__init__()
        self.which = which
        self._generation = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="roster-title")
        yield Static(id="roster-sub")
        yield VerticalScroll(id="roster-body")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "THE ROSTER"
        self.refresh_view()

    def action_show(self, which: str) -> None:
        self.which = which
        self.refresh_view()

    def cards(self) -> list[CardData]:
        context = self.app.context
        conn = context.conn
        out: list[CardData] = []

        if self.which in ("all", "masters"):
            for master in context.masters.values():
                curriculum = None
                if context.curricula is not None:
                    try:
                        curriculum = context.curricula[master.id]
                    except (KeyError, LookupError):
                        curriculum = None
                out.append(master_card(conn, master, curriculum))

        if self.which in ("all", "wardens"):
            from ..boss import gate_status
            from ..learning.mastery import all_mastery

            mastery = all_mastery(conn, context.library, scheduler=context.scheduler)
            for boss in context.bosses or ():
                status = gate_status(conn, boss, mastery, context.masters)
                out.append(boss_card(conn, boss, context.library, gate_open=status.open))

        return out

    def refresh_view(self) -> None:
        cards = self.cards()
        self._generation += 1

        self.query_one("#roster-title", Static).update(f"[b {INK}]THE ROSTER[/]")
        self.query_one("#roster-sub", Static).update(
            f"[{MUTE}]{len(cards)} of them   ·   m masters   w wardens   a all[/]"
        )

        body = self.query_one("#roster-body", VerticalScroll)
        body.remove_children()

        if self.size.width >= TWO_COLUMN_WIDTH:
            per_row, width = 2, CARD_WIDTH
        else:
            per_row = 1
            # The floor is what the card can *survive*, not what it prefers.
            # Held at eighty it overflowed an eighty column terminal by six
            # cells: the right border fell off the screen and the blurb was cut
            # mid-word with no ellipsis, because the widget was told it was
            # eighty wide and given seventy-four. Letterspacing already falls
            # back to plain text when it will not fit, so a narrow card degrades
            # rather than breaks.
            width = max(MIN_CARD_WIDTH, min(self.size.width - 6, MAX_SINGLE_WIDTH))

        for index in range(0, len(cards), per_row):
            row = Horizontal(classes="roster-row")
            body.mount(row)
            for data in cards[index : index + per_row]:
                row.mount(WardenCard(data, width=width))

    def action_leave(self) -> None:
        self.app.pop_screen()
