"""A suite no command runs is a false green, not an unused file.

Run b6436e36 shipped a three-file suite in which
`task-manager/ui.pw.test.mjs` is a Playwright spec while `scripts.test` is
`node --test`, which throws on another runner's spec rather than running it.
No gate in that pipeline executed the file once, and the finding whose own
words are "has no script that runs" it was handed to the milestone reviewer
under the heading "untidy rather than broken - dead rules, unused files".

`_BREAKS_BEHAVIOUR` already carries two routes to this same false green - a
suite that never executed, and one the gating command cannot parse. This was
the third, and its own docstring predicted the miss: "Classified untidy at
first for want of a phrase in this tuple, which is the stale-marker failure
this file is most exposed to."

`test_every_marker_is_a_phrase_some_message_really_emits` guards the other
direction - that no marker has gone stale. It cannot catch a breaking message
with no marker, which is this.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _severity_of,
    _source_files,
    summarise_integration,
)

STRANDED = (
    "task-manager/package.json has no script that runs task-manager/ui.pw.test.mjs "
    "- they are @playwright/test specs, and nothing in this manifest invokes "
    "@playwright/test. `scripts.test` cannot be made to run them: `node --test` "
    "throws on another runner's spec rather than failing. Add a script that calls "
    "the right runner."
)


def test_the_message_from_the_run_is_graded_as_breaking() -> None:
    assert _severity_of(STRANDED) == "BREAKS"


def test_an_ordinary_tidiness_finding_is_still_tidiness() -> None:
    """The grade has to separate them, or it grades nothing."""
    untidy = (
        "task-manager/app.js exports 10 name(s) and no test mentions generateId, "
        "init. A passing suite says nothing about those."
    )

    assert _severity_of(untidy) == "untidy"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    app = tmp_path / "app"
    app.mkdir()
    (app / "package.json").write_text(
        json.dumps({"name": "app", "type": "module", "scripts": {"test": "node --test app.test.mjs"}}),
        encoding="utf-8",
    )
    (app / "app.js").write_text("export function addTask(t) { return t; }\n", encoding="utf-8")
    (app / "app.test.mjs").write_text(
        "import { test } from 'node:test';\ntest('adds', () => {});\n", encoding="utf-8"
    )
    (app / "ui.pw.test.mjs").write_text(
        "import { test, expect } from '@playwright/test';\n"
        "test.describe('ui', () => { test('adds', async ({ page }) => {}); });\n",
        encoding="utf-8",
    )
    (app / "index.html").write_text(
        '<!doctype html><html><body><script type="module" src="app.js"></script></body></html>',
        encoding="utf-8",
    )
    return tmp_path


def test_the_reviewer_is_told_it_breaks_something(project: Path) -> None:
    """End to end: the heading the finding arrives under is what a reviewer
    reads before deciding a severity."""
    summary = summarise_integration(str(project))

    assert "has no script that runs" in summary
    stranded_line = next(
        line for line in summary.splitlines() if "has no script that runs" in line
    )
    breaking = summary.index("mean a feature DOES NOT WORK") if "DOES NOT WORK" in summary else -1
    untidy = summary.index("untidy rather") if "untidy rather" in summary else len(summary)

    assert breaking >= 0, summary
    assert summary.index(stranded_line) < untidy, "it is still filed under untidy"
