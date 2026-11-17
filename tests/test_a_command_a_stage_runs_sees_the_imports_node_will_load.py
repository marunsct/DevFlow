"""A command a stage runs sees the relative imports Node will load, not only the harness's measurement.

Measured on a small-model run of the pack that Node runs itself: drafted tests imported `../src/datastore.js` where
`src/datastore.ts` existed, and two testing work orders spent 55 calls on ERR_MODULE_NOT_FOUND before the harness added
the extension itself at its first measurement.
"""
from __future__ import annotations

import re
import sys

from app.stacks import contract, pack_named
from app.tools.sandbox import SandboxExecutor

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _scaffolded(tmp_path):
    pack = pack_named("node-hono-native-api")
    contract.write(tmp_path, pack, "notes", "Notes")
    root = tmp_path / "notes"
    for relative, text in pack.render("notes", "Notes", None).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (root / "src" / "datastore.ts").write_text("export const store = 1;\n")
    (root / "test").mkdir(exist_ok=True)
    test = root / "test" / "datastore.test.ts"
    test.write_text("import { store } from '../src/datastore.js';\n")
    return test


def _run(tmp_path, *, for_the_harness=False):
    return SandboxExecutor.execute(
        [sys.executable, "-c", "print('ran')"], str(tmp_path), role_name="testing_specialist",
        category="test", working_directory="notes", for_the_harness=for_the_harness,
    )


def test_a_stage_s_command_runs_on_imports_that_name_the_ts_file(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTENSIONS_BEFORE_A_RUN", "on")
    test = _scaffolded(tmp_path)

    outcome = _run(tmp_path)

    assert test.read_text() == "import { store } from '../src/datastore.ts';\n"
    note = str(outcome.get("note") or "")
    assert "name the `.ts` file itself" in note
    assert not BANNED.search(note)


def test_switched_off_or_for_the_harness_nothing_moves(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTENSIONS_BEFORE_A_RUN", "off")
    test = _scaffolded(tmp_path)
    _run(tmp_path)
    assert test.read_text() == "import { store } from '../src/datastore.js';\n"

    monkeypatch.setenv("EXTENSIONS_BEFORE_A_RUN", "on")
    _run(tmp_path, for_the_harness=True)
    assert test.read_text() == "import { store } from '../src/datastore.js';\n"
