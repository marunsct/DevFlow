"""Each write line of the contract is sent a body nothing can parse; a 5xx is a defect, any other answer the product's to choose.

Behind `CONTRACT_PROBE_WITH_A_BAD_BODY`. Measured on one product: unparsable JSON on a write route answered 500, the locked
suite did not ask, and a hidden quality test found it. The compiled probe is only read here, never run.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import switches
from app.acceptance import interface_contract as ic
from app.acceptance import suite
from app.agents.specialists import SpecialistOutput
from app.graph import acceptance_nodes, workflow
from app.observability import provenance
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LINES = ["AC-1 POST /notes -> 201", "AC-2 PUT /notes/{id} -> 200 or 404", "AC-3 GET /notes -> 200",
         "AC-4 POST /notes -> 400", "AC-5 PATCH /others/{id} -> 200", "AC-6 PUT /a/{x}/b/{y} -> 200"]


def _case(number, line, body):
    escaped = line.replace(">", "&gt;")
    return f'<testcase name="[{line.split()[0]}] contract {number}: {escaped}">{body}</testcase>'


GOT_500 = '<failure message="x">Expected: &lt; 500\nReceived: 500</failure>'
GOT_NOTHING = '<failure message="x">apiRequestContext.fetch: socket hang up</failure>'


class Probe:
    """Stands in for the probe's runner: reads the compiled spec it was given and writes a report. Nothing is run."""

    def __init__(self, root, bad_body_report="", bare_report=""):
        self.root, self.bad_body_report, self.bare_report = root, bad_body_report, bare_report
        self.specs = []

    def __call__(self, argv, category, where):
        spec = (self.root / where / ic.CHECK_DIR / "contract.spec.js").read_text()
        self.specs.append(spec)
        cases = self.bad_body_report if ic_is_bad_body(spec) else self.bare_report
        (self.root / where / "test-results").mkdir(exist_ok=True)
        (self.root / where / ic.REPORT_FILE).write_text(f'<testsuites><testsuite name="c">{cases}</testsuite></testsuites>')
        return {"returncode": "0"}


