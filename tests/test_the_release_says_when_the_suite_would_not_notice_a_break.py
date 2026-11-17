"""At release, a deliberate break the locked suite does not notice is a completion gap (plan item AF).

A suite that passes says the product does what the tests check, not that the
tests check much: one run's suite passed 8 of 9 while the product scored 2 of
10 on the hidden tests. The suite is locked before anything is built, so the
probe runs at release, over about three changes (owner's budget), and only
for a suite that drives no browser.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.acceptance import mutation, suite
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _project(tmp_path, monkeypatch, kind="http_api"):
    (tmp_path / "svc" / "src").mkdir(parents=True)
    (tmp_path / "svc" / "src" / "rules.js").write_text(
        "export function adult(age) { return age >= 18; }\nexport function pages(n) { return n + 1; }\n",
        encoding="utf-8",
    )
    pack = SimpleNamespace(kind=kind, kept_files=())
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {"project": "svc"}))
    monkeypatch.setattr(suite, "is_locked", lambda root: True)
    return tmp_path / "svc" / "src" / "rules.js"


def _a_suite_that_checks_only_adult(source):
    def run():
        held = ">= 18" in source.read_text(encoding="utf-8")
        tests = [SimpleNamespace(name="adult at 18", outcome="passed" if held else "failed"),
                 SimpleNamespace(name="pages exist", outcome="passed")]
        return SimpleNamespace(report=SimpleNamespace(tests=tests))
    return run


def test_a_change_no_test_notices_is_a_gap_and_the_product_is_put_back(tmp_path, monkeypatch):
    source = _project(tmp_path, monkeypatch)
    before = source.read_text(encoding="utf-8")

    gaps = mutation.what_the_suite_does_not_notice(tmp_path, run=_a_suite_that_checks_only_adult(source))

    assert len(gaps) == 1
    assert "`+` made `-`" in gaps[0] or "+ 1" in gaps[0]
    assert "line 2" in gaps[0]
    assert not BANNED.search(gaps[0])
    assert source.read_text(encoding="utf-8") == before


def test_a_suite_that_drives_a_browser_is_left_out(tmp_path, monkeypatch):
    source = _project(tmp_path, monkeypatch, kind="fullstack")
    calls = []

    gaps = mutation.what_the_suite_does_not_notice(tmp_path, run=lambda: calls.append(1))

    assert gaps == [] and calls == []
    assert source.exists()


def test_the_release_names_a_change_its_suite_did_not_notice(tmp_path, monkeypatch):
    from app.acceptance import junit
    from app.graph import delivery

    source = _project(tmp_path, monkeypatch)
    only_adult = _a_suite_that_checks_only_adult(source)

    def the_suite(root, **kwargs):
        tests = [junit.TestResult(name=t.name, outcome=t.outcome) for t in only_adult().report.tests]
        return suite.AcceptanceResult(ran=True, report=junit.Report(found=True, tests=tests))

    monkeypatch.setattr(suite, "run", the_suite)
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)

    released = delivery.release({"repository": SimpleNamespace(root_path=str(tmp_path))}, {"configurable": {}}, None)

    assert any("line 2" in gap and "rules.js" in gap for gap in released["completion_gaps"])
