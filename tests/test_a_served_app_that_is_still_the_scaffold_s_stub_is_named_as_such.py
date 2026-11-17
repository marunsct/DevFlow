"""A served app that is still the scaffold's stub is named as such.

The dominant live failure: the acceptance suite ran against the scaffold's
stub service while everything the run drafted sat in files nothing served -
31 of 35 locked tests failed against the stub and the fixers could not exit,
because no measurement ever said "the served app is not the drafted app".
The packs now declare the file the drafted service's routes live in, the
scaffold wrote it as a stub, and the harness's own measurement rounds
compare it byte for byte: while it is unchanged, one bundled defect names
the wiring gap itself (Initiative K.3).
"""

from __future__ import annotations

import re
from pathlib import Path

from app.stacks import contract, pack_named
from app.stacks.scaffold import entrypoint_is_still_the_stub

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def _a_scaffolded_workspace(tmp_path: Path, pack_name: str) -> Path:
    pack = pack_named(pack_name)
    assert pack is not None
    project = "notes-app"
    for relative, content in pack.render(project, "Notes", "notes_app").items():
        target = tmp_path / project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    contract.write(tmp_path, pack, project, "Notes", "notes_app")
    return tmp_path


def test_the_packs_that_serve_declare_the_file_their_routes_live_in() -> None:
    """The declaration is pack data: the served product's routes grow in this
    file, and the scaffold writes it as a stub."""
    assert pack_named("node-http-api").entrypoint == "src/app.js"
    assert pack_named("fullstack-node").entrypoint == "src/app.js"
    assert pack_named("node-nest-api").entrypoint == "src/app.module.ts"
    assert pack_named("go-http-api").entrypoint == "server.go"
    assert pack_named("rust-axum-api").entrypoint == "src/lib.rs"
    # A pack whose server is harness-owned declares none: the stub IS the
    # delivered server there, and the product is what it serves.
    assert pack_named("browser-javascript").entrypoint == ""


def test_an_untouched_stub_is_found(tmp_path: Path) -> None:
    root = _a_scaffolded_workspace(tmp_path, "node-http-api")

    found = entrypoint_is_still_the_stub(root)

    assert found == "notes-app/src/app.js"


def test_a_wired_entrypoint_is_not_the_stub(tmp_path: Path) -> None:
    root = _a_scaffolded_workspace(tmp_path, "go-http-api")
    server = root / "notes-app" / "server.go"
    server.write_text(server.read_text(encoding="utf-8") + "\n// one real route\n", encoding="utf-8")

    assert entrypoint_is_still_the_stub(root) is None


def test_a_missing_or_undeclared_entrypoint_says_nothing(tmp_path: Path) -> None:
    root = _a_scaffolded_workspace(tmp_path, "rust-axum-api")
    (root / "notes-app" / "src" / "lib.rs").unlink()
    assert entrypoint_is_still_the_stub(root) is None

    undeclared_root = tmp_path / "b"
    undeclared_root.mkdir()
    _a_scaffolded_workspace(undeclared_root, "browser-javascript")
    assert entrypoint_is_still_the_stub(undeclared_root) is None
    # No contract at all: nothing was scaffolded, nothing to compare.
    assert entrypoint_is_still_the_stub(tmp_path / "nowhere") is None


def test_the_defect_names_the_wiring_gap_in_plain_language(tmp_path: Path) -> None:
    from app.graph.workflow import _the_served_app_is_the_scaffold_s_stub

    defect = _the_served_app_is_the_scaffold_s_stub("notes-app/src/app.js", "backend")

    assert "still the scaffold's stub" in defect.description
    assert "notes-app/src/app.js" in defect.description
    assert defect.severity == "major"
    assert defect.affected_files == ["notes-app/src/app.js"]
    assert defect.owner == "backend"
    text = " ".join(str(v) for v in defect.model_dump().values() if v)
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", text, re.IGNORECASE), word


