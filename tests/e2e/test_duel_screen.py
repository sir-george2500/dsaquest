"""End-to-end coverage of Mode D — the Pattern Duel — through the real screen.

The duel engine shipped with tests of its own. This file covers the thing those
could not: that a player can actually reach a duel, see both statements, answer
it, and have the result land in the database.

The assertions that matter most here are the three *failure* shapes, because
they are the whole reason the mode exists. Getting one side wrong, swapping the
pair, and collapsing them onto a single pattern are different mistakes and the
screen must say so differently — a learner who swaps knows the pair and not the
tell, and a learner who collapses has not discriminated at all.
"""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Static

from dsaquest.context import build
from dsaquest.game.modes.duel import build_duel
from dsaquest.tui.app import DsaQuestApp, HomeScreen
from dsaquest.tui.duel import DuelScreen

SEED = 20260813

#: Markup that must never reach the screen as literal text. No single-letter
#: tags: ``[i]`` is both an italic tag and a C++ subscript, and problem
#: statements legitimately contain ``a[i]``, ``d[l]``, ``cnt[x]``.
LEAKED_MARKUP = (
    "[/]",
    "[b]",
    "[dim]",
    "[green]",
    "[red]",
    "[yellow]",
    "[cyan]",
    "[magenta]",
    "[b green]",
    "[b red]",
    "[b yellow]",
    "[b cyan]",
    "[b magenta]",
)


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


def _text(screen, selector: str) -> str:
    return str(screen.query_one(selector, Static).visual)


def _option_index(screen, pattern_id: str) -> int:
    return next(i for i, o in enumerate(screen.duel.options) if o.pattern_id == pattern_id)


async def _answer(pilot, screen, first: str, second: str) -> None:
    """Assign ``first`` to statement A and ``second`` to statement B."""
    for pattern_id in (first, second):
        await pilot.press(str(_option_index(screen, pattern_id) + 1))
        await pilot.pause()


def _duel_rows(context):
    return context.conn.execute(
        "SELECT pattern_id, correct, chosen_pattern_id FROM attempt WHERE mode = 'duel' ORDER BY id"
    ).fetchall()


def test_a_duel_shows_both_statements_and_two_options(context):
    """Both statements stay on screen the whole time — the mode is comparison."""

    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = DuelScreen(seed=SEED, rounds=1)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            statements = _text(screen, "#duel-statements")
            duel = screen.duel

            assert "STATEMENT A" in statements
            assert "STATEMENT B" in statements
            for problem in duel.problems:
                assert problem.title in statements
                # A meaningful slice of the real statement, not just the title.
                assert problem.statement.strip()[:60] in statements

            options = [b.label.plain for b in screen.query_one("#duel-choices").children]
            assert len(options) == 2
            for option in duel.options:
                assert any(option.name in label for label in options)

            # Statement A is asked first, and asking must not pre-empt the answer.
            assert "Statement A" in _text(screen, "#duel-ask")

    _run(journey())


def test_the_statements_never_name_their_own_pattern(context):
    """A duel that names its patterns in the prose answers itself."""

    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = DuelScreen(seed=SEED, rounds=1)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            statements = _text(screen, "#duel-statements")
            for pattern_id in screen.duel.pattern_ids:
                assert context.library[pattern_id].name not in statements

    _run(journey())


def test_option_order_is_not_the_answer_key(context):
    """Pressing 1 then 2 must not be a winning strategy.

    The engine orders the options independently of the statements. If it did
    not, positional guessing would beat the mode outright, so this asserts the
    property holds across many deals rather than trusting one.
    """
    positional_wins = 0
    deals = 60
    for offset in range(deals):
        duel = build_duel(context.library, context.bank, seed=SEED + offset)
        if duel.pair == duel.pattern_ids:
            positional_wins += 1

    assert 0 < positional_wins < deals, (
        f"option order tracked statement order {positional_wins}/{deals} times — "
        "a duel whose options are in statement order can be won by pressing 1 then 2"
    )


