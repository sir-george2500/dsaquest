"""Mode A (Pattern Hunter) and Mode C (Code Completion)."""

from __future__ import annotations

import pytest

from dsaquest.content.loader import load_library
from dsaquest.content.problems import load_problems
from dsaquest.domain.enums import GameMode
from dsaquest.game.modes import (
    TemplateError,
    build_round,
    build_round_for,
    choose_problem,
    exercise_source,
    find_hole,
    judge_round,
    parse_holes,
    reference_source,
    splice,
)
from dsaquest.game.modes.complete import TODO_MARKER
from dsaquest.storage import repositories as repo
from dsaquest.storage.db import connect


@pytest.fixture(scope="module")
def library():
    return load_library()


@pytest.fixture(scope="module")
def bank(library):
    return load_problems(library)


@pytest.fixture
def conn():
    connection = connect(":memory:")
    repo.ensure_profile(connection)
    yield connection
    connection.close()


# --------------------------------------------------------------------------
# Pattern Hunter
# --------------------------------------------------------------------------


def test_every_pattern_has_problems(library, bank):
    """A pattern with no statements cannot be played in the mode that matters."""
    missing = {p.id for p in library} - bank.patterns_with_problems()
    assert not missing, f"no problems for: {sorted(missing)}"


def test_no_statement_gives_away_its_own_pattern(bank):
    for problem in bank:
        assert not problem.names_pattern, f"{problem.id} names its pattern in the statement"


def test_distractors_come_from_the_confusion_graph(library, bank):
    """Random distractors make the question trivial; confusable ones make it real."""
    problem = bank["signal-run-k-frequencies"]
    round_ = build_round(library, problem, seed=1)

    offered = {option.pattern_id for option in round_.options} - {problem.pattern}
    confusable = set(library.confusable_ids(problem.pattern))
    assert offered & confusable, "no distractor was drawn from the confusion graph"


def test_the_correct_answer_is_always_present(library, bank):
    for problem in bank:
        for seed in range(5):
            round_ = build_round(library, problem, seed=seed)
            assert round_.correct_option.pattern_id == problem.pattern


def test_options_are_distinct(library, bank):
    for problem in bank:
        round_ = build_round(library, problem, seed=3)
        ids = [option.pattern_id for option in round_.options]
        assert len(ids) == len(set(ids))


def test_rounds_are_reproducible_from_the_seed(library, bank):
    problem = bank["signal-run-k-frequencies"]
    first = build_round(library, problem, seed=99)
    second = build_round(library, problem, seed=99)
    assert [o.pattern_id for o in first.options] == [o.pattern_id for o in second.options]
    assert first.correct_index == second.correct_index


def test_different_seeds_move_the_correct_answer_around(library, bank):
    """If the answer is always 'A', the mode teaches nothing."""
    problem = bank["signal-run-k-frequencies"]
    positions = {build_round(library, problem, seed=s).correct_index for s in range(30)}
    assert len(positions) > 1


def test_distractors_adapt_to_your_own_confusions(library, bank):
    """Your wrong answers should make later rounds harder, not stay static."""
    problem = bank["signal-run-k-frequencies"]
    confusable = library.confusable_ids(problem.pattern)
    assert len(confusable) >= 2

    favoured = confusable[-1]
    biased = build_round(library, problem, seed=5, history={favoured: 50}, choices=2)
    assert favoured in {o.pattern_id for o in biased.options}


def test_a_round_needs_at_least_two_options(library, bank):
    with pytest.raises(ValueError):
        build_round(library, bank["signal-run-k-frequencies"], seed=1, choices=1)


def test_asking_for_more_options_than_exist_fails_loudly(library, bank):
    """Better to error than to quietly show a two-way guess."""
    with pytest.raises(ValueError, match="distractors available"):
        build_round(library, bank["signal-run-k-frequencies"], seed=1, choices=99)


def test_a_correct_answer_is_graded_correct(library, bank):
    problem = bank["signal-run-k-frequencies"]
    round_ = build_round(library, problem, seed=7)
    feedback = judge_round(library, round_, round_.correct_index)
    assert feedback.correct
    assert feedback.why
    assert feedback.signals


def test_a_confusable_wrong_answer_returns_the_discriminator(library, bank):
    """The payload of the whole mode: not 'wrong', but 'here is how to tell'."""
    problem = bank["signal-run-k-frequencies"]
    confusable = library.confusable_ids(problem.pattern)[0]
    round_ = build_round(library, problem, seed=11, history={confusable: 99})

    index = round_.option_index(confusable)
    assert index is not None
    feedback = judge_round(library, round_, index)

    assert not feedback.correct
    assert feedback.has_tell, "a known confusion must return its tell"
    assert len(feedback.tell.split()) >= 8


