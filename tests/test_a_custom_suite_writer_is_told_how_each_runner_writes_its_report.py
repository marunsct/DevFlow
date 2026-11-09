"""A suite on a stack with no pack is written by agents who declare its runners: they are told each runner's JUnit form.

Measured on one run: a browser runner was asked for its report as `--reporter=junit:<path>`, a form it does not read,
and the run failed after five rounds; on the rerun the writer tried three flag forms in a row.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.acceptance import requests
from app.plugins.seed import JUNIT_REPORTS
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_a_suite_with_no_pack_is_told_each_runner_s_form(monkeypatch):
    monkeypatch.setattr(contract, "the_pack", lambda root: None)
    said = requests._how_to_write_them("/w", "app", "acceptance", SimpleNamespace(testing_framework="pytest and Playwright"))
    assert JUNIT_REPORTS in said
    assert "outputFile" in said and "--junitxml" in said and "PLAYWRIGHT_JUNIT_OUTPUT_NAME" in said
    assert not BANNED.search(JUNIT_REPORTS)


def test_a_suite_a_pack_runs_is_not(monkeypatch):
    pack = SimpleNamespace(kind="http_api", acceptance_guide="Write tests with httpx.", acceptance_test=("pytest",),
                           filled=lambda text, project, title, package: text)
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {"project": "app"}))
    assert JUNIT_REPORTS not in requests._how_to_write_them("/w", "app", "acceptance", None)
