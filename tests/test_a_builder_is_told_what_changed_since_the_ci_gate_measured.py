"""A builder is told which files changed since the CI gate measured, so it does not read an old verdict as now (plan PH.4).

The block's CI line is a measurement of one commit; a sibling's later change
made it stale without a word. Behind `STATE_AT_DISPATCH`, off until measured,
and only inside `WHERE_THINGS_STAND`'s block.
"""
from __future__ import annotations

import os
import re
import subprocess
from types import SimpleNamespace
from unittest import mock

from app.agents import where_things_stand

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def _measured_then_changed(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "h@example.com")
    _git(tmp_path, "config", "user.name", "h")
    (tmp_path / "app.py").write_text("a = 1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "batch")
    commit = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app.py").write_text("a = 2\n")
    (tmp_path / "store.py").write_text("b = 1\n")
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "ci.json").write_text("{}")
    return {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "ci_report": "Unit tests: 4 of 4 pass; acceptance tests: 2 of 6 pass.",
        "ci_batch_commit": commit,
    }


def test_on_the_block_names_the_product_s_files_changed_since_the_measurement(tmp_path):
    state = _measured_then_changed(tmp_path)
    with mock.patch.dict(os.environ, {"WHERE_THINGS_STAND": "on", "STATE_AT_DISPATCH": "on"}):
        text = where_things_stand.block(state)

    line = next(l for l in text.splitlines() if l.startswith("- Changed since that measurement"))
    assert "`app.py`" in line and "`store.py`" in line
    assert ".harness" not in line
    assert not BANNED.search(line)


def test_off_or_unchanged_there_is_no_such_line(tmp_path):
    state = _measured_then_changed(tmp_path)
    with mock.patch.dict(os.environ, {"WHERE_THINGS_STAND": "on", "STATE_AT_DISPATCH": ""}):
        assert "Changed since" not in where_things_stand.block(state)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "later")
    state["ci_batch_commit"] = _git(tmp_path, "rev-parse", "HEAD")
    with mock.patch.dict(os.environ, {"WHERE_THINGS_STAND": "on", "STATE_AT_DISPATCH": "on"}):
        assert "Changed since" not in where_things_stand.block(state)
