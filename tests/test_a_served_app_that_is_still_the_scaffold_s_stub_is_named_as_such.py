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


def test_the_harness_measurement_rounds_ask_the_question() -> None:
    """Both rounds the harness runs without a model - the file-by-file
    diagnosis and the fast-delivery round - name the stub when they find it."""
    import inspect

    from app.graph import workflow

    per_file = inspect.getsource(workflow._diagnosed_file_by_file)
    assert "entrypoint_is_still_the_stub" in per_file
    assert "_the_served_app_is_the_scaffold_s_stub" in per_file

    triage = inspect.getsource(workflow.build_workflow_graph)
    assert "entrypoint_is_still_the_stub" in triage
    assert "_the_served_app_is_the_scaffold_s_stub" in triage
