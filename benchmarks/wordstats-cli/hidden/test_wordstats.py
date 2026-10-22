"""Hidden acceptance tests for the wordstats-cli benchmark, written from brief.md's Interface."""

import json
import os
import subprocess
import sys
from pathlib import Path

PRODUCT = os.environ["PRODUCT_DIR"]
TEXT = "The cat and the hat.\nThe cat sat\n"  # 8 words, 2 lines, 33 characters


def run(*args, stdin=None, cwd=None):
    env = {**os.environ, "PYTHONPATH": PRODUCT}
    return subprocess.run(
        [sys.executable, "-m", "wordstats", *args],
        input=stdin, capture_output=True, text=True, env=env, cwd=cwd or PRODUCT, timeout=60,
    )


def _file(tmp_path: Path, text=TEXT) -> str:
    path = tmp_path / "sample.txt"
    path.write_text(text)
    return str(path)


def test_counts_words_lines_and_characters(tmp_path):
    done = run(_file(tmp_path))
    assert done.returncode == 0, done.stderr
    assert done.stdout.split("\n")[:3] == ["words: 8", "lines: 2", "characters: 33"]


def test_a_last_line_without_a_newline_still_counts(tmp_path):
    done = run(_file(tmp_path, "one two\nthree"))
    assert "lines: 2" in done.stdout and "words: 3" in done.stdout


def test_lists_the_most_frequent_words(tmp_path):
    done = run(_file(tmp_path), "--top", "2")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip().splitlines() == ["the 3", "cat 2"]


def test_ties_are_alphabetical(tmp_path):
    done = run(_file(tmp_path, "pear apple pear apple fig"), "--top", "3")
    assert done.stdout.strip().splitlines() == ["apple 2", "pear 2", "fig 1"]


def test_json_output(tmp_path):
    done = run(_file(tmp_path), "--json")
    assert json.loads(done.stdout) == {"words": 8, "lines": 2, "characters": 33}


def test_json_top_words(tmp_path):
    done = run(_file(tmp_path), "--top", "1", "--json")
    assert json.loads(done.stdout) == {"top": [{"word": "the", "count": 3}]}


def test_reads_standard_input():
    done = run("-", stdin="it's a test\n")
    assert done.returncode == 0, done.stderr
    assert "words: 3" in done.stdout


def test_a_missing_file_is_an_error(tmp_path):
    done = run(str(tmp_path / "nope.txt"))
    assert done.returncode == 2
    assert done.stderr.strip() and not done.stdout.strip()
