"""The contract's checks at the lock, its unread lines at the architect's review, non-numeric ids and a made record (plan item 17).

Measured on recent runs: `AC-health GET /health -> 200` was unread for its id; `GET /notes/{id} -> 200` was never probed
at release, having no record; unread lines surfaced only at release, when no one could still rewrite them; and the
round's probe asks only on a green suite.
"""
from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

import pytest

from app import switches
from app.acceptance import interface_contract as ic
from app.agents.specialists import SpecialistOutput
from app.graph import acceptance_nodes, workflow
from app.observability import provenance
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
NEW = ["CONTRACT_PROBE_AT_LOCK", "CONTRACT_UNREAD_LINES_AT_REVIEW", "CONTRACT_NON_NUMERIC_IDS", "CONTRACT_PROBE_WITH_A_RECORD"]


def _project(tmp_path, monkeypatch, lines, specification=None):
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(files={"playwright.config.js": ""}, probe_runner="playwright"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, lines, specification=specification)


def _reporting(tmp_path, cases):
    def run(argv, category, where):
        (tmp_path / where / "test-results").mkdir(exist_ok=True)
        (tmp_path / where / ic.REPORT_FILE).write_text(f'<testsuites><testsuite name="c">{cases}</testsuite></testsuites>')
        return {"returncode": "0"}
    return run


# --- an id that is no number

def test_a_non_numeric_id_is_read_behind_the_switch(monkeypatch):
    monkeypatch.setenv("CONTRACT_NON_NUMERIC_IDS", "off")
    assert ic.parse(["AC-health GET /health -> 200"]) == ([], ["AC-health GET /health -> 200"])

    monkeypatch.setenv("CONTRACT_NON_NUMERIC_IDS", "on")
    checks, unread = ic.parse(["AC-health GET /health -> 200", "AC-3 GET /notes -> 200", "AC-x something else"])
    assert [(c.criterion, c.method, c.path) for c in checks] == [("", "GET", "/health"), ("AC-3", "GET", "/notes")]
    assert unread == ["AC-x something else"]


# --- a record made through the contract's write line

@pytest.mark.parametrize("line, made", [
    ("AC-3 GET /notes/{id} -> 200", True),
    ("AC-4 PUT /notes/:id -> 200", True),
    ("AC-5 DELETE /notes/{id} -> 204", True),
    ("AC-3 GET /notes/{id} -> 200 or 404", False),  # the record that does not exist settles it
    ("AC-3 GET /others/{id} -> 200", False),  # no write line makes one
    ("AC-3 GET /notes/{id}/tags/{tag} -> 200", False),
    ("AC-3 GET/PUT /notes/{id} with a stale version -> 200", False),  # about another request
])
def test_which_lines_are_probed_on_a_made_record(line, made):
    checks = ic.parse(["AC-1 POST /notes -> 201", line])[0]
    found = ic.with_a_record_made_first(checks, [{"title": "a"}])
    assert bool(found) is made
    assert all(c.made_through == "/notes" for c in found)


def test_the_compiled_check_makes_the_record_then_uses_its_id():
    checks = ic.parse(["AC-1 POST /notes -> 201", "AC-4 PUT /notes/{note_id} -> 200"])[0]
    made = ic.with_a_record_made_first(checks, [{"title": "a"}])
    spec = ic.playwright_checks(made)
    assert 'method: \'POST\'' in spec and '[{"title": "a"}]' in spec and "...bodies, {}" in spec
    assert 'record["note_id"] ?? record.id' in spec
    assert '"/notes/" + encodeURIComponent(id) + ""' in spec
    assert "data: bodies[0]" in spec
    assert "test.skip(!made.ok()" in spec
    get_only = ic.with_a_record_made_first(ic.parse(["AC-1 POST /notes -> 201", "AC-3 GET /notes/{id} -> 200"])[0], [])
    assert "data: bodies[0]" not in ic.playwright_checks(get_only)


LINES = ["AC-1 POST /notes -> 201", "AC-3 GET /notes/{id} -> 200"]