def test_the_file_by_file_round_names_the_stub(tmp_path: Path, monkeypatch) -> None:
    """The round the harness runs without a model when the suite gave no answer names the stub when it finds it."""
    from types import SimpleNamespace

    from app.acceptance import suite
    from app.graph import workflow
    from app.state import RepositoryContext

    root = _a_scaffolded_workspace(tmp_path, "node-http-api")
    record = contract.read(root)
    spec = root / "notes-app" / str(record.get("acceptance_dir") or "") / "notes.spec.js"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("test('[AC-1] adds', async () => {});\n")
    suite.lock(root)
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner",
                        lambda repo_root: lambda argv, category, project: {"returncode": "1", "stdout": "1 failed", "stderr": ""})
    monkeypatch.setattr(workflow, "_run_unit_tests_procedurally", lambda root: (None, ""))
    state = {"repository": RepositoryContext(root_path=str(root), branch="main", commit="0", status="clean")}

    diagnosed = workflow._diagnosed_file_by_file(state, {}, SimpleNamespace(milestone_scope=[], delegated_tasks=[]), 1)

    assert any("still the scaffold's stub" in d.description and "notes-app/src/app.js" in d.description
               for d in diagnosed.defects)


def test_the_fast_delivery_round_names_the_stub(tmp_path: Path) -> None:
    """The round the harness runs itself in fast delivery, with locked criteria failing, names the stub."""
    from workflow_nodes import a_test_round

    root = _a_scaffolded_workspace(tmp_path, "node-http-api")

    update, _ = a_test_round(root, patches={
        "app.graph.acceptance_nodes.suite.is_locked": lambda root: True,
        "app.graph.acceptance_nodes.suite.last_result": lambda root: {"ran": True, "failed": 1},
        "app.graph.acceptance_nodes._failing_due": lambda state: (["AC-1"], "AC-1 fails"),
        "app.delivery.fast": lambda *a, **k: True,
    })

    assert "still the scaffold's stub" in str(update) and "notes-app/src/app.js" in str(update)


def test_a_fullstack_page_left_the_stub_is_found_though_the_app_was_drafted_elsewhere(tmp_path: Path) -> None:
    """One run drafted its app into frontend/ and backend/app/; the served page
    stayed the scaffold's root component and every page test failed its first
    control, while 13 fixers chased criteria one by one."""
    root = _a_scaffolded_workspace(tmp_path, "fullstack-react-fastapi")
    (root / "notes-app" / "frontend" / "src").mkdir(parents=True)
    (root / "notes-app" / "frontend" / "src" / "App.jsx").write_text("export default function App() {}\n")

    assert entrypoint_is_still_the_stub(root) == "notes-app/src/App.tsx"

    app = root / "notes-app" / "src" / "App.tsx"
    app.write_text(app.read_text(encoding="utf-8") + "\n// the real page\n", encoding="utf-8")
    assert entrypoint_is_still_the_stub(root) == "notes-app/notes_app/main.py"

    main = root / "notes-app" / "notes_app" / "main.py"
    main.write_text(main.read_text(encoding="utf-8") + "\n# the real routes\n", encoding="utf-8")
    assert entrypoint_is_still_the_stub(root) is None


def test_every_fullstack_pack_declares_its_page_and_its_service() -> None:
    for name in ("fullstack-react-fastapi", "fullstack-vue-express"):
        pack = pack_named(name)
        if pack is not None:
            assert len(pack.entrypoints) == 2, name


def test_every_fixer_is_told_first_while_the_stub_is_served(tmp_path: Path) -> None:
    """A queue assembled before the stub was found went fixer after fixer, each chasing its own symptom."""
    import the_fix_stage

    root = _a_scaffolded_workspace(tmp_path, "fullstack-react-fastapi")

    _, seen = the_fix_stage.run(root, the_fix_stage.a_state(root))

    told = seen.requests[0]
    assert "`notes-app/src/App.tsx` is byte-identical" in told
    assert not re.search(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", told.split(the_fix_stage.BASE_REQUEST, 1)[1], re.I)


def test_a_fixer_is_not_told_once_the_drafted_app_is_served(tmp_path: Path) -> None:
    import the_fix_stage

    root = _a_scaffolded_workspace(tmp_path, "fullstack-react-fastapi")
    for path in ("src/App.tsx", "notes_app/main.py"):
        f = root / "notes-app" / path
        f.write_text(f.read_text(encoding="utf-8") + "\n// built\n", encoding="utf-8")

    _, seen = the_fix_stage.run(root, the_fix_stage.a_state(root))

    assert "is byte-identical" not in seen.requests[0]
