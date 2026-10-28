"""A criterion defect whose test received a 5xx while the server logged nothing tells the fixer the handler hides the cause.

Measured on one run: POST answered 500, the product's error handler returned JSON without logging, and ten fix stages
changed headers and middleware around a cause none could see, each ending "its own tests still fail".
"""
from __future__ import annotations

import inspect
import re

from app.graph import acceptance_nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
FIVE_HUNDRED = "expect(received).toBe(expected)\n\n    Expected: 201\n    Received: 500\n"


def test_a_5xx_with_an_empty_server_log_adds_the_note():
    note = acceptance_nodes.the_server_hid_the_cause([FIVE_HUNDRED], "")
    assert "logged nothing" in note and "standard error" in note
    assert not BANNED.search(note)


def test_a_logged_5xx_or_a_non_5xx_failure_adds_nothing():
    assert acceptance_nodes.the_server_hid_the_cause([FIVE_HUNDRED], "TypeError: x is undefined\n  at notes.ts:12") == ""
    assert acceptance_nodes.the_server_hid_the_cause(["Expected: 201\n    Received: 400\n"], "") == ""


def test_the_criterion_defect_carries_it():
    source = inspect.getsource(acceptance_nodes.failing_due_defects)
    assert "the_server_hid_the_cause([t.get(\"message\") or \"\" for t in failed], logged, _root(state))" in source


ROUTE = """import { Hono } from 'hono';
export const r = new Hono();
r.post('/', async (c) => {
  try {
    return c.json(await create(await c.req.json()), 201);
  } catch (e) {
    return c.json({ error: 'Internal Server Error' }, 500);
  }
});
r.get('/', async (c) => {
  try {
    return c.json(await list());
  } catch (e) {
    console.error(e);
    return c.json({ error: 'Internal Server Error' }, 500);
  }
});
"""


def test_the_note_names_the_catch_that_answers_5xx_without_logging(tmp_path):
    """Measured on one run: told only that the handler hid the cause, the next fixers rewrote other files and the
    log stayed empty."""
    (tmp_path / "notes-api" / "src" / "routes").mkdir(parents=True)
    (tmp_path / "notes-api" / "src" / "routes" / "notes.ts").write_text(ROUTE)
    assert acceptance_nodes.where_errors_become_5xx(tmp_path) == [("notes-api/src/routes/notes.ts", 7)]
    note = acceptance_nodes.the_server_hid_the_cause([FIVE_HUNDRED], "", tmp_path)
    assert "`notes-api/src/routes/notes.ts` line 7" in note and "line 15" not in note
    assert "affected_files=sorted({f for f, _ in where_errors_become_5xx(_root(state))}) if hid else []" in inspect.getsource(
        acceptance_nodes.failing_due_defects)
