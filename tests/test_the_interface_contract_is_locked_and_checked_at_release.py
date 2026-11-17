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
        if argv[0] == "notes":  # the contract's command line, run as itself (Initiative AU)
            seen["command"] = argv
            return {"returncode": "0"}
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

    assert len(gaps) == 2 and "AC-1" in gaps[0] and "signed-in user" in gaps[0]
    # The prose line is named as unchecked, not dropped at the lock.
    assert "the notes page lists every note (follows none of the contract's three forms)" in gaps[1]
    assert seen["command"] == ["notes", "add", "milk"]
    assert not BANNED.search(gaps[0])
    assert "import base from './playwright.config.js'" in seen["config"]
    assert not (tmp_path / "app" / ic.CHECK_DIR).exists() and not (tmp_path / "app" / ic.CONFIG_FILE).exists()


def test_a_pack_without_a_probe_runner_says_its_routes_went_unchecked_and_still_runs_commands(tmp_path, monkeypatch):
    """Initiative AU: a line nothing can check is said to be unchecked, never left out in silence."""
    _locked_project(tmp_path, monkeypatch)
    ic.record_at_lock(tmp_path, LINES)
    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(files={}, probe_runner=""), {"project": "app"}))

    gaps = ic.what_the_contract_checks_find(tmp_path, runner=lambda argv, category, where: {"returncode": "3"})

    assert any("AC-5" in gap and "exited 3" in gap for gap in gaps)
    [unchecked] = [gap for gap in gaps if "were not checked" in gap]
    assert "AC-3 GET /api/notes" in unchecked and "no runner on this stack probes" in unchecked
    assert not BANNED.search(" ".join(gaps))


def test_a_route_with_a_parameter_is_unchecked_not_failed(tmp_path, monkeypatch):
    _locked_project(tmp_path, monkeypatch)
    ic.record_at_lock(tmp_path, ["AC-2 GET /api/notes/{id} -> 200"])

    gaps = ic.what_the_contract_checks_find(tmp_path, runner=lambda *a: 1 / 0)

    assert gaps == ["1 line(s) of the interface contract were not checked at release: AC-2 GET /api/notes/{id} -> 200 (a route with a parameter in it)"]


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


BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n## Acceptance Criteria\n- Notes persist between page refreshes\n"


def test_an_approved_suite_is_locked_with_the_architect_s_contract(tmp_path, monkeypatch):
    from app.acceptance import junit
    from app.acceptance.criteria import number
    from app.graph import acceptance_nodes

    (tmp_path / ".project-directory").write_text("notes\n")
    suite.save_criteria(tmp_path, number(BRIEF))
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    names = ["[AC-1] adds", "[AC-2] deletes", "[AC-3] persists"]
    spec.write_text("".join(f"test('{name}', async () => {{}});\n" for name in names))
    ran = suite.AcceptanceResult(ran=True, exit_code=1, command="npm run test:acceptance", report=junit.Report(
        found=True, tests=[junit.TestResult(name=name, outcome="failed", message="nope") for name in names]))
    monkeypatch.setattr(suite, "run", lambda root: ran)
    # The checks at the lock start the product: the sandbox's to do, not this test's.
    monkeypatch.setattr(ic, "probe_at_the_lock", lambda root: [])
    monkeypatch.setattr("app.graph.workflow._run_gated_agent", lambda state, config, *, output_key, next_stage, **kwargs: {
        output_key: SimpleNamespace(approved=True, findings=[]), "stage": next_stage})
    monkeypatch.setattr("app.agents.acceptance_reviewer.create_acceptance_reviewer_agent", lambda *a, **k: object())
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "document": SimpleNamespace(text=BRIEF),
        "product_intake": SimpleNamespace(product_name="Notes", success_measures=[]),
        "stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(product_kind="browser_app")),
        "technical_specification": SimpleNamespace(interface_contract=[LINES[0]]),
        "acceptance_round": 1,
    }
    context = acceptance_nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None)

    acceptance_nodes.acceptance_review(state, {"configurable": {"thread_id": "t"}}, context)

    assert suite.is_locked(tmp_path)
    assert [check.line for check in ic.the_locked_contract(tmp_path)] == [LINES[0]]


def test_a_contract_line_the_release_cannot_check_is_one_of_its_gaps(tmp_path, monkeypatch):
    from app.graph import delivery

    _locked_project(tmp_path, monkeypatch)
    ic.record_at_lock(tmp_path, ["AC-2 GET /api/notes/{id} -> 200"])
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)

    released = delivery.release({"repository": SimpleNamespace(root_path=str(tmp_path))}, {"configurable": {}}, None)

    assert ("1 line(s) of the interface contract were not checked at release: AC-2 GET /api/notes/{id} -> 200 "
            "(a route with a parameter in it)") in released["completion_gaps"]


