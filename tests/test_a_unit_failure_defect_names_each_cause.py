"""A failing unit run's defect names each distinct cause, and each failure by its error line, not its frame.

Measured on one run: eighteen unit tests failed on a table their fixture never made and two on a call the test
client does not offer. The report's messages opened with the frame (`self = <...>`, `data_dir = '/tmp/...'`), the
first 600 characters never reached the error, and the defect's summary held only the last cause's cut-off lines.
Two fix rounds changed one assertion each and the sprint was planned again.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app import ci
from app.graph import workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
FRAME = "self = <tests.test_store.TestRecords object at 0x7f>\ndata_dir = '/tmp/x'\n\n" + "    def body(self):\n" * 40


def _failed(name, error, within="tests.test_store.TestRecords"):
    return SimpleNamespace(outcome="failed", name=name, within=within, file="",
                           message=FRAME + f">       store.add('a')\n\nE           {error}\n\nstore.py:53: {error.split(':')[0]}")


TESTS = [_failed(f"test_{n}", "sqlite3.OperationalError: no such table: records") for n in range(18)] + [
    _failed("test_signin", "TypeError: 'dict' object is not callable", within="tests.test_auth.TestFlow"),
    _failed("test_signin_wrong", "TypeError: 'dict' object is not callable", within="tests.test_auth.TestFlow"),
    SimpleNamespace(outcome="passed", name="test_ok", within="", file="", message=""),
]


def test_each_failure_is_shown_by_its_error_line():
    said = ci.what_the_failing_unit_tests_say(TESTS)
    listed = said.split(ci.DISTINCT_CAUSES)[0]
    assert "self = <" not in listed and listed.count("no such table: records") == 12
    # The first twelve listed share one cause; the other is named only because the causes are grouped.
    assert "'dict' object is not callable" not in listed and "'dict' object is not callable" in said


def test_the_causes_are_grouped_most_failing_first():
    causes = ci.the_distinct_causes("runner output\n" + ci.what_the_failing_unit_tests_say(TESTS))
    lines = causes.splitlines()
    assert lines[0] == ci.DISTINCT_CAUSES
    assert lines[1].startswith("- 18 failing") and lines[1].endswith("sqlite3.OperationalError: no such table: records")
    assert lines[2].startswith("- 2 failing") and "tests.test_auth.TestFlow › test_signin" in lines[2]


def test_the_defect_says_every_cause():
    output = "....FF\n" + "FAILED tests/test_store.py::x - sqli...\n" * 8 + ci.what_the_failing_unit_tests_say(TESTS)
    defect = workflow._the_unit_tests_fail(SimpleNamespace(delegated_tasks=[]), output)
    stated = defect.description.split("The runner's output ends:")[0]
    assert "no such table: records" in stated and "'dict' object is not callable" in stated


def test_one_failure_or_a_short_message_is_as_before():
    one = [SimpleNamespace(outcome="failed", name="t", within="", file="a.test.js", message="expected 2 to be 3")]
    assert ci.what_the_failing_unit_tests_say(one) == (
        "Failing tests, from the runner's report:\n- t (a.test.js): expected 2 to be 3")
    assert ci.the_distinct_causes("nothing grouped here") == ""


def test_its_words_ban_the_product_s_nouns():
    assert not BANNED.search(ci.DISTINCT_CAUSES + " failing, e.g.")
