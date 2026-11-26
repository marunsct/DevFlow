"""A fix or testing stage's probe is scratch by what it is, not only by its name (LF.1533).

Measured on a page product: three fixers left `diag.js`, `diag.mjs`, `diag2.mjs` and `diag-filter.js` at the project
root, outside every name `file_kinds.SCRATCH_NAME` then knew; the cross-file check raised `diag.js`'s `require` under
`"type": "module"` as the product's defect, and it took a fix round. A name was added (LF.1529); the next probe will
have a name no list knows. The probes are the fixers' own files, copied from the run's transcript
(`tests/captured/fixer-probes/`), beside the captured page product of the same brief; `check_filter.js` is the
probe `diag.js` under a name no rule knows.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from app.analysis import project_memory
from app.analysis.file_kinds import is_scratch
from app.analysis.integration_checks import summarise_integration
from app.observability.transcript import asked_for
from app.tools.repository import clear_the_throwaways_left_behind, write_approved_artifact

CAPTURED = Path(__file__).parent / "captured"
PRODUCT = CAPTURED / "projects" / "react-to-do-list-app"
PROBES = CAPTURED / "fixer-probes"
PROJECT = "simple-to-do-list-app"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _workspace(tmp_path: Path) -> Path:
    """The captured page product, pinned, with the work orders' file table its run had."""
    root = tmp_path / "workspace"
    shutil.copytree(PRODUCT, root / PROJECT)
    (root / ".project-directory").write_text(PROJECT + "\n")
    (root / ".work-order-files.json").write_text(json.dumps({
        f"{PROJECT}/src/App.tsx": "specialist_ui_ux_0",
        f"{PROJECT}/src/styles.css": "specialist_ui_ux_0",
        f"{PROJECT}/tests/App.test.tsx": "specialist_testing_1",
    }))
    return root


def _left_by(root: Path, stage: str, name: str, probe: str) -> str:
    """A file a stage wrote at the project root, recorded as its own as the write tools record it."""
    relative = f"{PROJECT}/{name}"
    (root / relative).write_text((PROBES / probe).read_text())
    project_memory.record(root, relative, stage)
    return relative


def _the_fixers_probes(root: Path) -> list[str]:
    return [
        _left_by(root, "defect_fix_2_7", "diag.js", "diag.js"),
        _left_by(root, "defect_fix_2_7", "diag.mjs", "diag.mjs"),
        _left_by(root, "defect_fix_2_7", "diag2.mjs", "diag2.mjs"),
        _left_by(root, "defect_fix_2_4", "diag-filter.js", "diag-filter.js"),
        _left_by(root, "defect_fix_2_7", "check_filter.js", "diag.js"),
    ]


def test_an_unnamed_probe_a_fixer_left_is_scratch(tmp_path):
    root = _workspace(tmp_path)
    _the_fixers_probes(root)

    assert is_scratch(f"{PROJECT}/check_filter.js", root)
    # Project-relative too, as some checks name it.
    assert is_scratch("check_filter.js", root)


def test_the_cross_file_check_does_not_raise_a_probe_s_require_as_the_product_s(tmp_path):
    root = _workspace(tmp_path)
    _the_fixers_probes(root)

    found = summarise_integration(root)

    raised = [line for line in found.splitlines() if "check_filter.js" in line and "require" in line]
    assert raised == []


def test_the_sweep_removes_an_unnamed_probe(tmp_path):
    root = _workspace(tmp_path)
    _the_fixers_probes(root)

    removed = clear_the_throwaways_left_behind(root)

    assert f"{PROJECT}/check_filter.js" in removed
    assert not (root / PROJECT / "check_filter.js").exists()


def _a_module_the_product_imports(root: Path) -> str:
    relative = _left_by(root, "defect_fix_2_4", "filters.ts", "diag.js")
    (root / relative).write_text("export const FILTERS = ['all', 'active', 'completed'] as const;\n")
    app = root / PROJECT / "src" / "App.tsx"
    app.write_text("import { FILTERS } from '../filters';\n" + app.read_text())
    return relative


def _a_script_the_manifest_names(root: Path) -> str:
    relative = _left_by(root, "defect_fix_2_7", "serve-preview.mjs", "diag2.mjs")
    manifest = root / PROJECT / "package.json"
    held = json.loads(manifest.read_text())
    held["scripts"]["preview"] = "node serve-preview.mjs"
    manifest.write_text(json.dumps(held, indent=2))
    return relative


