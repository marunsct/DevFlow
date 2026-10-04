"""What an IDE would underline in a JavaScript file, from the TypeScript language service.

The failures this harness's runs met only at test time - `init is not defined`,
`render is not defined`, a test importing a name its module never exported -
are what an IDE shows before anything runs. Only the certain ones are
reported: see `app.analysis.language_service` for the measurement.

The service needs Node and a TypeScript compiler; the worker image installs
one beside Node. Where neither exists these tests that need it are skipped and
the write path falls back to `app.analysis.local_imports`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.analysis import language_service as service
from app.analysis.typescript_parse import compiler_for

needs_the_compiler = pytest.mark.skipif(
    shutil.which("node") is None or compiler_for(None) is None,
    reason="no TypeScript compiler beside Node here (the worker image has one)",
)


def _project(tmp_path: Path, files: dict[str, str]) -> Path:
    project = tmp_path / "app"
    for name, text in files.items():
        target = project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return project


def test_findings_are_grouped_by_what_is_wrong() -> None:
    found = service.Underlined(here=[
        {"line": 3, "code": 2304, "message": "Cannot find name 'render'.", "text": "render(a);"},
        {"line": 9, "code": 2304, "message": "Cannot find name 'render'.", "text": "render(b);"},
    ])
    note = found.note()
    assert "lines 3, 9: Cannot find name 'render'." in note and "ReferenceError" in note
    assert service.Underlined().note() == ""


@needs_the_compiler
def test_a_name_nothing_defines_is_underlined_and_a_comment_or_typeof_is_not(tmp_path) -> None:
    project = _project(tmp_path, {"src/ui.js": ""})
    content = (
        "/** @returns {Task[]} */\n"
        "export function show() {\n"
        "  if (typeof global !== 'undefined') return [];\n"
        "  return render(items);\n"
        "}\n"
    )

    found = service.underlined(tmp_path, project / "src" / "ui.js", content, project)

    names = sorted(f["message"] for f in found.here)
    assert names == ["Cannot find name 'items'.", "Cannot find name 'render'."]


@needs_the_compiler
def test_an_import_of_a_missing_export_or_file_is_underlined_in_both_directions(tmp_path) -> None:
    project = _project(tmp_path, {
        "src/store.js": "export function add(x) { return x; }\n",
        "tests/store.test.js": "import { add, remove } from '../src/store.js';\n",
        "src/main.js": "",
    })
    main = "import { add } from './store.js';\nimport { draw } from './view.js';\nadd(1);\n"

    found = service.underlined(tmp_path, project / "src" / "main.js", main, project)
    assert any("view.js" in f["message"] for f in found.here)

    # Removing an export breaks the files that import it.
    found = service.underlined(tmp_path, project / "src" / "store.js", "export const other = 1;\n", project)
    assert any(f["file"].endswith("store.test.js") for f in found.elsewhere)


@needs_the_compiler
def test_a_test_file_is_checked_for_its_imports_not_for_the_runner_s_globals(tmp_path) -> None:
    project = _project(tmp_path, {"tests/a.test.js": ""})
    found = service.underlined(
        tmp_path, project / "tests" / "a.test.js", "describe('x', () => { expect(1).toBe(1); });\n", project,
    )
    assert found.here == []


def test_without_a_compiler_it_says_it_cannot_tell(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.analysis.typescript_parse.compiler_for", lambda path: None)
    project = _project(tmp_path, {"src/a.js": ""})
    assert service.underlined(tmp_path, project / "src" / "a.js", "x();\n", project) is None
    assert service.underlined(tmp_path, project / "notes.md", "x", project) is None


def test_where_the_code_runs_comes_from_the_pack() -> None:
    from app.stacks import pack_named

    assert pack_named("browser-javascript").code_runs_in == service.BROWSER
    assert pack_named("node-http-api").code_runs_in == service.NODE
    assert pack_named("fullstack-node").code_runs_in == service.BOTH


def _committed(tmp_path: Path, files: dict[str, str], message: str) -> str:
    import subprocess

    for name, text in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", message], cwd=tmp_path, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()


def test_at_the_gate_what_is_still_underlined_becomes_a_defect(tmp_path, monkeypatch) -> None:
    """At a write it is a note - another work order may be about to define the
    name. Once the batch is done, it is a bug."""
    import subprocess

    from app.graph import engineering

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    before = _committed(tmp_path, {"app/src/a.js": "export const a = 1;\n"}, "before")
    _committed(tmp_path, {"app/src/a.js": "export const a = render();\n", "app/notes.md": "x"}, "batch")
    seen = []

    def fake(root, target, content, project=None):
        seen.append(Path(target).name)
        return service.Underlined(here=[
            {"line": 1, "code": 2304, "message": "Cannot find name 'render'.", "text": "export const a = render();"},
        ])

    monkeypatch.setattr("app.analysis.language_service.underlined", fake)
    state = {"milestone_plan": None}

    (defect,) = engineering.underlined_in_the_batch(state, str(tmp_path), before)

    assert seen == ["a.js"]
    assert defect.description.startswith("app/src/a.js line 1: Cannot find name 'render'.")
    assert defect.affected_files == ["app/src/a.js"] and defect.severity == "major"


@needs_the_compiler
def test_the_gate_finds_them_with_the_real_service(tmp_path) -> None:
    import subprocess

    from app.graph import engineering

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    before = _committed(tmp_path, {"app/src/a.js": "export const a = 1;\n"}, "before")
    _committed(tmp_path, {"app/src/a.js": "export const a = render();\n"}, "batch")

    defects = engineering.underlined_in_the_batch({"milestone_plan": None}, str(tmp_path), before)

    assert [d.affected_files for d in defects] == [["app/src/a.js"]]


# --- Python, through Pyright ---------------------------------------------------------

needs_pyright = pytest.mark.skipif(
    shutil.which("node") is None or service._pyright() is None,
    reason="no Pyright beside Node here (the worker image has one)",
)


@needs_pyright
def test_python_names_and_imports_are_underlined_as_an_ide_would(tmp_path) -> None:
    project = _project(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/store.py": "def add(a, b):\n    return a + b\n",
    })
    main = (
        "from pkg.store import add, remove\n"
        "from .missing import thing\n"
        "import json\n\n"
        "def run(items):\n"
        "    if 'x' in globals():\n"
        "        pass\n"
        "    return render(items) + add(1, 2)\n"
    )
    target = project / "pkg" / "main.py"
    target.write_text(main)

    found = service.underlined_any(tmp_path, target, main, project)

    messages = sorted(f["message"] for f in found.here)
    assert len(messages) == 3, messages
    assert any("remove" in m for m in messages) and any("render" in m for m in messages)
    assert any(".missing" in m for m in messages)


@needs_pyright
def test_python_code_that_is_right_is_left_alone(tmp_path) -> None:
    reference = Path(__file__).resolve().parent.parent / "benchmarks" / "textkit-lib" / "reference"
    for path in sorted(reference.rglob("*.py")):
        found = service.underlined_any(tmp_path, path, path.read_text(), reference)
        assert found is not None and found.here == [], (path, found.here)


def test_python_is_answered_only_for_the_file_as_written(tmp_path) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n")
    assert service.python_underlined(tmp_path, target, "x = 2\n") is None
