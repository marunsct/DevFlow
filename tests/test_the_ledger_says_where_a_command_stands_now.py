"""A fixed command must not read like a broken one.

Run 0afef410's milestone reviewer was handed the execution ledger as a
chronological list and nothing else:

    25 command(s) executed, 4 succeeded:
    ... - [testing_specialist] npm test -> exit 1   (four times)
    ... - [testing_specialist] npm test -> OK

and wrote a Major finding: "Test execution logs show multiple failures (exit 1)
across several commands. The test suite does not pass." At that moment
`npm test` in that workspace exited 0 with `# pass 4 # fail 0` - verified by
running it. The reading was fair on what it was given, and it sent the
milestone back for a defect that did not exist.

A command that failed and later succeeded has been fixed, and the failures are
the record of fixing it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.tools.sandbox import summarise_executions

#: The shape run 0afef410 produced, cut down to the part that misled.
HISTORY = [
    ("testing_specialist", ["npm", "test"], 1),
    ("testing_specialist", ["npm", "test"], 1),
    ("testing_specialist", ["npm", "test"], 0),
    ("ui_ux_specialist", ["node", "--test", "app.test.mjs"], 1),
]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "task-manager-run-abc"
    root.mkdir()
    return root


def _write(root: Path, entries) -> None:
    from app.tools.sandbox import _ledger_path

    path = _ledger_path(str(root))
    assert path is not None
    path.write_text(
        "\n".join(
            json.dumps({"role": role, "command": argv, "returncode": code})
            for role, argv, code in entries
        )
        + "\n",
        encoding="utf-8",
    )


def test_a_command_that_was_fixed_reads_as_OK_now(workspace: Path):
    _write(workspace, HISTORY)

    digest = summarise_executions(str(workspace))

    standing = digest.split("Where each distinct command stands now", 1)[1]
    assert "npm test -> OK" in standing
    assert "npm test -> exit 1" not in standing


def test_a_command_still_failing_is_still_shown_failing(workspace: Path):
    _write(workspace, HISTORY)

    standing = summarise_executions(str(workspace)).split(
        "Where each distinct command stands now", 1
    )[1]

    assert "node --test app.test.mjs -> exit 1" in standing


def test_the_attempts_are_still_there(workspace: Path):
    """The history is evidence of the work; it is only the verdict that moved."""
    _write(workspace, HISTORY)

    digest = summarise_executions(str(workspace))

    before = digest.split("Where each distinct command stands now", 1)[0]
    assert before.count("npm test -> exit 1") == 2


def test_it_says_how_to_read_the_two_lists(workspace: Path):
    _write(workspace, HISTORY)

    digest = summarise_executions(str(workspace))

    assert "Judge the product by this list" in digest
    assert "has been fixed" in digest
    assert "Only a command whose most recent run failed is still failing" in digest


def test_each_distinct_command_appears_once(workspace: Path):
    _write(workspace, HISTORY)

    standing = summarise_executions(str(workspace)).split(
        "Where each distinct command stands now", 1
    )[1]

    assert standing.count("npm test ->") == 1


def test_an_empty_workspace_is_unchanged(workspace: Path):
    assert summarise_executions(str(workspace)) == (
        "No commands were executed in this workspace."
    )
