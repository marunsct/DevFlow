"""The architect's interface contract is locked with the suite and checked at release (plan items C and J.3).

Owner decision 2026-10-18. The release trusted only the locked suite, which a
repair can weaken. The contract is strict lines the harness compiles into
checks with no model, from the architect's contract, never from the brief's
prose. A failed check is a completion gap for the first runs, not a block.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.acceptance import interface_contract as ic
from app.acceptance import suite
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LINES = [
    "AC-3 GET /api/notes -> 200",
    "- AC-1 page /login textbox \"Email\"",
    "AC-5 command notes add milk -> exit 0",
    "the notes page lists every note",
]


def test_each_form_is_read_and_prose_is_set_aside():
    checks, unreadable = ic.parse(LINES)

    assert [(c.criterion, c.kind) for c in checks] == [("AC-3", "http"), ("AC-1", "page"), ("AC-5", "command")]
    assert checks[0].method == "GET" and checks[0].path == "/api/notes" and checks[0].status == 200
    assert checks[1].role == "textbox" and checks[1].name == "Email"
    assert checks[2].command == "notes add milk" and checks[2].exit_code == 0
    assert unreadable == ["the notes page lists every note"]


def test_the_compiled_checks_carry_their_criterion_and_exact_names():
    spec = ic.playwright_checks(ic.parse(LINES)[0])

    assert spec.count("test(") == 2
    assert "[AC-3] contract 1" in spec and "[AC-1] contract 2" in spec
    assert 'getByRole("textbox", { name: "Email", exact: true })' in spec
    assert 'method: "GET"' in spec and "toBe(200)" in spec


def _locked_project(tmp_path, monkeypatch):
    (tmp_path / "app").mkdir()
    monkeypatch.setattr(suite, "_state", lambda root: state)
    monkeypatch.setattr(suite, "_save_state", lambda root, data: state.update(data))
    state: dict = {}
    pack = SimpleNamespace(files={"playwright.config.js": ""}, probe_runner="playwright")
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {"project": "app"}))
    return state


def test_the_contract_is_kept_at_lock(tmp_path, monkeypatch):
    _locked_project(tmp_path, monkeypatch)

    ic.record_at_lock(tmp_path, LINES)

    assert [c.line for c in ic.the_locked_contract(tmp_path)] == LINES[:1] + ['AC-1 page /login textbox "Email"'] + LINES[2:3]


def test_a_failed_check_at_release_is_a_gap_and_the_files_are_removed(tmp_path, monkeypatch):
    _locked_project(tmp_path, monkeypatch)
    ic.record_at_lock(tmp_path, LINES)
    seen = {}

    def runner(argv, category, working_directory):
        project = tmp_path / working_directory
        seen["spec"] = (project / ic.CHECK_DIR / "contract.spec.js").read_text()
        seen["config"] = (project / ic.CONFIG_FILE).read_text()
        (project / "test-results").mkdir(exist_ok=True)
        (project / ic.REPORT_FILE).write_text(
            '<testsuites><testsuite name="c" tests="2">'
            '<testcase name="[AC-3] contract 1: AC-3 GET /api/notes -&gt; 200"/>'
            '<testcase name="[AC-1] contract 2: AC-1 page /login textbox &quot;Email&quot;"><failure message="not visible"/></testcase>'
            "</testsuite></testsuites>"
        )
        return {"returncode": "1"}

    gaps = ic.what_the_contract_checks_find(tmp_path, runner=runner)

    assert len(gaps) == 1 and "AC-1" in gaps[0] and "signed-in user" in gaps[0]
    assert not BANNED.search(gaps[0])
    assert "import base from './playwright.config.js'" in seen["config"]
    assert not (tmp_path / "app" / ic.CHECK_DIR).exists() and not (tmp_path / "app" / ic.CONFIG_FILE).exists()


def test_a_pack_without_playwright_is_not_checked(tmp_path, monkeypatch):
    _locked_project(tmp_path, monkeypatch)
    ic.record_at_lock(tmp_path, LINES)
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(files={}, probe_runner=""), {"project": "app"}))

    assert ic.what_the_contract_checks_find(tmp_path, runner=lambda *a: 1 / 0) == []


def test_the_architect_writes_it_and_the_acceptance_author_reads_it(tmp_path):
    from app.acceptance.requests import _the_interface_contract
    from app.agents.principal_architect import TechnicalSpecificationOutput
    from app.graph.specification_parts import PARTS

    description = TechnicalSpecificationOutput.model_fields["interface_contract"].description
    section = _the_interface_contract(LINES[:2])

    assert any("interface_contract" in part for part in PARTS)
    assert "AC-3 GET /api/notes -> 200" in section
    assert not BANNED.search(description) and not BANNED.search(section)
    assert _the_interface_contract([]) == ""


def test_the_lock_and_the_release_use_it():
    import inspect

    from app.graph import acceptance_nodes, delivery

    assert "record_at_lock(root," in inspect.getsource(acceptance_nodes)
    assert "gaps.extend(what_the_contract_checks_find(root))" in inspect.getsource(delivery)


def test_a_pack_declares_its_runner_by_what_it_ships_and_the_checks_name_no_tool():
    from app.stacks.packs import ALL_PACKS

    declared = {pack.name: pack.probe_runner for pack in ALL_PACKS}

    assert declared["fullstack-react-fastapi"] == "playwright"
    assert declared["python-library"] == ""
    assert set(declared.values()) <= set(ic.PROBE_RUNNERS) | {""}
    body = __import__("inspect").getsource(ic.what_the_contract_checks_find)
    assert "playwright" not in body.lower().replace("probe_runners", "")