def test_at_release_off_the_line_stays_unchecked(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTRACT_PROBE_WITH_A_RECORD", "off")
    _project(tmp_path, monkeypatch, LINES)
    gaps = ic.what_the_contract_checks_find(tmp_path, runner=_reporting(tmp_path, ""))
    assert any("AC-3 GET /notes/{id} -> 200 (a route with a parameter in it)" in gap for gap in gaps)


def test_at_release_on_a_made_record_that_fails_is_a_gap(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTRACT_PROBE_WITH_A_RECORD", "on")
    _project(tmp_path, monkeypatch, LINES)
    case = '<testcase name="[AC-3] contract 1: AC-3 GET /notes/{id} -&gt; 200"><failure message="x">Expected: 200\nReceived: 404</failure></testcase>'
    gaps = ic.what_the_contract_checks_find(tmp_path, runner=_reporting(tmp_path, case))
    assert any("does not keep its interface contract" in gap and "AC-3" in gap for gap in gaps)
    assert not any("AC-3 GET /notes/{id} -> 200 (a route" in gap for gap in gaps)


def test_at_release_on_no_record_made_is_said_to_be_unchecked(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTRACT_PROBE_WITH_A_RECORD", "on")
    _project(tmp_path, monkeypatch, LINES)
    case = '<testcase name="[AC-3] contract 1: AC-3 GET /notes/{id} -&gt; 200"><skipped/></testcase>'
    gaps = ic.what_the_contract_checks_find(tmp_path, runner=_reporting(tmp_path, case))
    assert any(f"AC-3 GET /notes/{{id}} -> 200 ({ic.MADE_NO_RECORD})" in gap for gap in gaps)


def test_the_bodies_come_from_the_specification_s_literal_examples(tmp_path, monkeypatch):
    specification = SimpleNamespace(
        data_contracts=['Note: id int, title str. Example: {"id": 1, "title": "a"}', 'Create request: {"title": "b"}', "no example {here}"],
        api_and_event_contracts=[],
    )
    assert ic.example_bodies(specification) == [{"title": "b"}, {"id": 1, "title": "a"}]
    assert ic.example_bodies(None) == []
    _project(tmp_path, monkeypatch, LINES, specification)
    from app.acceptance import suite

    assert suite._state(tmp_path)["interface_contract_bodies"] == [{"title": "b"}, {"id": 1, "title": "a"}]


# --- the probe at the lock

GOT_500 = '<testcase name="[AC-2] contract 1: AC-2 PUT /notes/:id -&gt; 404"><failure message="x">Expected: 404\nReceived: 500</failure></testcase>'


def test_the_lock_s_probe_keeps_a_5xx_behind_the_switch_and_the_next_round_raises_it_once(tmp_path, monkeypatch):
    from app.stacks import scaffold

    monkeypatch.setattr(scaffold, "entrypoint_is_still_the_stub", lambda root: None)
    _project(tmp_path, monkeypatch, ["AC-2 PUT /notes/:id -> 404"])
    runner = _reporting(tmp_path, GOT_500)

    monkeypatch.setenv("CONTRACT_PROBE_AT_LOCK", "off")
    assert ic.probe_at_the_lock(tmp_path, runner=runner) == []
    assert ic.errors_found_at_the_lock(tmp_path) == []

    monkeypatch.setenv("CONTRACT_PROBE_AT_LOCK", "on")
    assert [status for _, status in ic.probe_at_the_lock(tmp_path, runner=runner)] == [500]

    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    red = SpecialistOutput(changed_files=[], defects=[], decisions=[])
    milestone = SimpleNamespace(delegated_tasks=[], milestone_scope=[])
    raised = workflow._with_the_lock_s_server_errors(state, red, milestone).defects
    assert len(raised) == 1 and raised[0].description.startswith(ic.SERVER_FAILED)
    assert "answered 500" in raised[0].description and not BANNED.search(raised[0].description)
    assert workflow._with_the_lock_s_server_errors(state, red, milestone).defects == []


def test_the_scaffold_s_stub_is_no_product_to_probe(tmp_path, monkeypatch):
    from app.stacks import scaffold

    monkeypatch.setattr(scaffold, "entrypoint_is_still_the_stub", lambda root: "app/main.ts")
    _project(tmp_path, monkeypatch, ["AC-2 PUT /notes/:id -> 404"])
    monkeypatch.setenv("CONTRACT_PROBE_AT_LOCK", "on")
    def never(*_):
        raise AssertionError("the probe ran against the stub")
    assert ic.probe_at_the_lock(tmp_path, runner=never) == []


def test_the_review_and_the_round_ask_it():
    assert "probe_at_the_lock(root)" in inspect.getsource(acceptance_nodes.acceptance_review)
    assert "_with_the_lock_s_server_errors(state, test_result, milestone)" in inspect.getsource(workflow)


# --- unread lines at the architect's review

def _spec_state(lines, **more):
    return {"technical_specification": SimpleNamespace(interface_contract=lines), **more}


def test_unread_lines_are_put_to_the_architect_s_review_behind_the_switch(monkeypatch):
    lines = ["AC-1 GET /notes -> 200", "AC-2 the list is sorted"]
    monkeypatch.setenv("CONTRACT_UNREAD_LINES_AT_REVIEW", "off")
    assert workflow._contract_lines_nothing_can_read(_spec_state(lines)) is None

    monkeypatch.setenv("CONTRACT_UNREAD_LINES_AT_REVIEW", "on")
    found = workflow._contract_lines_nothing_can_read(_spec_state(lines))
    assert found.severity == "major" and "`AC-2 the list is sorted`" in found.description
    assert "AC-1 GET" not in found.description
    assert not BANNED.search(found.description + found.required_remediation + found.evidence)

    assert workflow._contract_lines_nothing_can_read(_spec_state(lines[:1])) is None
    assert workflow._contract_lines_nothing_can_read(_spec_state(lines, specification_contract_lines_checked=True)) is None
    spent = workflow.MAX_ARCHITECTURE_REVISIONS - 1
    assert workflow._contract_lines_nothing_can_read(_spec_state(lines, architecture_revision_count=spent)) is None


def test_the_review_node_asks_it():
    assert "update[\"specification_contract_lines_checked\"] = True" in inspect.getsource(workflow)


def test_the_switches_are_registered_and_off(monkeypatch):
    for name in NEW:
        monkeypatch.delenv(name, raising=False)
        assert name in switches.EXPERIMENTS and name not in switches.EXPERIMENTS_ON
        assert name in provenance.SWITCHES
        assert provenance.switch(provenance.SWITCHES[name]).enabled() is False
