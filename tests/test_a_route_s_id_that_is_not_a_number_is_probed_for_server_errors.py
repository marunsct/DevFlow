"""A route's parameter is also probed with a value that is not a number: a 5xx there is a defect (found on the sweep).

Measured on one run (a Java service, 9/9 hidden): `GET /notes/abc` answered 500, a quality test found it, and nothing
in the run had asked - the server-error probe sent only a record that does not exist (`999999999`), a number.
"""
from __future__ import annotations

from app.acceptance import interface_contract as ic


def _checks():
    checks, _ = ic.parse(["AC-3 GET /notes/{id} -> 200, 404", "AC-5 DELETE /notes/{id} -> 204, 404",
                          "AC-2 GET /notes -> 200"])
    return checks


def test_each_templated_route_gets_a_variant_with_an_id_that_is_not_a_number():
    variants = ic.with_an_id_that_is_not_a_number(_checks())
    assert sorted((c.method, c.path) for c in variants) == [
        ("DELETE", f"/notes/{ic.AN_ID_THAT_IS_NOT_A_NUMBER}"), ("GET", f"/notes/{ic.AN_ID_THAT_IS_NOT_A_NUMBER}")]


def test_the_server_error_probe_asks_them_after_the_lines_it_asked_before(tmp_path, monkeypatch):
    from types import SimpleNamespace

    asked = []
    monkeypatch.setattr(ic, "the_locked_contract", lambda root: _checks())
    monkeypatch.setattr("app.stacks.contract.the_pack", lambda root: (SimpleNamespace(probe_runner="playwright"), {"project": "p"}))
    monkeypatch.setitem(ic.PROBE_RUNNERS, "playwright", object())

    def report(project, name, probe, web, run, *args, **kwargs):
        asked.extend(web)
        failed = SimpleNamespace(name=f"contract {len(web)}: x", outcome="failed", message="Received: 500")
        return SimpleNamespace(found=True, tests=[failed])

    monkeypatch.setattr(ic, "_the_probe_s_report", report)
    errors = ic.server_errors(tmp_path, runner=lambda *a: {})
    before = ic.checkable(_checks())
    assert [c.path for c in asked[:len(before)]] == [c.path for c in before]
    assert asked[-1].path.endswith(ic.AN_ID_THAT_IS_NOT_A_NUMBER)
    assert errors and errors[0][0].path.endswith(ic.AN_ID_THAT_IS_NOT_A_NUMBER) and errors[0][1] == 500
