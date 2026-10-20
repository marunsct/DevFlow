"""Python that parses but cannot compile is refused at the write, like any other syntax error.

Measured live: a work order rewrote a test file with `await` inside a plain
`def`. `ast.parse` accepts that - the error is raised by the compiler's later
pass - so the write went through without a word, and every test in the file
failed to collect in the next round.
"""
from __future__ import annotations

import re

import pytest

from app.analysis.syntax_balance import structural_problem

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.mark.parametrize("body", [
    "def test_lookup(db_session):\n    result = await db_session.execute(1)\n",
    "return 1\n",
    "def loop():\n    break\n",
])
def test_it_is_refused_with_its_line(body):
    problem = structural_problem("tests/test_items.py", body)

    assert problem and problem.startswith("Python cannot parse this file on line")
    assert not BANNED.search(problem)


def test_code_that_compiles_is_left_alone():
    assert structural_problem("tests/test_items.py", "async def test_lookup(db):\n    await db.execute(1)\n") is None
