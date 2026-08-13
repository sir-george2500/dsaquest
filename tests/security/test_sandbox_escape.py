"""Adversarial tests: things a hostile (or merely broken) submission might try.

These spawn real compilers and real processes, so they are slow. They are also
the tests that must never be allowed to silently regress — a sandbox that has
quietly stopped sandboxing looks exactly like one that works.
"""

from __future__ import annotations

import pytest

from dsaquest.domain import Limits, Submission, TestCase, Verdict
from dsaquest.judge import judge

pytestmark = [pytest.mark.security, pytest.mark.slow]

TIGHT = Limits(cpu_ms=1000, wall_ms=3000, memory_mb=128, output_kb=64, max_pids=32)


def _run(source: str, *, stdin: str = "", expected: str = "", limits: Limits = TIGHT):
    return judge(
        Submission(source=source),
        [TestCase(name="t", stdin=stdin, expected=expected)],
        limits=limits,
    )


# --- resource exhaustion -------------------------------------------------------


def test_infinite_loop_is_killed():
    report = _run("int main(){ while(true){} }")
    assert report.verdict is Verdict.TIME_LIMIT
    assert report.outcomes[0].wall_ms <= TIGHT.wall_ms + 1500


def test_blocking_on_stdin_still_times_out():
    """RLIMIT_CPU never fires here — the process burns wall time, not CPU.

    This is the case a CPU-limit-only sandbox misses entirely.
    """
    report = _run("#include <iostream>\nint main(){ int x; std::cin>>x; std::cin>>x; }", stdin="")
    assert report.verdict in (Verdict.TIME_LIMIT, Verdict.ACCEPTED, Verdict.WRONG_ANSWER)


def test_memory_bomb_is_contained():
    source = """
    #include <vector>
    int main(){
        std::vector<std::vector<char>> hold;
        for(;;) hold.emplace_back(64u*1024u*1024u, 1);
    }
    """
    report = _run(source)
    assert report.verdict in (Verdict.MEMORY_LIMIT, Verdict.RUNTIME_ERROR, Verdict.TIME_LIMIT)
    assert report.verdict is not Verdict.ACCEPTED


def test_output_flood_is_capped():
    source = """
    #include <cstdio>
    int main(){ for(;;) fputs("flooooooooooooooooooood\\n", stdout); }
    """
    report = _run(source)
    assert report.verdict in (Verdict.OUTPUT_LIMIT, Verdict.TIME_LIMIT)
    assert len(report.outcomes[0].stdout_excerpt) < 200_000


def test_fork_pressure_is_contained():
    """Bounded fork pressure must not escape the cgroup's TasksMax.

    Deliberately linear rather than exponential: the point is to prove the limit
    binds, not to gamble the developer's machine on it.
    """
    source = """
    #include <unistd.h>
    int main(){
        for(int i=0;i<400;i++){ if(fork()==0){ sleep(30); _exit(0); } }
        sleep(30);
    }
    """
    report = _run(source)
    assert report.verdict is not Verdict.ACCEPTED


def test_deep_recursion_is_a_runtime_error_not_a_crash_of_the_judge():
    source = "int f(int n){ return n?f(n+1)+1:0; } int main(){ return f(1); }"
    report = _run(source)
    assert report.verdict in (Verdict.RUNTIME_ERROR, Verdict.MEMORY_LIMIT, Verdict.TIME_LIMIT)


# --- isolation -----------------------------------------------------------------


def test_network_is_unreachable():
    source = """
    #include <cstdio>
    #include <sys/socket.h>
    #include <netinet/in.h>
    #include <arpa/inet.h>
    int main(){
        int s = socket(AF_INET, SOCK_STREAM, 0);
        if (s < 0) { puts("NO_SOCKET"); return 0; }
        sockaddr_in a{}; a.sin_family = AF_INET; a.sin_port = htons(80);
        inet_pton(AF_INET, "1.1.1.1", &a.sin_addr);
        puts(connect(s, (sockaddr*)&a, sizeof a) == 0 ? "CONNECTED" : "BLOCKED");
    }
    """
    report = _run(source)
    assert "CONNECTED" not in report.outcomes[0].stdout_excerpt


@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "/etc/shadow", "/home", "/root/.ssh/id_rsa", "/proc/self/environ"],
)
def test_host_paths_are_not_readable(path: str):
    source = f"""
    #include <cstdio>
    int main(){{
        FILE* f = fopen("{path}", "r");
        puts(f ? "OPENED" : "DENIED");
        if (f) fclose(f);
    }}
    """
    report = _run(source)
    assert report.outcomes[0].stdout_excerpt.strip() == "DENIED", (
        f"{path} was readable from inside the sandbox"
    )


def test_home_directory_is_invisible():
    source = """
    #include <cstdio>
    #include <dirent.h>
    int main(){ DIR* d = opendir("/home"); puts(d ? "LISTED" : "HIDDEN"); if(d) closedir(d); }
    """
    report = _run(source)
    assert report.outcomes[0].stdout_excerpt.strip() == "HIDDEN"


def test_workspace_is_read_only_at_run_time():
    source = """
    #include <cstdio>
    int main(){
        FILE* f = fopen("/box/scratch.txt", "w");
        puts(f ? "WROTE" : "READONLY");
        if (f) fclose(f);
    }
    """
    report = _run(source)
    assert report.outcomes[0].stdout_excerpt.strip() == "READONLY"


# --- compile-time exfiltration -------------------------------------------------


def test_compiler_cannot_probe_host_paths():
    """``__has_include`` is a file-existence oracle. Inside the jail it must lie."""
    source = """
    #if __has_include("/etc/passwd") || __has_include("/home/delta-x/.bashrc")
    #error "HOST FILE VISIBLE TO PREPROCESSOR"
    #endif
    int main(){}
    """
    report = _run(source)
    assert report.verdict is not Verdict.COMPILE_ERROR, report.compile_log


def test_including_a_host_file_fails_to_compile():
    report = _run('#include "/etc/shadow"\nint main(){}')
    assert report.verdict is Verdict.COMPILE_ERROR
    assert "shadow" in report.compile_log.lower()