def test_a_pack_declares_its_runner_by_what_it_ships():
    from app.stacks.packs import ALL_PACKS

    declared = {pack.name: pack.probe_runner for pack in ALL_PACKS}

    assert declared["fullstack-react-fastapi"] == "playwright"
    assert declared["python-library"] == ""
    assert set(declared.values()) <= set(ic.PROBE_RUNNERS) | {""}


def test_what_a_command_line_writes_is_not_shipped(tmp_path, monkeypatch):
    import subprocess

    _locked_project(tmp_path, monkeypatch)
    ic.record_at_lock(tmp_path, ["AC-5 command notes add milk -> exit 0"])
    for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=tmp_path, check=True)
    (tmp_path / "app" / "notes.txt").write_text("kept\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)

    def runner(argv, category, where):
        (tmp_path / "app" / "notes.txt").write_text("kept\nmilk\n")
        (tmp_path / "app" / "new-store.json").write_text("[]")
        return {"returncode": "0"}

    assert ic.what_the_contract_checks_find(tmp_path, runner=runner) == []
    assert (tmp_path / "app" / "notes.txt").read_text() == "kept\n"
    assert not (tmp_path / "app" / "new-store.json").exists()


def test_a_note_after_a_line_s_form_is_no_part_of_its_check():
    # One specification wrote a feature's route lines with a note after the status,
    # and the lock dropped them.
    checks, unreadable = ic.parse(["AC-11 PUT /api/tasks/7 -> 200 (updates reminder_at field)"])

    assert unreadable == [] and (checks[0].method, checks[0].path, checks[0].status) == ("PUT", "/api/tasks/7", 200)


def test_a_line_that_follows_no_form_is_named_at_release_not_dropped_at_the_lock(tmp_path, monkeypatch):
    _locked_project(tmp_path, monkeypatch)
    ic.record_at_lock(tmp_path, ["AC-11 page /dashboard card task reminder bell icon"])

    gaps = ic.what_the_contract_checks_find(tmp_path, runner=lambda *a: 1 / 0)

    assert gaps == ["1 line(s) of the interface contract were not checked at release: "
                    "AC-11 page /dashboard card task reminder bell icon (follows none of the contract's three forms)"]


def test_the_shapes_one_specification_wrote_its_lines_in_are_read():
    checks, unreadable = ic.parse([
        'AC-2 page /dashboard form textbox "Title"',
        'AC-4 page /dashboard form select "Priority"',
        'AC-2 page /dashboard form textarea "Description"',
        "AC-1 AC-2 AC-3 POST /auth/register -> 201",
        'AC-5 page /dashboard form input[type=date] "Due Date"',
    ])

    assert [(c.criterion, c.kind, c.role, c.name) for c in checks if c.kind == "page"] == [
        ("AC-2", "page", "textbox", "Title"), ("AC-4", "page", "combobox", "Priority"),
        ("AC-2", "page", "textbox", "Description"),
    ]
    assert [(c.criterion, c.method, c.path, c.status) for c in checks if c.kind == "http"] == [
        ("AC-1", "POST", "/auth/register", 201),
    ]
    assert unreadable == ['AC-5 page /dashboard form input[type=date] "Due Date"']


def test_a_line_set_aside_at_the_lock_is_read_again_at_release(tmp_path, monkeypatch):
    state = _locked_project(tmp_path, monkeypatch)
    state["interface_contract"] = []
    state["interface_contract_unreadable"] = ["AC-2 GET /api/notes/{id} -> 200"]

    gaps = ic.what_the_contract_checks_find(tmp_path, runner=lambda *a: 1 / 0)

    assert gaps == ["1 line(s) of the interface contract were not checked at release: "
                    "AC-2 GET /api/notes/{id} -> 200 (a route with a parameter in it)"]


def test_a_line_quoted_whole_is_read_and_a_page_line_keeps_its_name():
    checks, unreadable = ic.parse(['"AC-1 POST /notes -> 201"', "'AC-2 GET /notes -> 200'", 'AC-4 page /login textbox "Email"'])
    assert unreadable == []
    assert [(c.method, c.path, c.status) for c in checks[:2]] == [("POST", "/notes", 201), ("GET", "/notes", 200)]
    assert checks[2].name == "Email"


def test_a_write_that_succeeds_only_with_a_body_is_unchecked_not_failed(tmp_path, monkeypatch):
    _locked_project(tmp_path, monkeypatch)
    ic.record_at_lock(tmp_path, ["AC-1 POST /notes -> 201"])

    gaps = ic.what_the_contract_checks_find(tmp_path, runner=lambda *a: 1 / 0)

    assert gaps == ["1 line(s) of the interface contract were not checked at release: AC-1 POST /notes -> 201 "
                    "(a write that succeeds only with a body; the probe sends none)"]
    assert not BANNED.search(" ".join(gaps))
    refused, _ = ic.parse(["AC-7 POST /notes -> 422"])
    assert not ic._a_write_that_needs_a_body(refused[0])
