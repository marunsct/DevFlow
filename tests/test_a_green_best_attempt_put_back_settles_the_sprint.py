"""A sprint whose best attempt, put back as it runs out, passes every acceptance test settles, not planned again.

Measured on one run: a kept fix broke one acceptance test, the sprint ran out at 28 of 29, the settle rule read that
measurement, and only then was the best attempt (29 of 29, only unit tests failing) put back - and the green sprint
was planned again.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.acceptance import suite
from app.graph import best_attempt, end_of_attempt, settle_when_green
from app.stacks import contract, pack_named
from app.sprint import Defect


def _defect(description, source="acceptance suite", criteria=()):
    return Defect(description=description, severity="major", reproduction_steps="r", expected_behavior="e",
                  actual_behavior="a", owner="backend", source=source, failing_criteria=list(criteria))


def _measured(root, passed, failed, ac8):
    (root / suite.RESULT_FILE).parent.mkdir(parents=True, exist_ok=True)
    (root / suite.RESULT_FILE).write_text(json.dumps({
        "ran": True, "passed": passed, "failed": failed,
        "criteria": {"AC-8": {"status": ac8}, "AC-2": {"status": "passed"}}}))


def test_a_defect_about_criteria_that_pass_after_the_put_back_is_not_open(tmp_path, monkeypatch):
    monkeypatch.setenv("SETTLE_WHEN_ACCEPTANCE_IS_GREEN", "on")
    contract.write(tmp_path, pack_named("node-hono-native-api"), "bookmarks", "Bookmarks")
    _measured(tmp_path, 29, 0, "passed")
    broken = _defect("[AC-8] POST rejects a bad link - the acceptance suite says this does not work yet.", criteria=["AC-8"])
    unit = _defect("The unit tests fail. It says: 1 failing", source="test round")
    still = settle_when_green.open_after_the_put_back(tmp_path, [broken, unit])
    assert [d.status for d in still] == ["fixed", "open"]
    assert settle_when_green.applies(tmp_path, still, 1) is True
    # Without the put-back reading, the acceptance defect keeps the sprint from settling.
    assert settle_when_green.applies(tmp_path, [broken, unit], 1) is False


def test_the_attempt_settles_when_the_best_put_back_passes_every_acceptance_test(tmp_path, monkeypatch):
    monkeypatch.setenv("SETTLE_WHEN_ACCEPTANCE_IS_GREEN", "on")
    monkeypatch.setenv("KEEP_THE_BEST_ATTEMPT", "on")
    contract.write(tmp_path, pack_named("node-hono-native-api"), "bookmarks", "Bookmarks")
    (tmp_path / "bookmarks").mkdir()
    (tmp_path / "bookmarks" / "server.ts").write_text("the best product\n")
    for args in (("init", "-q"), ("add", "."), ("commit", "-q", "-m", "first")):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       check=True, capture_output=True)
    _measured(tmp_path, 29, 0, "passed")
    best_attempt.note(tmp_path)
    (tmp_path / "bookmarks" / "server.ts").write_text("a kept fix that broke one acceptance test\n")
    _measured(tmp_path, 28, 1, "failed")
    # The suite's runner, measuring the product put back: green again.
    monkeypatch.setattr(suite, "run", lambda root, **kwargs: _measured(Path(root), 29, 0, "passed"))
    broken = _defect("[AC-8] POST rejects a bad link - the acceptance suite says this does not work yet.", criteria=["AC-8"])
    unit = _defect("The unit tests fail. It says: 1 failing", source="test round")

    decided = end_of_attempt.decide(str(tmp_path), [broken, unit], replans=1, best_history=[])

    assert decided.outcome == end_of_attempt.SETTLE
    assert decided.put_back
    assert (tmp_path / "bookmarks" / "server.ts").read_text() == "the best product\n"
