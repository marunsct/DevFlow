"""A field the specification refuses empty is sent empty to every write that takes it, at release.

Measured on one run: the brief said once that a missing or empty title is refused; the suite tested it
on create only, the product accepted an update that emptied the title, and the run shipped as passing
while a hidden test failed. The rule holds for every write, so the harness asks each one.
"""
from app.acceptance import interface_contract as ic


def test_the_fields_a_rule_refuses_empty_are_read():
    texts = [
        "A title that is missing or empty is refused with 400 or 422, and nothing is stored",
        "An empty or missing `name` is rejected with 422",
        "The email must not be empty",
        "GET /health answers 200",
        "A body that is too long is truncated",
    ]
    assert ic.fields_refused_when_empty(texts) == ["title", "name", "email"]


def test_each_write_of_the_contract_is_asked_with_the_field_emptied():
    checks, _ = ic.parse([
        "AC-8 POST /notes -> 201",
        "AC-11 PUT /notes/{id} -> 200 or 404",
        "AC-10 GET /notes/{id} -> 200 or 404",
    ])
    bodies = [{"title": "Groceries", "body": "milk"}]

    asked, unchecked = ic.emptied_field_checks(checks, bodies, ["title", "colour"])

    assert [(c.method, c.path, c.emptied) for c in asked] == [("POST", "/notes", "title"), ("PUT", "/notes/{id}", "title")]
    assert unchecked == []


def test_the_test_sends_the_example_with_the_field_emptied_and_wants_a_refusal():
    checks, _ = ic.parse(["AC-8 POST /notes -> 201", "AC-11 PUT /notes/{id} -> 200 or 404"])
    asked, _ = ic.emptied_field_checks(checks, [{"title": "Groceries", "body": "milk"}], ["title"])

    spec = ic.playwright_emptied_field_checks(asked)

    assert '"title": ""' in spec or "'title': ''" in spec or '{"title":"","body":"milk"}' in spec.replace(" ", "")
    assert "toBeGreaterThanOrEqual(400)" in spec and "toBeLessThan(500)" in spec
    assert "encodeURIComponent(id)" in spec  # the update is asked on a record made first


def test_a_write_that_answered_2xx_to_the_emptied_field_is_an_error(tmp_path, monkeypatch):
    import types

    checks, _ = ic.parse(["AC-8 POST /notes -> 201", "AC-11 PUT /notes/{id} -> 200 or 404"])
    monkeypatch.setattr(ic, "the_locked_contract", lambda root: checks)
    from app.acceptance import suite
    from app.acceptance.criteria import Criterion
    from app.stacks import contract

    monkeypatch.setattr(suite, "criteria", lambda root: [Criterion("AC-13", "A title that is missing or empty is refused with 400 or 422", "brief")])
    monkeypatch.setattr(suite, "_state", lambda root: {"interface_contract_bodies": [{"title": "G", "body": "m"}]})
    monkeypatch.setattr(contract, "the_pack", lambda root: (types.SimpleNamespace(probe_runner="playwright"), {"project": "notes-api"}))
    report = types.SimpleNamespace(found=True, tests=[
        types.SimpleNamespace(name="[AC-8] contract 1: AC-8 POST /notes -> 201 with an empty title", outcome="passed", message=""),
        types.SimpleNamespace(name="[AC-11] contract 2: AC-11 PUT /notes/{id} -> 200 or 404 with an empty title",
                              outcome="failed", message="Expected: >= 400\nReceived: 200"),
    ])
    monkeypatch.setattr(ic, "_the_probe_s_report", lambda *a, **k: report)

    accepted = ic.emptied_field_errors(tmp_path, runner=object())

    assert [(c.method, c.path, c.emptied, status) for c, status in accepted] == [("PUT", "/notes/{id}", "title", 200)]


def test_the_green_round_raises_a_defect_for_it(monkeypatch):
    import types

    from app.agents.specialists import ReportedDefect
    from app.graph import workflow

    checks, _ = ic.parse(["AC-11 PUT /notes/{id} -> 200 or 404"])
    check = __import__("dataclasses").replace(checks[0], emptied="title")
    monkeypatch.setattr(ic, "emptied_field_errors", lambda root: [(check, 200)])
    monkeypatch.setattr(workflow, "_the_unit_tests_fail", lambda milestone, text: types.SimpleNamespace(owner="backend"))
    from app.graph import acceptance_nodes
    monkeypatch.setattr(acceptance_nodes, "where_errors_become_5xx", lambda root: [])
    result = types.SimpleNamespace(defects=[], model_copy=lambda update: types.SimpleNamespace(**update))
    state = {"repository": types.SimpleNamespace(root_path="/x")}

    raised = workflow._with_an_emptied_field_defect(state, result, None).defects

    assert len(raised) == 1 and raised[0].description.startswith(ic.EMPTIED_FIELD_ACCEPTED)
    assert "`PUT /notes/{id}` with an empty `title` answered 200" in raised[0].description
