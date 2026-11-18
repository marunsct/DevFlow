"""A bad-input contract line answered with another refusal of the same family is a note, not a broken contract.

Measured on a PHP run: it passed all 9 hidden and 8 quality tests and was "not deliverable" because the contract said
`GET /notes/{id} -> 400` and `DELETE /notes/{id} -> 400` for an id that is not a number, and the product answered 404 -
which every hidden and quality test of such an id accepts. A missing record's 404 still binds.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import interface_contract as ic
from app.stacks import contract


def _checked(tmp_path, monkeypatch, lines, cases):
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(files={"playwright.config.js": ""},
                                                                            probe_runner="playwright"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, lines)

    def runner(argv, category, where):
        (tmp_path / where / "test-results").mkdir(exist_ok=True)
        body = "".join(f'<testcase name="[{c}] contract {i}: x"><failure message="x">Expected: {e}\nReceived: {r}'
                       f"</failure></testcase>" for i, (c, e, r) in enumerate(cases, 1))
        (tmp_path / where / ic.REPORT_FILE).write_text(
            f'<testsuites><testsuite name="c" tests="{len(cases)}">{body}</testsuite></testsuites>')
        return {"returncode": "1"}

    return ic.what_the_contract_checks_find(tmp_path, runner=runner)


def test_a_400_line_answered_404_is_noted_not_failed(tmp_path, monkeypatch):
    gaps = _checked(tmp_path, monkeypatch, ["AC-3 GET /notes/{id} -> 400"], [("AC-3", 400, 404)])

    assert not any("does not keep its interface contract" in g for g in gaps)
    assert any("AC-3 GET /notes/{id} -> 400 (answered 404, another refusal" in g for g in gaps)


def test_a_missing_record_s_404_answered_400_still_fails(tmp_path, monkeypatch):
    gaps = _checked(tmp_path, monkeypatch, ["AC-3 GET /notes/{id} -> 404"], [("AC-3", 404, 400)])

    assert any("does not keep its interface contract" in g for g in gaps)


def test_a_bad_input_line_answered_with_a_server_error_still_fails(tmp_path, monkeypatch):
    gaps = _checked(tmp_path, monkeypatch, ["AC-3 GET /notes/{id} -> 400"], [("AC-3", 400, 500)])

    assert any("does not keep its interface contract" in g for g in gaps)