def test_grading_an_out_of_range_choice_fails(library, bank):
    round_ = build_round(library, bank["signal-run-k-frequencies"], seed=1)
    with pytest.raises(IndexError):
        judge_round(library, round_, 99)


def test_options_are_labelled_for_display(library, bank):
    round_ = build_round(library, bank["signal-run-k-frequencies"], seed=1)
    labels = [label for label, _ in round_.labelled()]
    assert labels == ["A", "B", "C", "D"]


def test_problem_selection_avoids_recently_seen(library, bank):
    pattern = "sliding-window"
    all_ids = {p.id for p in bank.for_pattern(pattern)}
    assert len(all_ids) >= 2
    exclude = frozenset({next(iter(all_ids))})
    chosen = {choose_problem(bank, pattern, seed=s, exclude=exclude).id for s in range(20)}
    assert not (chosen & exclude)


def test_selection_falls_back_rather_than_showing_nothing(library, bank):
    """Repeating a problem beats an empty screen."""
    pattern = "sliding-window"
    everything = frozenset(p.id for p in bank.for_pattern(pattern))
    assert choose_problem(bank, pattern, seed=1, exclude=everything).pattern == pattern


def test_round_building_reads_confusion_history_from_the_database(conn, library, bank):
    attempt_id = repo.start_attempt(conn, pattern_id="sliding-window", mode=GameMode.HUNTER, seed=1)
    repo.finish_attempt(conn, attempt_id, correct=False, chosen_pattern_id="prefix-sum")

    from dsaquest.game.modes.hunter import confusion_counts

    assert confusion_counts(conn, "sliding-window") == {"prefix-sum": 1}
    round_ = build_round_for(conn, library, bank, "sliding-window", seed=2, choices=2)
    assert "prefix-sum" in {o.pattern_id for o in round_.options}


# --------------------------------------------------------------------------
# Code Completion
# --------------------------------------------------------------------------

SAMPLE = """int main() {
// >>> HOLE id=alpha prompt=Compute the running total
    int total = 0;
    total += 1;
// <<< HOLE
// >>> HOLE id=beta prompt=Return it
    return total;
// <<< HOLE
}"""


def test_holes_are_parsed_with_prompts_and_bodies():
    holes = parse_holes(SAMPLE)
    assert [h.id for h in holes] == ["alpha", "beta"]
    assert holes[0].prompt == "Compute the running total"
    assert holes[0].line_count == 2
    assert "total += 1;" in holes[0].body


def test_reference_keeps_all_code_and_drops_all_markers():
    reference = reference_source(SAMPLE)
    assert "HOLE" not in reference
    assert "total += 1;" in reference
    assert "return total;" in reference


def test_the_exercise_empties_only_the_chosen_hole():
    exercise = exercise_source(SAMPLE, "alpha")
    assert "total += 1;" not in exercise, "the target hole must be emptied"
    assert "return total;" in exercise, "other holes stay filled in"
    assert TODO_MARKER in exercise
    assert "Compute the running total" in exercise
    assert "HOLE" not in exercise


def test_splicing_the_reference_body_reproduces_the_reference():
    hole = find_hole(SAMPLE, "alpha")
    assert splice(SAMPLE, "alpha", hole.body) == reference_source(SAMPLE)


def test_splicing_replaces_only_the_chosen_hole():
    spliced = splice(SAMPLE, "beta", "    return 42;")
    assert "return 42;" in spliced
    assert "return total;" not in spliced
    assert "total += 1;" in spliced


def test_an_unclosed_hole_is_a_content_error():
    with pytest.raises(TemplateError, match="never closed"):
        parse_holes("// >>> HOLE id=x prompt=y\nint a;")


def test_a_stray_close_is_a_content_error():
    with pytest.raises(TemplateError, match="without being opened"):
        parse_holes("int a;\n// <<< HOLE")


def test_nested_holes_are_a_content_error():
    source = (
        "// >>> HOLE id=a prompt=p\n// >>> HOLE id=b prompt=q\nint x;\n// <<< HOLE\n// <<< HOLE\n"
    )
    with pytest.raises(TemplateError, match="still open"):
        parse_holes(source)


def test_duplicate_hole_ids_are_a_content_error():
    source = (
        "// >>> HOLE id=dup prompt=p\nint x;\nint y;\n// <<< HOLE\n"
        "// >>> HOLE id=dup prompt=q\nint z;\nint w;\n// <<< HOLE\n"
    )
    with pytest.raises(TemplateError, match="duplicate hole ids"):
        parse_holes(source)


def test_asking_for_an_unknown_hole_lists_what_exists():
    with pytest.raises(TemplateError, match="alpha, beta"):
        find_hole(SAMPLE, "gamma")


def test_a_template_without_holes_parses_as_empty():
    assert parse_holes("int main(){}") == ()
