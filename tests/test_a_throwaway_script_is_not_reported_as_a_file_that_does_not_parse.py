"""A harness scratch file with a typo in it was the first defect of a sprint.

A command given as `python -c CODE` is run from a `tmp-inline-<hash>.py` file the harness saves in the
project; a stage's one-liner with a syntax error stayed there, and the cross-file parse check raised it
as "does not parse" for a fixer. Every other consumer of the scratch-name rule already skipped such files.
"""
from __future__ import annotations

from app.analysis import integration_checks


def test_a_scratch_file_that_does_not_parse_is_not_a_defect_and_a_product_file_still_is(tmp_path):
    (tmp_path / "tmp-inline-3ed15a9c.py").write_text("import time,sys; sys.path.insert(0,'x'); from y import (z\n")
    (tmp_path / "app.py").write_text("def broken(:\n    pass\n")
    (tmp_path / "ok.py").write_text("x = 1\n")

    problems = integration_checks._a_source_file_that_does_not_parse(
        sorted(tmp_path.glob("*.py")), tmp_path)

    assert len(problems) == 1 and problems[0].startswith("app.py does not parse")


def test_the_other_scratch_names_are_skipped_too(tmp_path):
    for name in ("temp2.py", "scratch_probe.py", "debug_run.py"):
        (tmp_path / name).write_text("def broken(:\n")

    assert integration_checks._a_source_file_that_does_not_parse(sorted(tmp_path.glob("*.py")), tmp_path) == []