def test_a_correct_duel_credits_both_patterns(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = DuelScreen(seed=SEED, rounds=1)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            actual = screen.duel.pattern_ids
            await _answer(pilot, screen, actual[0], actual[1])

            verdict = _text(screen, "#duel-verdict")
            assert "Both right" in verdict
            # Only after answering may the patterns be named.
            for pattern_id in actual:
                assert context.library[pattern_id].name in verdict
            assert "XP" in verdict

        rows = _duel_rows(context)
        assert len(rows) == 2, "a duel is two identifications and records two attempts"
        assert [r[0] for r in rows] == list(actual)
        assert all(r[1] == 1 for r in rows)
        assert [r[2] for r in rows] == list(actual)

    _run(journey())


def test_swapping_the_pair_is_named_as_swapping(context):
    """Both patterns known, both on the wrong statement — the near miss."""

    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = DuelScreen(seed=SEED, rounds=1)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            actual = screen.duel.pattern_ids
            await _answer(pilot, screen, actual[1], actual[0])

            verdict = _text(screen, "#duel-verdict")
            assert "Swapped" in verdict
            assert screen.query_one("#duel-verdict", Static).has_class("wrong")

        rows = _duel_rows(context)
        assert len(rows) == 2
        assert all(r[1] == 0 for r in rows)
        # What they said, per statement — this is what feeds the confusion history.
        assert [r[2] for r in rows] == [actual[1], actual[0]]

    _run(journey())


def test_collapsing_onto_one_pattern_earns_nothing_on_either_side(context):
    """The side that happens to match is a coin landing well, not recognition."""

    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = DuelScreen(seed=SEED, rounds=1)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            actual = screen.duel.pattern_ids
            said = screen.duel.options[0].pattern_id
            await _answer(pilot, screen, said, said)

            verdict = _text(screen, "#duel-verdict")
            assert "called both of them" in verdict
            assert context.library[said].name in verdict

        rows = _duel_rows(context)
        assert len(rows) == 2
        assert all(r[1] == 0 for r in rows), (
            "collapsing must credit neither pattern, including the one that matched"
        )
        # Exactly one side matched by construction, and it still scored zero.
        matched = [r for r in rows if r[0] == r[2]]
        assert len(matched) == 1 and matched[0][0] in actual
        assert matched[0][1] == 0

    _run(journey())


def test_a_wrong_answer_offers_the_tell(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = DuelScreen(seed=SEED, rounds=1)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            actual = screen.duel.pattern_ids
            await _answer(pilot, screen, actual[1], actual[1])

            verdict = _text(screen, "#duel-verdict")
            assert "How to tell:" in verdict, "a duel is posed on a mutual confusion"
            assert screen.duel.tell.split("\n")[0][:40] in verdict or (
                screen.duel.reverse_tell.split("\n")[0][:40] in verdict
            )

    _run(journey())


def test_a_run_of_duels_ends_with_a_tally(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = DuelScreen(seed=SEED, rounds=3)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            for round_number in range(3):
                assert f"Duel {round_number + 1} of 3" in _text(screen, "#duel-progress")
                actual = screen.duel.pattern_ids
                await _answer(pilot, screen, actual[0], actual[1])
                await pilot.press("space")
                await pilot.pause()

            assert screen.finished
            assert "3 of 3 clean" in _text(screen, "#duel-verdict")
            assert "Nothing got past you" in _text(screen, "#duel-verdict")

        assert len(_duel_rows(context)) == 6

    _run(journey())


def test_the_home_screen_reaches_a_duel(context):
    """The mode is only real if a player can get to it without knowing the class."""

    async def journey():
        app = DsaQuestApp(context)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            await pilot.press("d")
            await pilot.pause()
            assert isinstance(app.screen, DuelScreen)
            # No seed pinned — this is the product's own path, so assert only
            # what is true of every deal.
            assert app.screen.duel is not None
            assert "STATEMENT A" in _text(app.screen, "#duel-statements")
            assert len(app.screen.query_one("#duel-choices").children) == 2

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

    _run(journey())


def test_no_markup_leaks_and_subscripts_survive(context):
    """``[i]`` is an italic tag and a C++ subscript. Statements are full of both."""

    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = DuelScreen(seed=SEED, rounds=1)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            panels = ["#duel-title", "#duel-progress", "#duel-statements", "#duel-ask"]

            seen = "\n".join(_text(screen, panel) for panel in panels)
            actual = screen.duel.pattern_ids
            await _answer(pilot, screen, actual[1], actual[0])
            seen += "\n" + _text(screen, "#duel-verdict")

            for tag in LEAKED_MARKUP:
                assert tag not in seen, f"{tag} leaked into the screen as text"

            # Whatever bracketed expressions the dealt content contains must
            # have survived intact rather than being eaten as markup.
            statements = _text(screen, "#duel-statements")
            for problem in screen.duel.problems:
                assert problem.constraints.strip().split("\n")[0] in statements

    _run(journey())


def test_a_pattern_with_no_confusable_partner_is_refused_not_faked(context):
    """Better to say there is no duel than to invent one that answers itself."""

    async def journey():
        app = DsaQuestApp(context)
        # A real pattern id that has no mutually-confusable partner with
        # problems on both sides would refuse; an unknown id refuses too, and
        # is the case we can pin without depending on the content mix.
        app.pending_screen = DuelScreen("no-such-pattern", seed=SEED, rounds=1)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert screen.duel is None
            assert "No duel to fight" in _text(screen, "#duel-statements")
            assert len(screen.query_one("#duel-choices").children) == 0

            # Pressing on regardless must not deal, crash, or record anything.
            for key in ("1", "2", "space"):
                await pilot.press(key)
                await pilot.pause()
            assert screen.duel is None

        assert _duel_rows(context) == []

    _run(journey())


def test_pinning_a_pattern_puts_it_in_the_duel(context):
    async def journey():
        app = DsaQuestApp(context)
        app.pending_screen = DuelScreen("sliding-window", seed=SEED, rounds=1)
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert screen.duel is not None
            assert "sliding-window" in screen.duel.pattern_ids
            assert "sliding-window" in screen.duel.pair

    _run(journey())
