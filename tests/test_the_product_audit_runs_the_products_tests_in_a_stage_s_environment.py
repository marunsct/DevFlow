"""The product audit runs the product's tests as a stage would (measured live).

`loop.sh product` runs the product's test command inside the worker, which holds
the harness's own settings. A generated service that reads a variable of the same
name - an empty CORS list failed its settings parse, a signing secret made a
service start that the run's own commands could not start - was measured with the
harness's values, so the audit reported failures and passes the run never had.
"""
from __future__ import annotations

import glob
import json
import runpy
import stat
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "product_audit.py"


def test_the_harness_s_variables_do_not_reach_the_product_s_tests(tmp_path, monkeypatch, capsys):
    workspace = tmp_path / "workspace-run-x"
    project = workspace / "app"
    project.mkdir(parents=True)
    (workspace / ".project-directory").write_text("app")
    (project / "package.json").write_text(json.dumps({"scripts": {"test": "x"}}))
    fake = tmp_path / "bin"
    fake.mkdir()
    npm = fake / "npm"
    npm.write_text('#!/bin/sh\necho "tests failed: signing secret=[$HARNESS_SECRET] origins=[$ALLOWED_ORIGINS]"\n')
    npm.chmod(npm.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{fake}:/usr/bin:/bin")
    monkeypatch.setenv("HARNESS_SECRET", "leaked")
    monkeypatch.setenv("ALLOWED_ORIGINS", "")
    monkeypatch.setattr(glob, "glob", lambda pattern: [str(workspace)])
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "run-x"])

    try:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    except SystemExit:
        pass

    shown = capsys.readouterr().out
    assert "signing secret=[]" in shown
    assert "leaked" not in shown
