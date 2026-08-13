"""Rich renderers for the non-interactive commands.

Kept free of any Textual import so ``dsa stats`` starts in well under a second.
"""

from __future__ import annotations

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..content.loader import PatternLibrary
from ..domain.pattern import Pattern
from ..game.levels import LevelProgress
from ..learning.mastery import PatternMastery

console = Console()

_BAR_FILLED = "█"
_BAR_EMPTY = "░"


def _colour(fraction: float) -> str:
    if fraction >= 0.75:
        return "green"
    if fraction >= 0.45:
        return "yellow"
    if fraction > 0.0:
        return "red"
    return "bright_black"


def bar(fraction: float, width: int = 18) -> Text:
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    return Text(_BAR_FILLED * filled + _BAR_EMPTY * (width - filled), style=_colour(fraction))


def header(level: LevelProgress, streak: int, due: int) -> Panel:
    line = Text()
    line.append(f"Level {level.level}  ", style="bold cyan")
    line.append(f"{level.title}\n", style="cyan")
    line.append(bar(level.fraction, 28))
    if level.is_max:
        line.append(f"  {level.xp_total:,} XP  (max level)", style="bright_black")
    else:
        line.append(f"  {level.xp_into_level:,} / {level.xp_for_level:,} XP", style="bright_black")
    line.append("\n")
    line.append(f"{streak} day streak", style="bold yellow" if streak else "bright_black")
    line.append("   ")
    line.append(
        f"{due} due for review" if due else "nothing due",
        style="bold green" if due else "bright_black",
    )
    return Panel(line, title="DSA QUEST", border_style="cyan", expand=False)


def mastery_table(
    library: PatternLibrary,
    mastery: dict[str, PatternMastery],
    unlocked: set[str],
) -> Table:
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    # Width 3: the lock glyph is double-width and truncates to an ellipsis in 2.
    table.add_column("", width=3)
    table.add_column("Pattern", style="bold", width=30, overflow="ellipsis", no_wrap=True)
    table.add_column("Mastery", width=20)
    table.add_column("", width=6, justify="right")
    table.add_column("Rec", width=5, justify="right")
    table.add_column("Recall", width=6, justify="right")
    table.add_column("Impl", width=5, justify="right")
    table.add_column("Notes", style="bright_black")

    current_world = None
    for pattern in library:
        if pattern.world != current_world:
            current_world = pattern.world
            table.add_row("", Text(f"World {current_world}", style="bold magenta"), "", "")

        record = mastery[pattern.id]
        playable = pattern.id in unlocked or not pattern.prerequisites

        if not playable:
            marker, style = "🔒", "bright_black"
        elif record.overall >= 0.65:
            marker, style = "✓", "green"
        elif record.started:
            marker, style = "★", "yellow"
        else:
            marker, style = " ", "white"

        notes = []
        if record.gated:
            notes.append("needs implementation reps")
        if not playable:
            missing = [p for p in pattern.prerequisites if p not in unlocked]
            notes.append("locked: " + ", ".join(missing))

        table.add_row(
            Text(marker, style=style),
            Text(pattern.name, style=style),
            bar(record.overall),
            f"{record.overall:.0%}",
            _pct(record.recognition.score),
            _pct(record.recall.score),
            _pct(record.implementation.score),
            "; ".join(notes),
        )
    return table


def _pct(value: float) -> str:
    return "—" if value <= 0 else f"{value:.0%}"


def pattern_detail(pattern: Pattern, library: PatternLibrary) -> Group:
    blocks: list = []

    head = Text()
    head.append(f"{pattern.name}\n", style="bold cyan")
    head.append(pattern.tagline.strip(), style="italic")
    blocks.append(Panel(head, border_style="cyan", expand=False))

    signals = Table(box=None, show_header=False, pad_edge=False)
    signals.add_column(width=3)
    signals.add_column()
    for signal in sorted(pattern.signals, key=lambda s: -s.strength):
        star = "★" * signal.strength
        text = Text(signal.cue, style="bold" if signal.strength == 3 else "")
        if signal.note:
            text.append(f"\n  {signal.note.strip()}", style="bright_black")
        signals.add_row(Text(star, style="yellow"), text)
    blocks.append(Panel(signals, title="Signals", border_style="green", expand=False))

    if pattern.anti_signals:
        anti = Table(box=None, show_header=False, pad_edge=False)
        anti.add_column()
        for item in pattern.anti_signals:
            text = Text()
            text.append(item.cue, style="bold")
            text.append(f"  →  {item.instead}", style="magenta")
            if item.note:
                text.append(f"\n  {item.note.strip()}", style="bright_black")
            anti.add_row(text)
        blocks.append(Panel(anti, title="Rules this out", border_style="red", expand=False))

    if pattern.confusable_with:
        confusions = Table(box=None, show_header=False, pad_edge=False)
        confusions.add_column()
        for confusion in pattern.confusable_with:
            text = Text()
            text.append(f"vs {library[confusion.pattern_id].name}\n", style="bold magenta")
            text.append(confusion.tell.strip(), style="")
            confusions.add_row(text)
        blocks.append(
            Panel(confusions, title="Easily confused with", border_style="magenta", expand=False)
        )

    facts = Text()
    facts.append("Invariant  ", style="bold")
    facts.append(f"{pattern.invariant.strip()}\n")
    facts.append("Complexity ", style="bold")
    facts.append(f"time {pattern.complexity.time}, space {pattern.complexity.space}\n")
    if pattern.data_structures:
        facts.append("Uses       ", style="bold")
        facts.append(", ".join(pattern.data_structures))
    blocks.append(Panel(facts, border_style="blue", expand=False))

    if pattern.traps:
        traps = Table(box=None, show_header=False, pad_edge=False)
        traps.add_column()
        for trap in pattern.traps:
            text = Text()
            text.append(trap.description.strip(), style="bold")
            if trap.symptom:
                text.append(f"\n  symptom: {trap.symptom.strip()}", style="bright_black")
            traps.add_row(text)
        blocks.append(Panel(traps, title="Common mistakes", border_style="yellow", expand=False))

    return Group(*blocks)
