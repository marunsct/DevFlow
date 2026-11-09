"""A sprint whose suites are green is not planned again for a finding a check read from the files.

Measured on one run: every acceptance test and every unit test passed, and the sprint was planned again for a
cross-file finding about scratch files a dead attempt left in the unit-test folder - which told the team to widen the
pattern of the test script the harness keeps.
"""
from __future__ import annotations

import json
import re

from app.acceptance import suite
from app.analysis import integration_checks
from app.graph import settle_when_green
from app.sprint import Defect
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _defect(source, description="notes-api/package.json runs `x`, which runs only what it matches.", criteria=()):
    return Defect(description=description, severity="major", reproduction_steps="r", expected_behavior="e",
                  actual_behavior="a", owner="testing", source=source, failing_criteria=list(criteria))


def _green(monkeypatch, failed=0):
    monkeypatch.setenv("SETTLE_WHEN_ACCEPTANCE_IS_GREEN", "on")
    monkeypatch.setattr(suite, "last_result", lambda root: {"ran": True, "passed": 11, "failed": failed})
    monkeypatch.setattr(suite, "_command", lambda root: (["npm", "run", "test:acceptance"], "notes-api"))


def test_a_cross_file_finding_beside_a_green_suite_settles(tmp_path, monkeypatch):
    _green(monkeypatch)
    assert settle_when_green.applies(tmp_path, [_defect("cross-file check")], 0) is True


def test_a_failing_criterion_or_a_red_suite_does_not(tmp_path, monkeypatch):
    _green(monkeypatch)
    criterion = _defect("acceptance suite", "[AC-12] DELETE answers 204", criteria=["AC-12"])
    criterion.caught_by = "npm run test:acceptance"
    assert settle_when_green.applies(tmp_path, [_defect("cross-file check"), criterion], 0) is False
    _green(monkeypatch, failed=1)
    assert settle_when_green.applies(tmp_path, [_defect("cross-file check")], 0) is False


def test_stranded_files_beside_the_pack_s_kept_script_are_moved_or_deleted_not_the_script_widened(tmp_path):
    pack = pack_named("node-hono-native-api")
    contract.write(tmp_path, pack, "notes-api", "Notes")
    project = tmp_path / "notes-api"
    (project / "test").mkdir(parents=True, exist_ok=True)
    (project / "package.json").write_text(json.dumps({"type": "module", "scripts": {"test": pack.kept_scripts["test"]}}))
    (project / "test" / "app.test.ts").write_text("import { test } from 'node:test';\ntest('a', () => {});\n")
    (project / "test" / "child-verify-1793213270934.mjs").write_text("import { test } from 'node:test';\ntest('b', () => {});\n")
    files = [p for p in project.rglob("*") if p.is_file()]
    found = [f for f in integration_checks._tests_the_project_never_runs(files, tmp_path) if "Stranded" in f]
    assert found and "put back before every run" in found[0] and "Widen the pattern" not in found[0]
    assert not BANNED.search(found[0])
