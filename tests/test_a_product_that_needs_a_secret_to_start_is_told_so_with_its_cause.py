"""A product that cannot start says why, from the end of its traceback (measured live).

A service needed `jwt_secret_key` and the suite sets only `PORT` and `DATA_DIR`,
so it crashed at import. The defect showed the first six lines of the
traceback - uvicorn's own frames - and not the cause on the last line, so
fixers could not see it; and the model's `export JWT_SECRET_KEY=... &&` attempts
were it trying to supply the value by hand.
"""
from __future__ import annotations

import re

from app.acceptance import suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

FRAMES = "".join(f'[WebServer]   File "/venv/lib/python3.12/site-packages/x{n}.py", line {n}, in f{n}\n' for n in range(30))
OUTPUT = (
    "Error: Process from config.webServer was not able to start. Exit code: 1\n"
    "[WebServer] Traceback (most recent call last):\n" + FRAMES +
    "[WebServer] pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings\n"
    "[WebServer] jwt_secret_key\n"
    "[WebServer]   Field required [type=missing, input_value={'data_dir': 'x'}, input_type=dict]\n"
)


def test_the_cause_at_the_end_of_the_traceback_is_in_the_problem():
    problem = suite.the_product_did_not_start(OUTPUT)

    assert problem.startswith(suite.PRODUCT_DID_NOT_START)
    assert "jwt_secret_key" in problem and "Field required" in problem
    assert len(problem) < 2500


def test_a_missing_setting_gets_the_hint_and_other_failures_do_not():
    assert "sets only `PORT` and `DATA_DIR`" in suite.the_product_did_not_start(OUTPUT)
    other = suite.the_product_did_not_start(
        "Error: Process from config.webServer was not able to start. Exit code: 1\n[WebServer] SyntaxError: invalid syntax\n"
    )
    assert other and "sets only" not in other


def test_the_hint_uses_none_of_the_banned_words():
    assert not BANNED.search(suite.the_product_did_not_start(OUTPUT))


def test_a_start_that_did_not_fail_is_not_reported():
    assert suite.the_product_did_not_start("3 passed") == ""
