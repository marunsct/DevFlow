"""A criterion defect whose test received a 5xx while the server logged nothing tells the fixer the handler hides the cause.

Measured on one run: POST answered 500, the product's error handler returned JSON without logging, and ten fix stages
changed headers and middleware around a cause none could see, each ending "its own tests still fail".
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

from app.acceptance import suite
from app.acceptance.criteria import number
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


def _the_round_s_defect(tmp_path, server_log: str):
    """The defect the round's backstop raises for AC-1, whose locked test got a 500 while the server logged `server_log`."""
    (tmp_path / ".project-directory").write_text("notes-api\n")
    (tmp_path / "notes-api" / "src" / "routes").mkdir(parents=True)
    (tmp_path / "notes-api" / "src" / "routes" / "notes.ts").write_text(ROUTE)
    suite.save_criteria(tmp_path, number("# Brief\n## Features\n- Create a note\n- List the notes\n"))
    suite.lock(tmp_path)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({
        "ran": True, "command": "npm run test:acceptance", "server_log": server_log,
        "criteria": {"AC-1": {"id": "AC-1", "text": "Create a note", "status": "failed", "tests": [
            {"name": "[AC-1] creates a note", "outcome": "failed", "message": FIVE_HUNDRED}]}}}))
    [defect] = acceptance_nodes.failing_due_defects({"repository": SimpleNamespace(root_path=str(tmp_path))}, [])
    return defect


def test_the_criterion_defect_carries_the_note_and_names_the_catch_as_its_file(tmp_path):
    defect = _the_round_s_defect(tmp_path, "")

    assert "logged nothing" in defect.actual_behavior and "`notes-api/src/routes/notes.ts` line 7" in defect.actual_behavior
    assert defect.affected_files == ["notes-api/src/routes/notes.ts"]


def test_a_criterion_defect_whose_server_logged_the_cause_names_no_catch(tmp_path):
    defect = _the_round_s_defect(tmp_path, "TypeError: x is undefined\n  at notes.ts:12")

    assert "logged nothing" not in defect.actual_behavior and defect.affected_files == []
