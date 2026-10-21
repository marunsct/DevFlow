"""A fix that made nothing pass and wrote lines the language service is sure fail is reverted.

A fix is reverted for breaking what passed before it. With every test red -
the service not starting - nothing could break: measured on a gate run, a fix
wrote calls to a function its module never defined, was kept, and the service
crashed at start for every fixer after it.
"""
from __future__ import annotations

import subprocess

from app import ci
from app.graph import engineering


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=h@example.com", "-c", "user.name=h", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def _a_fix(tmp_path, fixed_main):
    (tmp_path / ".project-directory").write_text("items-api")
    package = tmp_path / "items-api" / "items_api"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "database.py").write_text("def connect(path):\n    return path\n")
    (package / "main.py").write_text("from items_api import database\n\nDB = database.connect('x')\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (package / "main.py").write_text(fixed_main)
    return base


def _underlined(found):
    """The language service as a stub: pyright is not on every machine the suite runs on."""
    return lambda root, files, project, most: {f: found for f in files if f.endswith("main.py")}


UNDEFINED = {"line": 4, "message": '"get_db_sync" is not a known attribute of module "items_api.database"'}
UNCHANGED = {"line": 3, "message": '"connect" is not a known attribute of module "items_api.database"'}


def _measured(monkeypatch, reverted):
    red = ci.Snapshot(label="latest", acceptance={"a": "failed", "b": "failed"}, acceptance_ran=True)
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "load", lambda root, which: red)
    monkeypatch.setattr(ci, "take", lambda root, label: red)
    monkeypatch.setattr(ci, "save", lambda root, snapshot: None)
    monkeypatch.setattr(ci, "commit", lambda root, message: None)
    monkeypatch.setattr(ci, "revert_to", lambda root, base: reverted.append(base) or True)


def test_a_fix_that_wrote_a_call_to_an_undefined_function_and_made_nothing_pass_is_reverted(tmp_path, monkeypatch):
    base = _a_fix(tmp_path, "from items_api import database\n\nDB = database.connect('x')\nCONN = database.get_db_sync('x')\n")
    reverted: list[str] = []
    _measured(monkeypatch, reverted)
    monkeypatch.setattr("app.analysis.language_service.underlined_in", _underlined([UNDEFINED]))

    broke = engineering.after_a_fix(str(tmp_path), base, "defect_fix_1_6", "the start script")

    assert reverted == [base]
    assert len(broke) == 1 and "get_db_sync" in broke[0] and "`items-api/items_api/main.py` line 4" in broke[0]


def test_a_clean_fix_and_a_finding_the_fix_did_not_write_are_kept(tmp_path, monkeypatch):
    base = _a_fix(tmp_path, "from items_api import database\n\nDB = database.connect('y')\nX = 1\n")
    reverted: list[str] = []
    _measured(monkeypatch, reverted)
    monkeypatch.setattr("app.analysis.language_service.underlined_in", _underlined([]))

    assert engineering.after_a_fix(str(tmp_path), base, "defect_fix_1_6", "the start script") == []
    monkeypatch.setattr("app.analysis.language_service.underlined_in", _underlined([UNCHANGED]))
    (tmp_path / "items-api" / "items_api" / "main.py").write_text(
        "from items_api import database\n\nDB = database.connect('x')\nX = 1\n")
    assert engineering.after_a_fix(str(tmp_path), base, "defect_fix_1_6", "the start script") == []
    assert reverted == []
