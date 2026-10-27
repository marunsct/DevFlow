"""A failing criterion's defect carries what the product's server logged while the suite ran: its error and its frames.

Measured on one run: `POST /notes` answered 500, every test that created a note failed on `res.json()` of "Internal
Server Error", and the server had logged `Error: Internal server error at NotesRepository.save
(src/services/persistence.ts:44)` - in the suite's output, under Playwright's `[WebServer]` prefix - and no fixer was
shown it: five fixers in a row changed nothing or chased the tests.
"""
from __future__ import annotations

import inspect

from app.graph import acceptance_nodes

OUTPUT = """Running 15 tests using 1 worker
[WebServer] Listening on http://127.0.0.1:23011
[WebServer] Error: Internal server error
[WebServer]     at NotesRepository.save (file://notes-api/src/services/persistence.ts:44:13)
[WebServer]     at NotesRepository.create (file://notes-api/src/services/persistence.ts:30:5)
[WebServer]     at Array.<anonymous> (file://notes-api/src/routes/notes.ts:31:27)
[WebServer]     at #dispatch (file://notes-api/node_modules/hono/dist/hono-base.js:276:34)
[WebServer]     at async node:internal/modules/esm/loader:647:26
  1) [AC-1] creates a note
"""


def test_the_server_s_error_and_its_frames_in_the_product_are_kept():
    logged = acceptance_nodes.what_the_server_logged(OUTPUT)

    assert "Error: Internal server error" in logged
    assert "persistence.ts:44" in logged and "notes.ts:31" in logged
    assert "node_modules" not in logged and "node:internal" not in logged
    assert "Listening on" not in logged


def test_nothing_logged_is_nothing_said():
    assert acceptance_nodes.what_the_server_logged("Running 15 tests\n  1) [AC-1] x\n") == ""


def test_each_failing_criterion_s_defect_carries_it():
    source = inspect.getsource(acceptance_nodes.failing_due_defects)
    assert "what_the_server_logged(" in source


def test_an_error_the_product_put_in_place_of_the_one_it_caught_is_named(tmp_path):
    """Measured on the same run: the logged frame was `throw new Error('Internal server error')` inside `catch (_)`;
    the real cause - the folder the write needed did not exist - was thrown away, and the fixers saw only the
    replacement."""
    project = tmp_path / "notes-api"
    (project / "src" / "services").mkdir(parents=True)
    (project / "src" / "services" / "persistence.ts").write_text(
        "export class R {\n  save(notes) {\n    try {\n      write(notes);\n    } catch (_) {\n"
        "      throw new Error('Internal server error');\n    }\n  }\n}\n")
    logged = ("Error: Internal server error\n"
              "    at R.save (file://notes-api/src/services/persistence.ts:6:13)")

    said = acceptance_nodes.what_the_logged_frames_hide(tmp_path, logged)

    assert "notes-api/src/services/persistence.ts" in said and "line 6" in said
    assert "throws its own error in place of the one it caught" in said


def test_a_frame_on_an_ordinary_line_says_nothing(tmp_path):
    project = tmp_path / "notes-api" / "src"
    project.mkdir(parents=True)
    (project / "app.ts").write_text("export function f() {\n  return g();\n}\n")

    assert acceptance_nodes.what_the_logged_frames_hide(tmp_path, "Error: x\n    at f (file://notes-api/src/app.ts:2:3)") == ""
