"""A shell builtin is refused with why, beside the list of programs (measured live).

`export JWT_SECRET_KEY=... && npm run test:acceptance` was refused with "'export'
is not permitted for role ..." and a list of allowed programs - which does not
say that there is no shell, so nothing set in one command reaches the next. The
model tried again in other shapes.
"""
from __future__ import annotations

import re

import pytest

from app.tools.sandbox import CommandNotAllowed, validate_command

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.mark.parametrize("builtin", ["export", "set", "source", "unset"])
def test_a_builtin_is_refused_with_the_reason(builtin, tmp_path):
    with pytest.raises(CommandNotAllowed) as refused:
        validate_command([builtin, "JWT_SECRET_KEY=x", "&&", "npm", "test"], "testing_specialist", tmp_path)

    said = str(refused.value)
    assert "shell builtin" in said and "no shell here" in said
    assert not BANNED.search(said)


def test_export_names_where_a_value_belongs(tmp_path):
    with pytest.raises(CommandNotAllowed) as refused:
        validate_command(["export", "X=1"], "testing_specialist", tmp_path)

    assert "`PORT` and `DATA_DIR`" in str(refused.value) and "project's own configuration" in str(refused.value)
