"""Every stage that writes code is told which manifests the project's install reads.

"Add dependencies the normal way" left a Python project's stages to choose
between `requirements.txt` and `pyproject.toml`; on five gate runs in a row
drafting chose the file the install never read.
"""
from __future__ import annotations

import re

from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_requirement_files_the_install_reads_are_named():
    record = {"install": [["python3", "-m", "venv", ".venv"],
                          [".venv/bin/python", "-m", "pip", "install", "-r", "requirements.txt", "-r", "requirements-dev.txt"]]}
    text = contract._where_dependencies_go("items-api", record)
    assert "`items-api/requirements.txt` and `items-api/requirements-dev.txt`" in text
    assert "pyproject.toml" in text and "never installed" in text
    assert not BANNED.search(text)


def test_another_install_names_its_command_and_none_names_the_manifest():
    assert "`npm install`" in contract._where_dependencies_go("app", {"install": [["npm", "install"]]})
    assert "project's manifest" in contract._where_dependencies_go("app", {})


def test_every_drafted_file_is_told_too(tmp_path):
    import json
    from types import SimpleNamespace

    from app.graph import drafting

    (tmp_path / contract.CONTRACT_FILE).parent.mkdir(parents=True)
    (tmp_path / contract.CONTRACT_FILE).write_text(json.dumps({"pack": "python-http-api", "project": "items-api",
        "install": [[".venv/bin/python", "-m", "pip", "install", "-r", "requirements.txt"]]}))
    request = drafting.draft_request(tmp_path, "items-api/pyproject.toml", SimpleNamespace(task_description="Set up"), None, None)
    assert "--- Where this project's dependencies go ---" in request and "`items-api/requirements.txt`" in request


def test_a_mixed_install_names_the_javascript_manifest_too():
    from app.stacks import contract as _contract

    record = {"install": [["pip", "install", "-r", "requirements.txt"], ["npm", "install"]]}
    text = _contract._where_dependencies_go("shop", record)
    assert "`shop/requirements.txt`" in text and "`package.json`" in text and "Python package" in text
    assert "package.json" not in _contract._where_dependencies_go("shop", {"install": [["pip", "install", "-r", "requirements.txt"]]})
