"""A response name last assigned from a helper is not read as the `request` fixture's response

Measured on one run: a helper held `const res = await request.post(...)` and returned `{ status, body: await res.json() }`.
A test's own `const res = await createNote(...)` kept the kind of the helper's `res`, so the right `res.body.title` was
called a fixture response read as `.body.<field>`, with a correction that would have called `.json()` on a plain object.
"""
from __future__ import annotations

from app.acceptance import suite


def _write(tmp_path, body: str):
    folder = tmp_path / "acceptance"
    folder.mkdir()
    (folder / "notes.spec.js").write_text(body, encoding="utf-8")
    return tmp_path


HELPER = """import { test, expect } from '@playwright/test';
async function createNote(request, title) {
  const res = await request.post('/notes', { data: { title } });
  return { status: res.status(), body: await res.json() };
}
"""


def _findings(monkeypatch, tmp_path, body: str) -> list[str]:
    root = _write(tmp_path, HELPER + body)
    monkeypatch.setattr(suite, "suite_files", lambda _root: [root / "acceptance" / "notes.spec.js"])
    return suite.responses_read_without_the_call(root)


def test_a_helper_s_answer_read_as_its_own_fields_is_no_finding(monkeypatch, tmp_path):
    body = """test('[AC-1] creates', async ({ request }) => {
  const res = await createNote(request, 'a');
  expect(res.status).toBe(201);
  expect(res.body.title).toBe('a');
});
"""
    assert _findings(monkeypatch, tmp_path, body) == []


def test_the_fixture_s_own_response_read_so_after_a_helper_is_still_found(monkeypatch, tmp_path):
    body = """test('[AC-1] creates', async ({ request }) => {
  const res = await createNote(request, 'a');
  expect(res.body.title).toBe('a');
});
test('[AC-2] reads', async ({ request }) => {
  const res = await request.get('/notes/1');
  expect(res.body.title).toBe('a');
});
"""
    found = _findings(monkeypatch, tmp_path, body)
    assert len(found) == 1
    assert "line(s) 12:" in found[0]


def test_the_kind_of_a_name_follows_its_last_assignment_of_any_kind():
    text = "const a = await request.get('/x');\nconst a = make();\nlet b = await fetch('/y');\nb = await request.get('/z');\n"
    assert suite._the_kind_assigned(text, "a", 3) == ""  # noqa: SLF001 - not yet assigned at that point
    assert suite._the_kind_assigned(text, "a", 34) == "request"  # noqa: SLF001
    assert suite._the_kind_assigned(text, "a", len(text)) == ""  # noqa: SLF001
    assert suite._the_kind_assigned(text, "b", len(text)) == "request"  # noqa: SLF001
