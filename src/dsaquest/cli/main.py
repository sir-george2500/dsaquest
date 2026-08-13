"""The ``dsa`` command.

Textual is imported lazily, inside the commands that actually need it, so the
read-only commands (``stats``, ``patterns``, ``streak``) start in well under a
second. Checking your progress should not cost a UI framework load.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    name="dsa",
    help="A terminal game for training C++ pattern recognition.",
    no_args_is_help=False,
    add_completion=False,
)

DbOption = Annotated[
    Path | None,
    typer.Option("--db", help="Path to the progress database (default: user data dir)."),
]


def _context(db: Path | None):
    from ..context import build

    return build(db)


def _launch(db: Path | None, *, review_only: bool = False, size: int = 8) -> None:
    from ..tui.app import DsaQuestApp

    context = _context(db)
    try:
        DsaQuestApp(context, review_only=review_only, session_size=size).run()
    finally:
        context.close()


@app.callback(invoke_without_command=True)
def default(ctx: typer.Context, db: DbOption = None) -> None:
    """Launch the interactive app when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        _launch(db)


@app.command()
def practice(
    db: DbOption = None,
    size: Annotated[int, typer.Option("--size", "-n", help="Exercises this session.")] = 8,
) -> None:
    """Start a session chosen by the scheduler."""
    _launch(db, size=size)


@app.command()
def review(
    db: DbOption = None,
    size: Annotated[int, typer.Option("--size", "-n")] = 12,
) -> None:
    """Practise only what is due."""
    _launch(db, review_only=True, size=size)


@app.command()
def stats(db: DbOption = None) -> None:
    """Progress, mastery per pattern, and what to do next."""
    from ..game.levels import progress
    from ..learning.mastery import all_mastery, weakest_patterns
    from ..learning.planner import build_session
    from ..storage import repositories as repo
    from .render import console, header, mastery_table

    context = _context(db)
    try:
        mastery = all_mastery(context.conn, context.library, scheduler=context.scheduler)
        plan = build_session(
            context.conn, context.library, context.bank, scheduler=context.scheduler
        )
        streak = repo.get_streak(context.conn, "daily")

        console.print(header(progress(context.profile.xp), streak.current, plan.due_count))
        console.print()
        console.print(mastery_table(context.library, mastery, repo.unlocked_patterns(context.conn)))
        console.print()

        confusions = repo.confusion_pairs(context.conn, limit=3)
        if confusions:
            console.print("[bold]Most common confusions[/bold]")
            for actual, chosen, count in confusions:
                console.print(
                    f"  [red]{count}x[/red] called [bold]{actual}[/bold] problems "
                    f"[yellow]{chosen}[/yellow]"
                )
            console.print()

        mistakes = repo.top_mistakes(context.conn, limit=3)
        if mistakes:
            console.print("[bold]Most common mistakes[/bold]")
            for code, count in mistakes:
                console.print(f"  [red]{count}x[/red] {code.value}")
            console.print()

        weak = weakest_patterns(mastery, limit=1)
        if weak:
            console.print(f"[bold]Weakest pattern[/bold]  {weak[0].pattern_id}")
        console.print(f"[bold]Next session[/bold]  {plan.recommendation}")
    finally:
        context.close()


@app.command()
def patterns(db: DbOption = None) -> None:
    """List every pattern with its mastery."""
    from ..learning.mastery import all_mastery
    from ..storage import repositories as repo
    from .render import console, mastery_table

    context = _context(db)
    try:
        mastery = all_mastery(context.conn, context.library, scheduler=context.scheduler)
        console.print(mastery_table(context.library, mastery, repo.unlocked_patterns(context.conn)))
    finally:
        context.close()


