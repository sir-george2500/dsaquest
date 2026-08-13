"""Training under a master, driven headlessly."""

from __future__ import annotations

import asyncio

import pytest

from dsaquest.context import build
from dsaquest.storage import repositories as repo
from dsaquest.tui.app import DsaQuestApp
from dsaquest.tui.master import MasterScreen

MASTER_ID = "master_bits"


@pytest.fixture
def context(tmp_path):
    ctx = build(tmp_path / "progress.db", fuzz=False)
    yield ctx
    ctx.close()


def _run(coro):
    return asyncio.run(coro)


def _launch(context, *, seed: int = 20260813):
    """Always pin the seed: an unpinned session deals a different drill each run."""
    app = DsaQuestApp(context)
    app.pending_screen = MasterScreen(context.masters[MASTER_ID], context.curricula, seed=seed)
    return app


def _text(screen, selector: str) -> str:
    return str(screen.query_one(selector).visual)


def _flat(screen, selector: str) -> str:
    """Rendered text with whitespace collapsed.

    Panels wrap, so a substring assertion against the raw render breaks on line
    breaks that fall in the middle of the phrase being checked. The drill dealt
    also varies per run (the seed is the wall clock), so assertions must not
    depend on which one came up.
    """
    return " ".join(_text(screen, selector).split())


def _squash(text: str) -> str:
    return " ".join(text.split())


def test_the_master_greets_and_teaches_the_first_secret(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, MasterScreen)

            assert _text(screen, "#say").strip()
            lesson = _flat(screen, "#lesson")
            assert "SECRET 1/5" in lesson
            assert "n & 1" in lesson
            assert "DEMONSTRATION" in lesson
            assert "WATCH FOR" in lesson
            assert screen.phase == "teach"

        # Delivering the lesson must be recorded, not merely displayed.
        assert repo.get_secret_progress(context.conn, MASTER_ID, "lowest-bit").is_taught

    _run(scenario())


