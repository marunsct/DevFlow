"""Python stacks are told that passlib's bcrypt handler fails with bcrypt 5.

Measured on one gate run: the service declared `passlib[bcrypt]` and
`bcrypt>=4.0.0`, the install took bcrypt 5.0.0, and every hash raised
"password cannot be longer than 72 bytes" from passlib 1.7.4's own start-up
check - its last release - so the unit tests that hash a password failed.
"""
from __future__ import annotations

import re

from app.plugins.seed import SEED_INSTRUCTIONS

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_python_stacks_are_told_how_to_hash_a_password():
    row = SEED_INSTRUCTIONS["python"]
    (line,) = [line for line in row.splitlines() if line.startswith("- Password hashing")]

    assert "passlib" in line and "bcrypt` 5" in line
    assert "bcrypt.hashpw(" in line and "bcrypt.checkpw(" in line and "`bcrypt<5`" in line
    assert not BANNED.search(line)


def test_only_python_is_told():
    assert not any("passlib" in text for key, text in SEED_INSTRUCTIONS.items() if key != "python")
