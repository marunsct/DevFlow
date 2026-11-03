"""A role that may run Python but not `pip` is told to run pip through Python, not to run `pip install`."""
from __future__ import annotations

import re

import pytest

from app.tools.sandbox import CommandNotAllowed, allowed_executables, validate_command

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.mark.parametrize("program", [".venv/bin/pip", "pip", "pip3"])
def test_the_refusal_names_python_dash_m_pip(tmp_path, program):
    role = "testing_specialist"
    if "pip" in allowed_executables(role, tmp_path) or "python" not in allowed_executables(role, tmp_path):
        pytest.skip("this role's allowlist no longer refuses pip while allowing python")
    with pytest.raises(CommandNotAllowed) as caught:
        validate_command([program, "install", "-r", "requirements.txt"], role, tmp_path)
    said = str(caught.value)
    assert "-m pip install" in said
    assert not BANNED.search(said)
