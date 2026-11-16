"""Quality tests for the wordstats-cli benchmark: the brief's interface at its edges (LR.25).

Scored apart from the hidden tests. Each holds the command to something the brief already says that the hidden tests
do not reach; the benchmark's reference passes every one.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PRODUCT = os.environ["PRODUCT_DIR"]


def run(*args):
    env = {**os.environ, "PYTHONPATH": PRODUCT}
    return subprocess.run([sys.executable, "-m", "wordstats", *args], capture_output=True, text=True, env=env,
                          cwd=PRODUCT, timeout=60)


def _file(tmp_path: Path, text: str) -> str:
    path = tmp_path / "sample.txt"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_an_empty_file_has_nothing_in_it(tmp_path):
    done = run(_file(tmp_path, ""))
    assert done.returncode == 0, done.stderr
    assert done.stdout.split("\n")[:3] == ["words: 0", "lines: 0", "characters: 0"]


def test_a_last_line_without_a_newline_still_counts(tmp_path):
    done = run(_file(tmp_path, "one\ntwo"))
    assert done.stdout.split("\n")[:3] == ["words: 2", "lines: 2", "characters: 7"]


def test_apostrophes_stay_inside_a_word_and_punctuation_splits(tmp_path):
    done = run("--json", _file(tmp_path, "don't stop-now, it's fine"))
    assert json.loads(done.stdout)["words"] == 5


def test_top_counts_words_in_lower_case_and_orders_ties_alphabetically(tmp_path):
    done = run("--top", "3", "--json", _file(tmp_path, "b a B c A b"))
    assert json.loads(done.stdout)["top"] == [{"word": "b", "count": 3}, {"word": "a", "count": 2},
                                              {"word": "c", "count": 1}]


def test_top_larger_than_the_distinct_words_lists_them_all(tmp_path):
    done = run("--top", "10", _file(tmp_path, "x y x"))
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip().splitlines() == ["x 2", "y 1"]


def test_a_missing_file_says_so_on_standard_error_only(tmp_path):
    done = run(str(tmp_path / "nope.txt"))
    assert done.returncode == 2 and done.stderr.strip() and not done.stdout.strip()
