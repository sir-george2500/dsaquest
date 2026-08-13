"""The happy paths and the ordinary failures a learner actually hits."""

from __future__ import annotations

import pytest

from dsaquest.domain import CheckerKind, Limits, Submission, TestCase, Verdict
from dsaquest.judge import judge

pytestmark = pytest.mark.slow

SUM_TO_N = """
#include <bits/stdc++.h>
int main(){
    std::ios::sync_with_stdio(false); std::cin.tie(nullptr);
    long long n; std::cin >> n;
    std::cout << n * (n + 1) / 2 << "\\n";
}
"""

TESTS = [
    TestCase(name="small", stdin="10\n", expected="55\n"),
    TestCase(name="one", stdin="1\n", expected="1\n"),
    TestCase(
        name="large",
        stdin="1000000\n",
        expected="500000500000\n",
        hidden=True,
        characterisation="n = 10^6",
    ),
]


def test_correct_solution_is_accepted():
    report = judge(Submission(source=SUM_TO_N), TESTS)
    assert report.accepted, report.first_failure
    assert report.passed == report.total == 3
    assert report.max_cpu_ms >= 0


def test_wrong_answer_reports_the_first_divergence():
    bad = SUM_TO_N.replace("n * (n + 1) / 2", "n * (n + 1)")
    report = judge(Submission(source=bad), TESTS)
    assert report.verdict is Verdict.WRONG_ANSWER
    failure = report.first_failure
    assert failure is not None
    assert "expected 55" in failure.diff_hint and "got 110" in failure.diff_hint


def test_integer_overflow_is_caught_by_the_large_hidden_test():
    """The classic trap: `int` passes the samples and dies on n = 10^6."""
    overflowing = SUM_TO_N.replace("long long n;", "int n;").replace(
        "n * (n + 1) / 2", "(int)(n * (n + 1) / 2)"
    )
    report = judge(Submission(source=overflowing), TESTS)
    assert report.verdict is Verdict.WRONG_ANSWER
    assert report.first_failure.name == "large"


def test_compile_error_is_reported_with_a_clean_path():
    report = judge(Submission(source="int main(){ this is not c++ }"), TESTS)
    assert report.verdict is Verdict.COMPILE_ERROR
    assert report.total == 0
    assert "solution.cpp" in report.compile_log
    assert "/box/" not in report.compile_log, "sandbox paths leaked into user-facing output"


def test_segfault_is_explained_not_just_labelled():
    source = "#include <vector>\nint main(){ std::vector<int> v; return v.at(5); }"
    report = judge(Submission(source=source), [TestCase(name="t", stdin="", expected="")])
    assert report.verdict is Verdict.RUNTIME_ERROR
    assert report.first_failure.diff_hint


def test_division_by_zero_is_diagnosed():
    """Both operands must be runtime-unknown.

    With a literal numerator, GCC 16 at -O2 replaces `1/z` with a branchless
    cmova sequence and never emits idiv, so no SIGFPE is raised at all.
    """
    source = (
        "#include <cstdio>\n"
        'int main(){ int a, b; if (scanf("%d %d", &a, &b) != 2) return 1;'
        ' printf("%d\\n", a / b); }'
    )
    report = judge(Submission(source=source), [TestCase(name="t", stdin="1 0\n", expected="")])
    assert report.verdict is Verdict.RUNTIME_ERROR
    assert "division" in report.first_failure.diff_hint


def test_optimised_undefined_behaviour_is_explained_as_such():
    """-O2 turns provable UB into `ud2` → SIGILL, which is baffling without a hint."""
    source = '#include <cstdio>\nint main(){ int z = 0; printf("%d", 1 / z); }'
    report = judge(Submission(source=source), [TestCase(name="t", stdin="", expected="")])
    assert report.verdict is Verdict.RUNTIME_ERROR
    assert "undefined behaviour" in report.first_failure.diff_hint


def test_all_tests_run_by_default_so_failure_count_is_informative():
    """Failing 1 of 3 is a different diagnosis from failing 3 of 3."""
    only_ten = '#include <cstdio>\nint main(){ printf("55\\n"); }'
    report = judge(Submission(source=only_ten), TESTS)
    assert report.total == 3
    assert report.passed == 1


def test_stop_on_first_failure_is_opt_in():
    only_ten = '#include <cstdio>\nint main(){ printf("55\\n"); }'
    report = judge(Submission(source=only_ten), TESTS, stop_on_first_failure=True)
    assert report.total == 2


def test_empty_input_is_not_a_judge_error():
    source = """
    #include <bits/stdc++.h>
    int main(){ long long n = 0; std::cin >> n; std::cout << n * (n+1) / 2 << "\\n"; }
    """
    report = judge(Submission(source=source), [TestCase(name="empty", stdin="", expected="0\n")])
    assert report.verdict is not Verdict.INTERNAL_ERROR


def test_progress_hook_fires_per_test():
    seen = []
    judge(Submission(source=SUM_TO_N), TESTS, on_result=seen.append)
    assert [o.name for o in seen] == ["small", "one", "large"]


def test_float_checker_tolerates_epsilon():
    source = '#include <cstdio>\nint main(){ printf("3.1415926\\n"); }'
    report = judge(
        Submission(source=source),
        [TestCase(name="pi", stdin="", expected="3.14159265\n")],
        checker=CheckerKind.FLOAT,
    )
    assert report.accepted


def test_generous_limits_do_not_false_positive_on_a_heavy_but_valid_solution():
    source = """
    #include <bits/stdc++.h>
    int main(){
        std::vector<int> v(5'000'000);
        std::iota(v.begin(), v.end(), 0);
        std::cout << std::accumulate(v.begin(), v.end(), 0LL) << "\\n";
    }
    """
    report = judge(
        Submission(source=source),
        [TestCase(name="heavy", stdin="", expected="12499997500000\n")],
        limits=Limits(cpu_ms=4000, wall_ms=9000, memory_mb=256),
    )
    assert report.accepted, (report.verdict, report.first_failure)
