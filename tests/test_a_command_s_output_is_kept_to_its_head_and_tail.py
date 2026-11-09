"""A command's output is kept to a bound - its start and its end - while it is read, not cut down afterwards.

Found in review: the sandbox read a command's stdout and stderr line by line
into lists and joined them whole, and the product fingerprint read `git diff`
whole; only then was the output cut to what a model is shown. A product that
prints without end grew the Celery pool process by everything it printed,
outside every rlimit the command had - the limits bound the command, not the
process reading it. A stream with no newline was read as one line, whole.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from app.tools import bounded_output, sandbox

LIMIT = 64 * 1024


@pytest.fixture
def small_bound(monkeypatch):
    monkeypatch.setattr(bounded_output, "MOST_CAPTURED_CHARACTERS_PER_STREAM", LIMIT)
    monkeypatch.setattr(sandbox, "_tree_budget_bytes", lambda: 4 * 1024**3)


def _printing(code: str):
    return sandbox._run_and_watch_the_tree(
        [sys.executable, "-c", code], cwd=os.getcwd(), env=dict(os.environ), timeout=60
    )


def test_a_command_that_prints_without_end_is_kept_to_its_head_and_tail(small_bound):
    result = _printing(
        "import sys\n"
        "print('FIRST LINE')\n"
        "for i in range(200000): print('noise', i)\n"
        "print('LAST LINE')\n"
        "print('x' * 10, file=sys.stderr)\n"
    )

    assert result.returncode == 0
    assert len(result.stdout) < LIMIT + 200, "kept to the bound, plus the line naming what was left out"
    assert result.stdout.startswith("FIRST LINE") and result.stdout.rstrip().endswith("LAST LINE")
    assert "characters of output left out here" in result.stdout
    assert result.stderr == "x" * 10 + "\n", "a stream inside the bound is kept whole"


def test_one_line_with_no_newline_is_read_in_pieces(small_bound):
    result = _printing("import sys; sys.stdout.write('a' * 3_000_000 + 'END')")

    assert len(result.stdout) < LIMIT + 200
    assert result.stdout.startswith("a") and result.stdout.endswith("END")


def test_what_was_left_out_still_tells_two_outputs_apart():
    """The fingerprint compares kept text: a change in the middle must still change it."""
    kept, other = bounded_output.HeadAndTail(100), bounded_output.HeadAndTail(100)
    for stream, middle in ((kept, "one"), (other, "two")):
        stream.append("h" * 60)
        stream.append(middle * 50)
        stream.append("t" * 60)

    assert kept.text() != other.text()
    assert kept.text().startswith("h" * 50) and kept.text().endswith("t" * 50)


def test_the_run_bounded_helper_answers_as_subprocess_run_does(small_bound):
    done = bounded_output.run_bounded(
        [sys.executable, "-c", "import sys; print('out' * 100000); print('err', file=sys.stderr); sys.exit(3)"]
    )

    assert done.returncode == 3 and done.stderr == "err\n"
    assert len(done.stdout) < LIMIT + 200 and done.stdout.rstrip().endswith("out")

    with pytest.raises(subprocess.TimeoutExpired):
        bounded_output.run_bounded([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)


def test_the_product_fingerprint_reads_git_to_the_bound(small_bound, tmp_path):
    from app.acceptance import unstable

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "data.txt").write_text("start\n")
    git("add", ".")
    git("commit", "-q", "-m", "first")
    (tmp_path / "data.txt").write_text("".join(f"line {i}\n" for i in range(100000)))

    diff = unstable._git(tmp_path, "diff", "HEAD")

    assert diff is not None and len(diff) < LIMIT + 200
    assert "characters of output left out here" in diff