def test_the_portrait_renders_without_any_image_support(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            assert _text(app.screen, "#portrait").strip()

    _run(scenario())


def test_space_moves_from_the_lesson_into_drills(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()

            screen = app.screen
            assert screen.phase == "drill"
            assert screen.drill is not None
            assert _text(screen, "#drill").strip()

    _run(scenario())


def test_answering_a_drill_correctly_is_recorded_and_explained(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()

            screen = app.screen
            drill = screen.drill
            assert drill is not None

            if drill.options:
                await pilot.press(str(drill.correct_index + 1))
            else:
                screen.answer(drill.answer)
            await pilot.pause()

            verdict = _flat(screen, "#verdict")
            assert "Correct" in verdict
            assert _squash(drill.explanation)[:40] in verdict

        progress = repo.get_secret_progress(context.conn, MASTER_ID, "lowest-bit")
        assert progress.drills_seen == 1
        assert progress.drills_correct == 1

    _run(scenario())


def test_a_wrong_answer_reveals_the_answer_and_still_explains(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()

            screen = app.screen
            drill = screen.drill
            assert drill is not None
            wrong = next(o for o in drill.options if o != drill.answer) if drill.options else "no"
            screen.answer(wrong)
            await pilot.pause()

            verdict = _flat(screen, "#verdict")
            assert "No." in verdict
            assert _squash(drill.answer) in verdict, "a wrong answer must reveal the right one"

        # Failing a drill must never cost respect.
        assert repo.get_respect(context.conn, MASTER_ID) == 0

    _run(scenario())


def test_drilling_a_secret_to_fluency_advances_the_stage(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()

            screen = app.screen
            for _ in range(12):
                drill = screen.drill
                if drill is None:
                    break
                screen.answer(drill.answer)
                await pilot.pause()
                if screen.phase == "fluent":
                    break
                await pilot.press("space")
                await pilot.pause()

            assert screen.phase == "fluent"
            assert "FLUENT" in _flat(screen, "#verdict")

            await pilot.press("space")
            await pilot.pause()
            # Fluency does not advance the stage — it opens that stage's trial.
            # Teaching the next secret before testing this one would leave the
            # loop at teach-and-drill, which proves nothing.
            assert screen.phase == "trial"
            assert screen.trial is not None
            assert screen.trial.stage.order == 0

        assert repo.get_respect(context.conn, MASTER_ID) > 0

    _run(scenario())


def test_the_track_shows_which_secrets_are_done(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            track = _flat(app.screen, "#track")
            assert "n & 1" in track
            assert "respect" in track

    _run(scenario())


def test_escape_leaves_the_master(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, MasterScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, MasterScreen)

    _run(scenario())


def _drill_stage_to_fluency(screen, pilot):
    """Answer drills correctly until the stage is fluent."""

    async def run():
        await pilot.press("space")
        await pilot.pause()
        for _ in range(14):
            drill = screen.drill
            if drill is None:
                break
            screen.answer(drill.answer)
            await pilot.pause()
            if screen.phase == "fluent":
                return True
            await pilot.press("space")
            await pilot.pause()
        return False

    return run()


def test_a_trial_follows_the_drills_with_the_pattern_hidden(context):
    """The half that proves anything: the master stops naming the pattern."""

    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert await _drill_stage_to_fluency(screen, pilot)

            await pilot.press("space")
            await pilot.pause()

            assert screen.phase == "trial", "fluency must lead into a trial, not the next lesson"
            statement = _flat(screen, "#statement")
            assert "TRIAL" in statement
            assert "Which pattern should you use?" in statement
            assert "bit manipulation" not in statement.lower(), "the trial named its own pattern"

            assert screen.trial is not None
            assert screen.trial.budget.has_deadline, "a trial must run a clock"
            assert len(screen.query("#choices Button")) == 4

    _run(scenario())


def test_the_trial_clock_is_generous(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert await _drill_stage_to_fluency(screen, pilot)
            await pilot.press("space")
            await pilot.pause()

            budget = screen.trial.budget
            assert budget.limit_ms >= budget.target_ms * 1.9
            assert budget.limit_ms >= 150_000, "under two and a half minutes to read and decide"
            assert _text(screen, "#clock").strip()

    _run(scenario())


def test_passing_the_trial_marks_the_secret_tested_and_pays_respect(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert await _drill_stage_to_fluency(screen, pilot)
            await pilot.press("space")
            await pilot.pause()

            before = repo.get_respect(context.conn, MASTER_ID)
            screen.answer_trial(screen.trial.round.correct_index)
            await pilot.pause()

            assert screen.phase == "trial_done"
            assert "PASSED" in _flat(screen, "#verdict")
            assert repo.get_respect(context.conn, MASTER_ID) > before

        assert repo.get_secret_progress(context.conn, MASTER_ID, "lowest-bit").state == "tested"

    _run(scenario())


def test_failing_the_trial_shows_the_discriminator(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert await _drill_stage_to_fluency(screen, pilot)
            await pilot.press("space")
            await pilot.pause()

            round_ = screen.trial.round
            wrong = (round_.correct_index + 1) % len(round_.options)
            screen.answer_trial(wrong)
            await pilot.pause()

            verdict = _flat(screen, "#verdict")
            assert "No." in verdict
            assert "Why:" in verdict

        # A failed trial must not mark the secret tested.
        assert repo.get_secret_progress(context.conn, MASTER_ID, "lowest-bit").state != "tested"

    _run(scenario())


def test_a_timeout_is_recorded_as_a_speed_result_not_a_lapse(context):
    """The load-bearing rule, end to end: the clock must not corrupt memory."""

    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert await _drill_stage_to_fluency(screen, pilot)
            await pilot.press("space")
            await pilot.pause()

            screen.answer_trial(None)  # ran out of clock
            await pilot.pause()

            assert "TIME" in _flat(screen, "#verdict")

        row = context.conn.execute(
            "SELECT timed_out, limit_ms FROM attempt WHERE mode='hunter' "
            "AND finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["timed_out"] == 1
        assert row["limit_ms"] is not None

        rating = context.conn.execute(
            "SELECT rating FROM review_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert rating["rating"] == "hard", "a timeout must never rate as forgotten"

    _run(scenario())


def test_phase_timing_is_persisted_for_the_trial(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert await _drill_stage_to_fluency(screen, pilot)
            await pilot.press("space")
            await pilot.pause()
            screen.answer_trial(screen.trial.round.correct_index)
            await pilot.pause()

        attempt = context.conn.execute(
            "SELECT id FROM attempt WHERE mode='hunter' AND finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert "recognise" in repo.phase_breakdown(context.conn, attempt["id"])

    _run(scenario())


def test_continuing_after_a_trial_teaches_the_next_secret(context):
    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert await _drill_stage_to_fluency(screen, pilot)
            await pilot.press("space")
            await pilot.pause()
            screen.answer_trial(screen.trial.round.correct_index)
            await pilot.pause()

            await pilot.press("space")
            await pilot.pause()

            assert screen.phase == "teach"
            assert "SECRET 2/5" in _flat(screen, "#lesson")

    _run(scenario())


def test_square_brackets_in_content_survive_rendering(context):
    """C++ is full of `a[i]`, and `[i]` is an italic tag in this markup.

    Unescaped, the learner is shown `a & 1` when the drill asked about
    `a[i] & 1` — a different expression — and the rest of the line silently
    turns italic. This guards every content string on the screen.
    """

    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen

            # Find the drill whose answer contains a subscript.
            for _ in range(14):
                await pilot.press("space")
                await pilot.pause()
                drill = screen.drill
                if drill is None:
                    break
                if "[" in drill.answer or "[" in drill.prompt:
                    screen.answer("deliberately wrong")
                    await pilot.pause()
                    rendered = _flat(screen, "#verdict") + _flat(screen, "#drill")
                    assert "[" in rendered, "square brackets were eaten by the markup parser"
                    return
                screen.answer(drill.answer)
                await pilot.pause()
                if screen.phase in ("fluent", "trial"):
                    break
        pytest.skip("no bracketed drill was dealt with this seed")

    _run(scenario())


def _complete_curriculum(context, seed_base=500):
    """Drill and pass every stage, so the final test unlocks."""
    from dsaquest.lessons import (
        current_stage,
        deal,
        grade,
        judge_trial,
        open_trial,
        pending_trial,
        teach,
    )

    master = context.masters[MASTER_ID]
    curriculum = context.curricula[MASTER_ID]
    for n in range(24):
        stage = pending_trial(context.conn, curriculum)
        if stage is not None:
            trial = open_trial(
                context.conn,
                master,
                context.library,
                context.bank,
                curriculum,
                stage,
                seed=seed_base + n,
            )
            judge_trial(
                context.conn,
                master,
                context.library,
                curriculum,
                trial,
                trial.round.correct_index,
                scheduler=context.scheduler,
                seed=seed_base + n,
            )
            continue
        stage = current_stage(context.conn, curriculum)
        if stage is None:
            return True
        teach(context.conn, master, curriculum, stage, seed=seed_base + n)
        for i in range(16):
            drill = deal(context.conn, curriculum, stage, seed=seed_base + n * 100 + i)
            if drill is None:
                break
            if grade(
                context.conn, master, curriculum, stage, drill, drill.answer, seed=i
            ).became_fluent:
                break
    return False


def test_the_final_test_is_gated_until_every_secret_is_tested(context):
    """A gate that can be walked through is not a gate."""
    from dsaquest.lessons import final_test

    assert not final_test.available(context.conn, context.curricula[MASTER_ID])

    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            screen.start_final_test()
            await pilot.pause()
            assert screen.exam is None, "the final test opened without the gate being met"

    _run(scenario())


def test_completing_the_curriculum_offers_the_final_test(context):
    from dsaquest.lessons import final_test

    assert _complete_curriculum(context)
    assert final_test.available(context.conn, context.curricula[MASTER_ID])

    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert screen.phase == "gate"
            lesson = _flat(screen, "#lesson")
            assert "FINAL TEST" in lesson
            assert "Nothing will be named" in lesson

    _run(scenario())


def test_passing_the_final_test_earns_the_masters_respect(context):
    assert _complete_curriculum(context)

    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            before = repo.get_respect(context.conn, MASTER_ID)

            await pilot.press("space")
            await pilot.pause()
            assert screen.phase == "exam"

            for _ in range(10):
                if screen.exam is None or screen.exam.current is None:
                    break
                screen.answer_exam(screen.exam.current.round.correct_index)
                await pilot.pause()

            verdict = _flat(screen, "#verdict")
            assert "THE MASTER IS SATISFIED" in verdict
            assert repo.get_respect(context.conn, MASTER_ID) > before

        progress = repo.get_master_progress(context.conn, MASTER_ID)
        assert progress.passed
        assert progress.best_score == progress.best_total

    _run(scenario())


def test_the_final_test_gives_no_feedback_between_rounds(context):
    """It tests; it does not coach. Feedback would let you correct mid-sitting."""
    assert _complete_curriculum(context)

    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            screen = app.screen

            first = screen.exam.current
            screen.answer_exam(first.round.correct_index)
            await pilot.pause()

            assert screen.phase == "exam", "should go straight to the next problem"
            assert screen.exam.current.number == 2
            assert not screen.query_one("#verdict").display

    _run(scenario())


def test_failing_the_final_test_names_what_to_train(context):
    assert _complete_curriculum(context)

    async def scenario():
        app = _launch(context)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            screen = app.screen

            for _ in range(10):
                if screen.exam is None or screen.exam.current is None:
                    break
                round_ = screen.exam.current.round
                screen.answer_exam((round_.correct_index + 1) % len(round_.options))
                await pilot.pause()

            verdict = _flat(screen, "#verdict")
            assert "NOT YET" in verdict
            assert "Train, then return" in verdict

        progress = repo.get_master_progress(context.conn, MASTER_ID)
        assert not progress.passed
        assert progress.attempts == 1

    _run(scenario())


def test_a_passed_final_test_is_never_revoked(context):
    """A master does not un-recognise what you proved."""
    assert _complete_curriculum(context)
    repo.record_final_test(context.conn, MASTER_ID, score=4, total=4, passed=True)
    repo.record_final_test(context.conn, MASTER_ID, score=0, total=4, passed=False)

    progress = repo.get_master_progress(context.conn, MASTER_ID)
    assert progress.passed
    assert progress.best_score == 4
