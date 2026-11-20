"""A page line no bare visit can check is named unchecked at release, never a broken contract (2026-11-20).

Measured on a fullstack run that passed every hidden and quality test: `page / message "Failed to delete bookmark"`
was probed as a role named `message`, which no page has, and the release was "not deliverable" on it. A word that is
no ARIA role gives the probe nothing to find; an alert or a status is shown only after an action, often a failed one.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from xml.sax.saxutils import quoteattr

from app import completion_verdict
from app.acceptance import interface_contract as ic


def _release_gaps(tmp_path, monkeypatch, line: str) -> list[str]:
    """The release's gaps for one locked page line, on a product whose page shows none of the contract's controls."""
    from app.stacks import contract

    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(files={"playwright.config.js": ""}, probe_runner="playwright"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, [line])

    def runner(argv, category, where):
        project = tmp_path / where
        spec = "".join(p.read_text() for p in project.rglob("contract.spec.js"))
        titles = [json.loads(t) for t in re.findall(r'^test\(("(?:[^"\\]|\\.)*"), async', spec, re.M)]
        (project / "test-results").mkdir(exist_ok=True)
        (project / ic.REPORT_FILE).write_text(
            f'<testsuites><testsuite name="c" tests="{len(titles)}">'
            + "".join(f'<testcase name={quoteattr(t)}><failure message="x">not visible</failure></testcase>' for t in titles)
            + "</testsuite></testsuites>")
        return {"returncode": "1" if titles else "0"}

    return ic.what_the_contract_checks_find(tmp_path, runner=runner)


def _broken(gaps: list[str]) -> list[str]:
    return [g for g in gaps if "does not keep its interface contract" in g]


def _unchecked(gaps: list[str]) -> str:
    return next((g for g in gaps if "were not checked at release" in g), "")


def test_a_line_naming_a_message_is_listed_unchecked_and_does_not_block(tmp_path, monkeypatch):
    gaps = _release_gaps(tmp_path, monkeypatch, 'AC-20 page / message "Failed to delete bookmark"')
    assert _broken(gaps) == []
    unchecked = _unchecked(gaps)
    assert 'AC-20 page / message "Failed to delete bookmark"' in unchecked
    assert "names no role a probe can find" in unchecked
    assert not completion_verdict.is_blocking(unchecked)


def test_an_alert_at_a_bare_visit_is_listed_unchecked_and_does_not_block(tmp_path, monkeypatch):
    gaps = _release_gaps(tmp_path, monkeypatch, 'AC-4 page / alert "Saved"')
    assert _broken(gaps) == []
    assert "a message shown after an action" in _unchecked(gaps)


def test_a_control_absent_at_a_bare_visit_still_breaks_the_contract(tmp_path, monkeypatch):
    gaps = _release_gaps(tmp_path, monkeypatch, 'AC-2 page / button "Add"')
    assert len(_broken(gaps)) == 1 and 'button "Add"' in _broken(gaps)[0]


def test_a_strict_line_naming_a_field_is_checked_as_a_textbox():
    checks, unreadable = ic.parse(['AC-1 page /notes field "Title"'])
    assert unreadable == []
    assert (checks[0].kind, checks[0].path, checks[0].role, checks[0].name) == ("page", "/notes", "textbox", "Title")
