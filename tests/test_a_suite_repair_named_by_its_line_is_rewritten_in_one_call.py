"""A locked test named by its file and line is rewritten in one call, as one named by its title is.

Measured on one run: a check named `notes.spec.js` line 142 (a content type asserted on a 204). The one-call rewrite
took the finding's first quoted name - the file - as the test's title, could not place it, and the repair went to QA's
whole agent loop: about 20 minutes, twice, for one line.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import acceptance_nodes

SPEC = (
    "import { test, expect } from '@playwright/test';\n\n"
    "test('[AC-1] create a note', async ({ request }) => {\n  expect(1).toBe(1);\n});\n\n"
    "test('[AC-5] delete a note', async ({ request }) => {\n"
    "  const gone = await request.delete('/notes/1');\n"
    "  expect(gone.headers()['content-type']).toContain('json');\n"
    "});\n"
)


def test_the_test_at_the_named_line_is_the_one_rewritten(tmp_path, monkeypatch):
    (tmp_path / ".project-directory").write_text("notes\n")
    (tmp_path / "notes" / "acceptance").mkdir(parents=True)
    (tmp_path / "notes" / "acceptance" / "notes.spec.js").write_text(SPEC)
    finding = ("`notes/acceptance/notes.spec.js` line(s) 9: a test asserts a JSON content type on a DELETE the "
               "interface contract answers with 204")
    named = []

    def repair(root, findings, model, *, which_test, **kwargs):  # the rewrite's model call is the edge
        named.extend(which_test(f) for f in findings)
        return ["[AC-5] delete a note"]

    monkeypatch.setattr("app.graph.rewritten_tests.repair", repair)
    monkeypatch.setenv("NAMED_TEST_REWRITE", "on")
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}

    assert acceptance_nodes._rewritten_in_one_call_each(state, [finding], model=object())
    assert named == ["[AC-5] delete a note"]
