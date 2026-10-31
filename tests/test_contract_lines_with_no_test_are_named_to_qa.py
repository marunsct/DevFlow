"""A contract line no test calls is named to QA at the suite's review (plan item 16, behind `CONTRACT_LINE_COVERAGE`).

The suite was checked against the criteria only, so a route its contract promised could be called by no test. Test paths
may use helpers and parameters, so each way the kept suites call a route is checked here as counting.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app import switches
from app.acceptance import contract_coverage as cc
from app.acceptance import suite
from app.graph import acceptance_nodes
from app.observability import provenance
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _project(root, text, name="api.spec.js"):
    contract.write(root, pack_named("node-hono-native-api"), "notes", "Notes")
    where = root / "notes" / "acceptance"
    where.mkdir(parents=True, exist_ok=True)
    (where / name).write_text(text)
    return root


@pytest.mark.parametrize("line, text", [
    ("AC-1 POST /notes -> 201", "await request.post('/notes', { data: {} });"),
    ("AC-1 POST /notes -> 201", "function make(request) {\n  return request.post('/notes', { data: {} });\n}"),
    ("AC-3 GET /notes/{id} -> 200", "await request.get(`/notes/${created.id}`);"),
    ("AC-3 GET /notes/:id -> 200", "await request.get('/notes/' + id);"),
    ("AC-3 GET /notes/{id} -> 200", "await request.get('/notes/999');"),
    ("AC-3 PUT /notes/{id} -> 200", "const url = `/notes/${id}`;\n\n\n\nawait request.put(url, {});"),
    ("AC-1 POST /notes -> 201", "for (const e of [{ method: 'post', path: '/notes' }]) await request[e.method](e.path);"),
    ("AC-1 POST /notes -> 201", 'httpx.post(\n    f"{base_url}/notes",\n    json={},\n)'),
    ("AC-3 DELETE /notes/{id} -> 204", "const base = '/notes';\nawait request.delete(`${base}/${id}`);"),
    ("AC-1 GET /api/notes -> 200", "const api = '/api';\nawait request.get(`${api}/notes`);"),
    ("AC-1 GET /notes -> 200", "await fetch('/notes?limit=1');"),
])
def test_each_way_a_test_calls_a_route_counts(tmp_path, line, text):
    _project(tmp_path, text + "\nawait request.get('/health');\n")
    assert cc.lines_with_no_test(tmp_path, [line, "GET /health -> 200"]) == []


def test_a_route_or_method_no_test_calls_is_named(tmp_path):
    _project(tmp_path, "await request.post('/notes', {});\nawait request.get(`/notes/${id}`);\n")
    assert cc.lines_with_no_test(tmp_path, [
        "AC-1 POST /notes -> 201", "AC-3 GET /notes/{id} -> 200",
        "AC-4 DELETE /notes/{id} -> 204", "AC-5 GET /stats -> 200",
    ]) == ["AC-4 DELETE /notes/{id} -> 204", "AC-5 GET /stats -> 200"]


def test_a_comment_or_a_title_naming_a_route_proves_nothing(tmp_path):
    _project(tmp_path, (
        "// DELETE '/stats' is checked below\n"
        "test('[AC-5] GET /stats answers', async ({ request }) => {\n"
        "  await request.post('/notes', {});\n"
        "});\n"
    ))
    assert cc.lines_with_no_test(tmp_path, ["AC-1 POST /notes -> 201", "AC-5 GET /stats -> 200"]) == ["AC-5 GET /stats -> 200"]


def test_a_refusal_line_needs_its_status_named_somewhere(tmp_path):
    _project(tmp_path, "const r = await request.post('/signup', {});\nexpect(r.status()).toBe(201);\n")
    lines = ["AC-1 POST /signup -> 201", "AC-2 POST /signup -> 409"]
    assert cc.lines_with_no_test(tmp_path, lines) == ["AC-2 POST /signup -> 409"]
    _project(tmp_path, "const r = await request.post('/signup', {});\nexpect(r.status()).toBe(201);\nexpect(s).toBe(409);\n")
    assert cc.lines_with_no_test(tmp_path, lines) == []


def test_a_suite_that_reaches_routes_through_its_pages_is_not_named(tmp_path):
    _project(tmp_path, "await page.goto('/');\nawait page.getByRole('textbox', { name: 'Title' }).fill('a');\n")
    # None of the routes is called directly.
    assert cc.lines_with_no_test(tmp_path, ["AC-1 POST /notes -> 201", "AC-2 GET /notes -> 200"]) == []
    # A contract with page lines is reached through them: only the control is looked for.
    assert cc.lines_with_no_test(tmp_path, ['AC-1 POST /notes -> 201', 'AC-3 page / textbox "Title"']) == []
    assert cc.lines_with_no_test(tmp_path, ['AC-3 page / textbox "Body"']) == ['AC-3 page / textbox "Body"']


def test_a_command_line_needs_its_subcommand_said(tmp_path):
    _project(tmp_path, "run(['add', 'milk'])\n", "test_cli.py")
    assert cc.lines_with_no_test(tmp_path, ["AC-1 command notes add milk -> exit 0"]) == []
    assert cc.lines_with_no_test(tmp_path, ["AC-2 command notes remove milk -> exit 0"]) == ["AC-2 command notes remove milk -> exit 0"]


def _review(monkeypatch, state):
    monkeypatch.setattr(suite, "run", lambda root: SimpleNamespace(ran=False, problem="x", output="", exit_code=1))
    monkeypatch.setattr(suite, "tests_that_cannot_pass", lambda root, result: [])
    monkeypatch.setattr(suite, "vacuous_green", lambda root, result: [])
    return acceptance_nodes.acceptance_review(state, {}, SimpleNamespace())


def _state(root, **more):
    return {"repository": SimpleNamespace(root_path=str(root)), "acceptance_round": 1,
            "technical_specification": SimpleNamespace(interface_contract=["AC-1 GET /notes -> 200", "AC-2 GET /stats -> 200"]),
            **more}


def test_the_review_names_the_line_to_qa_behind_the_switch_and_not_on_a_repair(tmp_path, monkeypatch):
    _project(tmp_path, "await request.get('/notes');\n")

    monkeypatch.setenv("CONTRACT_LINE_COVERAGE", "on")
    feedback = _review(monkeypatch, _state(tmp_path))["acceptance_feedback"]
    named = [item for item in feedback if "`AC-2 GET /stats -> 200`" in item]
    assert len(named) == 1 and not BANNED.search(named[0])
    assert not any("`AC-2" in item for item in _review(monkeypatch, _state(tmp_path, acceptance_return_to="release"))["acceptance_feedback"])

    monkeypatch.setenv("CONTRACT_LINE_COVERAGE", "off")
    assert not any("`AC-2" in item for item in _review(monkeypatch, _state(tmp_path))["acceptance_feedback"])


def test_the_count_at_the_lock_is_kept_on_or_off(tmp_path, monkeypatch):
    from app.acceptance import interface_contract as ic

    _project(tmp_path, "await request.get('/notes');\n")
    ic.record_at_lock(tmp_path, ["AC-1 GET /notes -> 200", "AC-2 GET /stats -> 200"])
    monkeypatch.delenv("CONTRACT_LINE_COVERAGE", raising=False)
    assert cc.record_at_lock(tmp_path) == ["AC-2 GET /stats -> 200"]
    assert suite._state(tmp_path)["interface_contract_no_test"] == ["AC-2 GET /stats -> 200"]


def test_the_switch_is_registered_and_off(monkeypatch):
    monkeypatch.delenv("CONTRACT_LINE_COVERAGE", raising=False)
    assert "CONTRACT_LINE_COVERAGE" in switches.EXPERIMENTS and "CONTRACT_LINE_COVERAGE" not in switches.EXPERIMENTS_ON
    assert "CONTRACT_LINE_COVERAGE" in provenance.SWITCHES
    assert cc.enabled() is False