def _a_configuration_a_tool_finds_by_its_name(root: Path) -> str:
    relative = _left_by(root, "defect_fix_2_7", "postcss.config.cjs", "diag.js")
    (root / relative).write_text("module.exports = { plugins: {} };\n")
    return relative


def _a_planned_module(root: Path) -> str:
    relative = _left_by(root, "specialist_testing_1", "filter-state.js", "diag.js")
    plan = root / "docs" / "technical_specification.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("## File Plan\n\n- `filter-state.js` - the filter the page shows\n")
    return relative


def _a_builder_s_module(root: Path) -> str:
    return _left_by(root, "specialist_ui_ux_0", "theme.js", "diag.js")


@pytest.mark.parametrize("arrange", [
    _a_module_the_product_imports, _a_script_the_manifest_names, _a_configuration_a_tool_finds_by_its_name,
    _a_planned_module, _a_builder_s_module,
])
def test_a_file_the_product_uses_or_plans_is_never_scratch_and_never_swept(tmp_path, arrange):
    root = _workspace(tmp_path)
    _the_fixers_probes(root)
    kept = arrange(root)

    assert not is_scratch(kept, root)
    assert kept not in clear_the_throwaways_left_behind(root)
    assert (root / kept).is_file()


def test_a_probe_the_product_comes_to_use_stops_being_scratch(tmp_path):
    root = _workspace(tmp_path)
    _the_fixers_probes(root)
    assert is_scratch(f"{PROJECT}/check_filter.js", root)
    app = root / PROJECT / "src" / "App.tsx"
    app.write_text("import './../check_filter.js';\n" + app.read_text())
    project_memory.record(root, f"{PROJECT}/src/App.tsx", "defect_fix_3_0")

    assert f"{PROJECT}/check_filter.js" not in clear_the_throwaways_left_behind(root)


def _write_as(root: Path, stage: str, name: str, probe: str) -> dict:
    with asked_for(stage):
        return write_approved_artifact(root, f"{PROJECT}/{name}", (PROBES / probe).read_text())


def test_a_fixer_creating_a_probe_is_told_once_to_name_it_or_delete_it(tmp_path):
    root = _workspace(tmp_path)

    first = _write_as(root, "defect_fix_2_7", "check_filter.js", "diag.js")
    second = _write_as(root, "defect_fix_2_7", "check_filter2.mjs", "diag2.mjs")

    note = first.get("note") or ""
    assert "check_filter.js" in note and "tmp-" in note and "delete" in note
    assert "tmp-" not in (second.get("note") or "")


def test_a_builder_creating_a_file_is_not_told_it_is_a_probe(tmp_path):
    root = _workspace(tmp_path)

    written = _write_as(root, "specialist_ui_ux_0", "check_filter.js", "diag.js")

    assert "probe" not in (written.get("note") or "")


def test_the_probe_note_uses_no_product_word(tmp_path):
    root = _workspace(tmp_path)

    note = _write_as(root, "defect_fix_2_4", "check_filter.js", "diag.js").get("note") or ""

    told = note[note.index("check_filter.js") - 1:]
    assert "tmp-" in told and not BANNED.search(told)


def test_a_file_a_fixer_s_command_created_is_recorded_as_its_own(tmp_path, monkeypatch):
    """A probe saved by a command, not a write tool, had no creator, so no rule could call it anyone's scratch."""
    from app.tools import sandbox
    from app.tools.agent_toolkit import build_terminal_command_tool

    root = _workspace(tmp_path)

    def a_command_that_saves_a_probe(**_: object) -> dict:
        (root / PROJECT / "check_filter.js").write_text((PROBES / "diag.js").read_text())
        return {"returncode": 0, "stdout": "", "stderr": "", "files_changed": [f"{PROJECT}/check_filter.js"]}

    monkeypatch.setattr(sandbox.SandboxExecutor, "execute", staticmethod(a_command_that_saves_a_probe))
    tool = build_terminal_command_tool(str(root), "defect_fix")
    with asked_for("defect_fix_2_7"):
        tool.invoke({"command": ["node", "--version"], "working_directory": PROJECT})

    assert project_memory.who_created(root, f"{PROJECT}/check_filter.js") == "defect_fix_2_7"
    assert is_scratch(f"{PROJECT}/check_filter.js", root)
