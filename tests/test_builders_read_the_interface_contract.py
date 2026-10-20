"""Every builder and fixer reads the interface contract lines the suite and the release check (plan CM.2, EF.11).

The architect writes one strict line per route, page control or command, and
the locked suite and the release check are made from them; the builders were
given only prose, so a label or route the suite looks for was a guess.
Measured on one run: the page kept 1 of its 10 contract lines at release.
"""

from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

import pytest

from app.agents import ledger
from app.agents.specialists import specification_for_the_work_order

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

SPEC = SimpleNamespace(interface_contract=[
    "AC-1 page /login textbox \"Email\"",
    "AC-3 GET /api/notes -> 200",
    "AC-5 command notes add milk -> exit 0",
])
ORDER = SimpleNamespace(files=["app/src/App.tsx"], interfaces=[])


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("DECISION_LEDGER", "on")


def test_a_work_order_reads_every_contract_line_word_for_word():
    detail = specification_for_the_work_order(SPEC, ORDER)

    assert "--- The interface contract:" in detail
    for line in SPEC.interface_contract:
        assert f"- {line}" in detail


def test_it_is_off_until_its_before_and_after_runs_switch_it_on(monkeypatch):
    monkeypatch.delenv("DECISION_LEDGER")
    assert ledger.ON_BY_DEFAULT is False
    assert "interface contract" not in specification_for_the_work_order(SPEC, ORDER)


def test_a_slice_keeps_to_its_budget_and_names_what_it_left_out():
    many = SimpleNamespace(interface_contract=[f"AC-{n} GET /api/items/{n} -> 200" for n in range(1, 400)])

    block = ledger.rendered(ledger.from_the_specification(many))

    assert len(block) <= ledger.SLICE_CHARACTERS + 300
    assert "more line(s) left out for room: AC-" in block


def test_a_slice_is_everyone_s_entries_the_role_s_and_those_about_its_files():
    entries = [
        ledger.Entry("decision", "D1", "for all", "x"),
        ledger.Entry("blocker", "B1", "for the page", "x", roles=("frontend_specialist",)),
        ledger.Entry("decision", "D2", "about the service", "x", files=("app/board/main.py",)),
    ]
    assert [e.id for e in ledger.the_slice(entries, "frontend_specialist", ["app/src/App.tsx"])] == ["D1", "B1"]
    assert [e.id for e in ledger.the_slice(entries, "backend_specialist", ["./app/board/main.py"])] == ["D1", "D2"]


def test_no_contract_is_no_block():
    assert ledger.for_a_work_order(SimpleNamespace(interface_contract=[]), ORDER) == ""
    assert ledger.for_a_work_order(None, ORDER) == ""


def test_the_new_lines_name_no_ui_control_or_unit_of_work():
    said = " ".join(re.findall(r'f?"([^"\n]*)"', inspect.getsource(ledger)))
    assert not BANNED.search(said), BANNED.findall(said)


def test_a_later_work_order_reads_what_earlier_ones_reported_about_its_files():
    # Plan CM.3: a builder's blockers and decisions reached only the milestone
    # review, after every work order had run.
    outputs = {
        "specialist_backend_specialist_0": SimpleNamespace(
            blockers=["The page imports `listItems` from app/src/api.ts, which does not export it yet"],
            decisions=["Renamed the session cookie to `sid` in app/board/auth.py", "Kept the defaults"],
        ),
    }
    page = SimpleNamespace(files=["app/src/api.ts", "app/src/App.tsx"])
    plan = [SimpleNamespace(files=["app/board/auth.py"]), page]
    request = {"messages": [{"role": "user", "content": "Build the page."}]}

    text = ledger.with_the_reports(request, outputs, page, plan, leave_out="specialist_frontend_specialist_1")["messages"][-1]["content"]

    assert "--- What earlier work orders reported about your files ---" in text
    assert "- blocker (specialist_backend_specialist_0): The page imports `listItems`" in text
    assert "sid" not in text and "Kept the defaults" not in text
    assert not BANNED.search(ledger.REPORTS_HEADING)


def test_the_linear_dispatch_routes_the_reports():
    from app.graph import workflow

    assert "ledger.with_the_reports(request, done, task, tasks, leave_out=stage_name)" in inspect.getsource(workflow)