@app.command()
def pattern(
    pattern_id: Annotated[str, typer.Argument(help="Pattern id, e.g. sliding-window")],
    db: DbOption = None,
    template: Annotated[bool, typer.Option("--template", help="Print the C++ template.")] = False,
) -> None:
    """Show a pattern's signals, confusions, invariant and traps."""
    from rich.syntax import Syntax

    from ..content.paths import read_template
    from .render import console, pattern_detail

    context = _context(db)
    try:
        if pattern_id not in context.library:
            console.print(f"[red]Unknown pattern[/red] {pattern_id!r}")
            console.print("Known: " + ", ".join(p.id for p in context.library))
            raise typer.Exit(1)

        found = context.library[pattern_id]
        if template:
            console.print(
                Syntax(
                    read_template(found.template_file),
                    "cpp",
                    theme="ansi_dark",
                    line_numbers=True,
                )
            )
        else:
            console.print(pattern_detail(found, context.library))
    finally:
        context.close()


@app.command()
def streak(db: DbOption = None) -> None:
    """Show your daily streak."""
    from ..storage import repositories as repo
    from .render import console

    context = _context(db)
    try:
        record = repo.get_streak(context.conn, "daily")
        if record.current:
            console.print(
                f"[bold yellow]{record.current}[/bold yellow] day streak "
                f"[bright_black](best {record.best})[/bright_black]"
            )
        else:
            console.print(
                f"No active streak [bright_black](best {record.best})[/bright_black] — "
                "run [bold]dsa practice[/bold] to start one."
            )
    finally:
        context.close()


@app.command()
def doctor(db: DbOption = None) -> None:
    """Check the sandbox, the toolchain, and the content tree."""
    from ..content.paths import content_root
    from ..judge import probe
    from ..judge.workspace import editor_command
    from ..storage.db import integrity_check
    from .render import console

    ok = True

    console.print("[bold]Sandbox[/bold]")
    for capability, present in probe().items():
        mark = "[green]yes[/green]" if present else "[red]NO[/red]"
        console.print(f"  {capability:12s} {mark}")
        if capability in {"bwrap", "prlimit", "userns"} and not present:
            ok = False

    console.print("\n[bold]Editor[/bold]")
    try:
        console.print(f"  {' '.join(editor_command())}")
    except RuntimeError as exc:
        console.print(f"  [red]{exc}[/red]")
        ok = False

    context = _context(db)
    try:
        console.print("\n[bold]Content[/bold]")
        console.print(f"  {content_root()}")
        console.print(f"  {len(context.library)} patterns, {len(context.bank)} problems")

        console.print("\n[bold]Database[/bold]")
        problems = integrity_check(context.conn)
        if problems:
            ok = False
            for problem in problems:
                console.print(f"  [red]{problem}[/red]")
        else:
            console.print("  [green]healthy[/green]")
    finally:
        context.close()

    if not ok:
        console.print(
            "\n[red]Some checks failed.[/red] On Arch: sudo pacman -S bubblewrap util-linux"
        )
        raise typer.Exit(1)
    console.print("\n[green]All good.[/green]")


if __name__ == "__main__":  # pragma: no cover
    app()


@app.command()
def train(
    master: Annotated[
        str | None, typer.Argument(help="Master id, e.g. master_bits. Omit to list them.")
    ] = None,
    db: DbOption = None,
) -> None:
    """Train under a master: he teaches a secret, drills it, then tests you."""
    from .render import console

    context = _context(db)
    try:
        if not context.masters:
            console.print("[yellow]No masters are teaching yet.[/]")
            raise typer.Exit(1)

        if master is None:
            console.print("[bold]Masters accepting students[/]\n")
            for found in context.masters.values():
                from ..storage import repositories as repo

                respect = repo.get_respect(context.conn, found.id)
                console.print(f"  [b]{found.id}[/]  {found.title}")
                console.print(
                    f"      teaches [cyan]{', '.join(found.patterns)}[/]   "
                    f"[bright_black]respect {respect}[/]\n"
                )
            console.print("[dim]dsa train <master_id>[/]")
            return

        if master not in context.masters:
            console.print(f"[red]Unknown master[/] {master!r}")
            console.print("Known: " + ", ".join(context.masters))
            raise typer.Exit(1)

        from ..tui.app import DsaQuestApp
        from ..tui.master import MasterScreen

        chosen = context.masters[master]
        application = DsaQuestApp(context)
        application.pending_screen = MasterScreen(chosen, context.curricula)
        application.run()
    finally:
        context.close()
