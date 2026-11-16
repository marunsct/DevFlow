"""A Python file is checked by Pyright as it is about to be written, not only once it is on disk (found on a run).

Measured on one run (a Python service): fixes rewrote the entry module to import `tasks_api.db` and
`tasks_api.routes`, modules the project did not have. The write-time refusal asked Pyright about content not yet on
disk, Pyright answered only for files as written, so it said nothing; each fix was committed, broke the start, was
measured and reverted - 13 reverts. JavaScript and TypeScript were checked as written; Python never was.
"""
from __future__ import annotations

import shutil

import pytest

from app.analysis import language_service as service

needs_pyright = pytest.mark.skipif(
    shutil.which("node") is None or service._pyright() is None,
    reason="no Pyright beside Node here (the worker image has one)",
)


def _project(tmp_path):
    project = tmp_path / "svc"
    (project / "pkg").mkdir(parents=True)
    (project / "pkg" / "__init__.py").write_text("")
    (project / "pkg" / "store.py").write_text("def add(a, b):\n    return a + b\n")
    target = project / "pkg" / "main.py"
    target.write_text("from pkg.store import add\n\nprint(add(1, 2))\n")
    return project, target


@needs_pyright
def test_content_not_yet_written_is_checked_as_it_would_be(tmp_path):
    project, target = _project(tmp_path)
    found = service.underlined_any(tmp_path, target, "import pkg.db as db\nfrom pkg.store import add\n", project)
    assert found is not None
    assert any("pkg.db" in f["message"] for f in found.here), found.here
    # The file on disk is untouched and nothing is left beside it.
    assert target.read_text().startswith("from pkg.store import add")
    assert sorted(p.name for p in (project / "pkg").iterdir()) == ["__init__.py", "main.py", "store.py"]


@needs_pyright
def test_right_content_not_yet_written_is_left_alone(tmp_path):
    project, target = _project(tmp_path)
    found = service.underlined_any(tmp_path, target, "from pkg.store import add\n\nprint(add(2, 3))\n", project)
    assert found is not None and found.here == []


@needs_pyright
def test_a_new_file_is_checked_too(tmp_path):
    project, _ = _project(tmp_path)
    found = service.underlined_any(tmp_path, project / "pkg" / "routes.py", "from pkg.handlers import H\n", project)
    assert found is not None and any("pkg.handlers" in f["message"] for f in found.here)
    assert not (project / "pkg" / "routes.py").exists()


def _workspace(tmp_path, planned):
    import json

    from app.tools import repository

    root = tmp_path
    (root / ".harness").mkdir()
    project, target = _project(root)
    (root / repository.PROJECT_MARKER).write_text("svc")
    (root / repository.WORK_ORDER_FILES).write_text(json.dumps({path: "drafting" for path in planned}))
    return root, project, target


@needs_pyright
def test_a_fix_importing_a_module_the_project_lacks_is_refused_once_every_planned_file_is_written(tmp_path):
    from app.tools import repository

    root, _, target = _workspace(tmp_path, ["svc/pkg/main.py", "svc/pkg/store.py"])
    with pytest.raises(repository.RepositoryToolError, match="language service is sure of"):
        repository.write_approved_artifact(str(root), "svc/pkg/main.py",
                                           "import pkg.db as db\nfrom pkg.store import add\n")
    assert "pkg.db" not in target.read_text()


@needs_pyright
def test_while_a_planned_file_is_unwritten_the_import_waits_for_it(tmp_path):
    from app.tools import repository

    root, _, target = _workspace(tmp_path, ["svc/pkg/main.py", "svc/pkg/db.py"])
    repository.write_approved_artifact(str(root), "svc/pkg/main.py", "import pkg.db as db\nfrom pkg.store import add\n")
    assert "pkg.db" in target.read_text()


@needs_pyright
@pytest.mark.parametrize("stage,refused", [("defect_fix_1_0", True), ("drafting", False)])
def test_with_no_plan_recorded_a_fix_stage_is_refused_and_drafting_is_not(tmp_path, monkeypatch, stage, refused):
    from app.observability import transcript
    from app.tools import repository

    root, _, target = _workspace(tmp_path, [])
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: stage)
    write = lambda: repository.write_approved_artifact(str(root), "svc/pkg/main.py",
                                                       "import pkg.db as db\nfrom pkg.store import add\n")
    if refused:
        with pytest.raises(repository.RepositoryToolError, match="language service is sure of"):
            write()
    else:
        write()
        assert "pkg.db" in target.read_text()