def ic_is_bad_body(spec):
    return "'content-type': 'application/json'" in spec


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTRACT_PROBE_WITH_A_BAD_BODY", "on")
    monkeypatch.setenv("CONTRACT_SERVER_ERRORS_AT_A_ROUND", "on")  # always on in the product; conftest turns the built-ins off
    monkeypatch.setattr(contract, "the_pack", lambda root: (
        SimpleNamespace(files={"playwright.config.js": ""}, probe_runner="playwright"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, LINES, specification=SimpleNamespace(
        data_contracts=['Create request: {"title": "a"}'], api_and_event_contracts=[]))
    return tmp_path


def _round(root, monkeypatch, probe):
    monkeypatch.setattr(acceptance_nodes.suite, "is_locked", lambda _: True)
    monkeypatch.setattr(suite, "_sandbox_runner", lambda _: probe)
    state = {"repository": SimpleNamespace(root_path=str(root))}
    milestone = SimpleNamespace(delegated_tasks=[], milestone_scope=[])
    return workflow._with_the_contract_s_server_errors(state, SpecialistOutput(changed_files=[], defects=[], decisions=[]), milestone)


# The probe's order: POST /notes, PUT /notes/{id} (on a made record). The others are not asked.
A_500_ON_THE_POST = _case(1, "AC-1 POST /notes -> 201", GOT_500) + _case(2, "AC-2 PUT /notes/{id} -> 200 or 404", "")


def test_a_5xx_at_a_green_round_is_raised_as_a_defect_saying_what_was_sent(project, monkeypatch):
    probe = Probe(project, A_500_ON_THE_POST)
    raised = _round(project, monkeypatch, probe).defects
    assert len(raised) == 1
    defect = raised[0]
    assert defect.description.startswith(ic.SERVER_FAILED)
    assert "`POST /notes` sent with a JSON body that cannot be parsed answered 500" in defect.description
    assert "`PUT /notes" not in defect.description
    assert ic.A_BODY_NOTHING_CAN_PARSE in defect.reproduction_steps
    assert "`POST /notes` answered 500" in defect.actual_behavior
    for said in (defect.description, defect.reproduction_steps, defect.expected_behavior, defect.actual_behavior,
                 ic.bad_body_switch.explanation, ic.SIGN_IN_ANSWERED_FIRST):
        assert not BANNED.search(said)


def test_a_bare_probe_s_5xx_and_a_bad_body_s_are_one_defect_naming_both(project, monkeypatch):
    bare = _case(1, "AC-2 PUT /notes/{id} -> 200 or 404", GOT_500)
    raised = _round(project, monkeypatch, Probe(project, A_500_ON_THE_POST, bare)).defects
    assert len(raised) == 1
    assert f"`PUT /notes/{ic.A_RECORD_THAT_DOES_NOT_EXIST}` sent with no body answered 500" in raised[0].description
    assert "`POST /notes` sent with a JSON body that cannot be parsed answered 500" in raised[0].description


def test_any_answer_under_500_passes(project, monkeypatch):
    passing = _case(1, "AC-1 POST /notes -> 201", "") + _case(2, "AC-2 PUT /notes/{id} -> 200 or 404", "")
    probe = Probe(project, passing)
    assert _round(project, monkeypatch, probe).defects == []
    assert any(ic_is_bad_body(spec) for spec in probe.specs)
    assert "toBeLessThan(500)" in next(spec for spec in probe.specs if ic_is_bad_body(spec))


def test_off_nothing_is_sent(project, monkeypatch):
    monkeypatch.setenv("CONTRACT_PROBE_WITH_A_BAD_BODY", "off")
    probe = Probe(project, A_500_ON_THE_POST)
    assert _round(project, monkeypatch, probe).defects == []
    assert not any(ic_is_bad_body(spec) for spec in probe.specs)
    assert ic.what_the_bad_body_probe_did_not_ask(project) == []


def test_the_defect_is_settled_by_asking_the_same_request_again(project, monkeypatch):
    probe = Probe(project, A_500_ON_THE_POST)
    description = _round(project, monkeypatch, probe).defects[0].description
    assert ic.still_raised(project, description, runner=probe) is True
    probe.bad_body_report = _case(1, "AC-1 POST /notes -> 201", "")
    assert ic.still_raised(project, description, runner=probe) is False


def test_a_defect_of_a_bare_request_is_not_kept_open_by_the_bad_body_probe(project):
    # Only the bare probe is asked: the POST still fails on a bad body, and that says nothing of this defect.
    probe = Probe(project, A_500_ON_THE_POST)
    bare = f"{ic.SERVER_FAILED} `POST /notes` sent with no body answered 500 where the contract gives 201."
    assert ic.still_raised(project, bare, runner=probe) is False
    assert not any(ic_is_bad_body(spec) for spec in probe.specs)


def test_a_defect_it_raised_stays_settled_when_the_switch_is_turned_off(project, monkeypatch):
    probe = Probe(project, A_500_ON_THE_POST)
    description = _round(project, monkeypatch, probe).defects[0].description
    monkeypatch.setenv("CONTRACT_PROBE_WITH_A_BAD_BODY", "off")
    assert ic.still_raised(project, description, runner=probe) is False


def test_each_call_is_asked_once_and_a_route_with_a_parameter_on_a_made_record():
    checks = ic.parse(LINES)[0]
    asked, unchecked = ic.bad_body_checks(checks, [{"title": "a"}])
    assert [(c.method, c.path, c.made_through) for c in asked] == [("POST", "/notes", ""), ("PUT", "/notes/{id}", "/notes")]
    assert len(unchecked) == 2
    assert all("no write line of the contract makes its record" in line for line in unchecked)
    assert "AC-5 PATCH /others/{id}" in unchecked[0] and "AC-6 PUT /a/{x}/b/{y}" in unchecked[1]


def test_a_write_line_with_a_refusal_it_allows_still_needs_its_record():
    # A bare probe of `/notes/999999999` is settled by its 404, but a 404 comes before any body is read.
    asked, _ = ic.bad_body_checks(ic.parse(["AC-1 POST /notes -> 201", "AC-2 PUT /notes/:id -> 404"])[0], [])
    assert asked[1].made_through == "/notes"


def test_the_compiled_probe_sends_unparsable_json_and_reads_only_status():
    # Text only: the compiled probe is never run against anything here.
    asked, _ = ic.bad_body_checks(ic.parse(LINES)[0], [{"title": "a"}])
    spec = ic.playwright_bad_body_checks(asked)
    assert "contract 1: AC-1 POST /notes -> 201" in spec and "contract 2: AC-2 PUT /notes/{id} -> 200 or 404" in spec
    assert spec.count("headers: { 'content-type': 'application/json' }") == 2
    assert 'data: "{\\"unparsable\\": "' in spec
    assert spec.count("expect(answer.status()).toBeLessThan(500)") == 2
    assert spec.count("test.skip([401, 403].includes(answer.status())") == 2
    # The PUT reaches the record the POST made; the POST itself makes none.
    assert spec.count("method: 'POST', data, failOnStatusCode: false") == 1
    assert '"/notes/" + encodeURIComponent(id) + ""' in spec
    assert '[{"title": "a"}]' in spec


def test_the_body_cannot_be_parsed():
    import json

    with pytest.raises(json.JSONDecodeError):
        json.loads(ic.A_BODY_NOTHING_CAN_PARSE)


def test_the_probe_s_report_is_read_with_the_message_a_less_than_check_prints():
    test = SimpleNamespace(message="Error: expect(received).toBeLessThan(expected)\n\nExpected: < 500\nReceived:   503\n")
    assert ic._a_server_error(test) == 503


def test_what_sign_in_stopped_and_what_could_not_be_asked_are_said_at_release(project, monkeypatch):
    skipped = _case(1, "AC-1 POST /notes -> 201", "<skipped/>") + _case(2, "AC-2 PUT /notes/{id} -> 200 or 404", "<skipped/>")
    probe = Probe(project, skipped)
    assert _round(project, monkeypatch, probe).defects == []
    gap = ic.what_the_bad_body_probe_did_not_ask(project)[0]
    assert "4 write line(s)" in gap and "not asked with an unparsable body" in gap
    assert f"AC-1 POST /notes -> 201 ({ic.SIGN_IN_ANSWERED_FIRST})" in gap
    assert f"AC-2 PUT /notes/{{id}} -> 200 or 404 ({ic.MADE_NO_RECORD}, or {ic.SIGN_IN_ANSWERED_FIRST})" in gap
    assert "AC-5 PATCH /others/{id}" in gap
    gaps = ic.what_the_contract_checks_find(project, runner=probe)
    assert gap in gaps
    assert not BANNED.search(gap)


def test_a_probe_that_got_no_status_is_said_unchecked_and_raises_nothing(project, monkeypatch):
    probe = Probe(project, _case(1, "AC-1 POST /notes -> 201", GOT_NOTHING))
    assert _round(project, monkeypatch, probe).defects == []
    assert "AC-1 POST /notes -> 201 (the probe got no status back)" in ic.what_the_bad_body_probe_did_not_ask(project)[0]


def test_a_stack_with_no_probe_runner_says_so(project, monkeypatch):
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(files={}, probe_runner=""), {"project": "app"}))
    assert ic.bad_body_errors(project) is None
    assert "no runner on this stack probes it" in ic.what_the_bad_body_probe_did_not_ask(project)[0]


def test_a_probe_that_cannot_run_raises_nothing(project, monkeypatch):
    def broken(*_):
        raise RuntimeError("no runner")
    assert _round(project, monkeypatch, broken).defects == []


def test_the_switch_is_registered_and_off(monkeypatch):
    name = "CONTRACT_PROBE_WITH_A_BAD_BODY"
    monkeypatch.delenv(name, raising=False)
    assert name in switches.EXPERIMENTS and name not in switches.EXPERIMENTS_ON
    assert provenance.switch(provenance.SWITCHES[name]).enabled() is False
    compose = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text()
    assert f"{name}: ${{{name}:-off}}" in compose
