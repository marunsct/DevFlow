"""A setup whose install failed says why, from the line that names the error (measured live).

One run's custom setup declared `pip install -e .`; the harness's proof of it
failed on "Multiple top-level packages discovered in a flat-layout", and the
record kept the output's last 800 characters, which began "...covery." and went
on through pip's closing advice. The setup was left to the agents with no cause
anyone could act on. Python setups are also told, through the seed, how such an
install has to name what it installs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.plugins.seed import SEED_INSTRUCTIONS
from app.stacks import custom_setup
from app.stacks.scaffold import where_it_failed

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

PIP = "\n".join([
    "Obtaining file:///workspace/bookmarks",
    "  Installing build dependencies: started",
    "  Getting requirements to build editable: finished with status 'error'",
    "  error: subprocess-exited-with-error",
    "  × Getting requirements to build editable did not run successfully.",
    "  error: Multiple top-level packages discovered in a flat-layout: ['data', 'acceptance', 'node_modules'].",
    *[f"  advice line {n} about package discovery and the options setuptools offers" for n in range(14)],
    "  [end of output]",
    "  note: This error originates from a subprocess, and is likely not a problem with pip.",
    "error: subprocess-exited-with-error",
])


def test_the_excerpt_keeps_the_line_that_names_the_cause():
    excerpt = where_it_failed(PIP)

    assert "Multiple top-level packages discovered in a flat-layout" in excerpt
    assert "likely not a problem with pip" in excerpt


def test_the_proof_records_the_cause(tmp_path):
    project = tmp_path / "bookmarks"
    project.mkdir()
    (project / custom_setup.DECLARATION_FILE).write_text(json.dumps({
        "kind": "http_api", "install": [[".venv/bin/pip", "install", "-e", "."]],
        "unit_test": ["pytest"], "unit_report": "unit.xml", "unit_dir": "tests/unit", "unit_pattern": "test_*.py",
        "acceptance_test": ["pytest", "acceptance"], "acceptance_report": "acc.xml",
        "acceptance_dir": "acceptance", "acceptance_pattern": "test_*.py",
        "smoke_files": ["tests/unit/test_smoke.py", "acceptance/test_smoke.py"],
    }))
    for name in ("tests/unit/test_smoke.py", "acceptance/test_smoke.py"):
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).write_text("def test_x():\n    pass\n")

    result = custom_setup.prove(tmp_path, "bookmarks", {"language": "Python"},
                                run=lambda argv, category, where: {"stdout": PIP, "returncode": "1"})

    assert not result.ok
    assert "Multiple top-level packages discovered in a flat-layout" in result.problem


def test_a_python_setup_is_told_how_an_install_names_what_it_installs():
    for key in ("python:setup", "fastapi:setup"):
        text = SEED_INSTRUCTIONS[key]
        assert "flat-layout" in text and "py-modules" in text
        assert not BANNED.search(text)
