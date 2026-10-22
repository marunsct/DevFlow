"""A fast fix rewrites the files its own defect names, not those of the run's last failing command.

Measured live: a page check's "the interface is not styled" was rewritten as its
stylesheet and `tests/test_tasks.py`. The test file was named by another
fixer's unit-test run - the run's last failing command, which every rewrite is
given - the rewritten test broke 17 tests, and the revert took the stylesheet
with it.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph.rewritten_fixes import THE_LAST_FAILING_COMMAND, files_to_fix

LAST = (f"{THE_LAST_FAILING_COMMAND}\n.venv/bin/python -m pytest\n"
        "ERROR collecting shop/tests/test_items.py\nshop/shop_pkg/auth.py:12: in <module>")


def _workspace(tmp_path):
    for name in ("shop/src/styles.css", "shop/src/App.tsx", "shop/tests/test_items.py", "shop/shop_pkg/auth.py"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x\n")
    return tmp_path


def test_a_styling_defect_rewrites_its_stylesheet_and_nothing_the_last_command_named(tmp_path):
    defect = SimpleNamespace(description="The interface is not styled: the only stylesheet is shop/src/styles.css.",
                             affected_files=[])
    failure = "The interface is not styled: the only stylesheet is shop/src/styles.css.\n\n" + LAST

    assert files_to_fix(defect, failure, _workspace(tmp_path), lambda path: True) == ["shop/src/styles.css"]


def test_the_last_command_is_used_when_the_defect_names_no_file(tmp_path):
    defect = SimpleNamespace(description="Signing in fails.", affected_files=[])

    found = files_to_fix(defect, "Signing in fails.\n\n" + LAST, _workspace(tmp_path), lambda path: True)

    assert found == ["shop/shop_pkg/auth.py"], "a test file is not taken from the text for a defect not about tests"


def test_a_unit_test_failure_may_rewrite_the_test_its_output_names(tmp_path):
    defect = SimpleNamespace(description="The unit tests fail. The runner's output ends: ERROR collecting "
                                         "shop/tests/test_items.py", affected_files=[])

    found = files_to_fix(defect, defect.description, _workspace(tmp_path), lambda path: True)

    assert found == ["shop/tests/test_items.py"]
