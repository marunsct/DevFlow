"""The gate's language service reads a whole batch, the product's own code first.

Measured live: a batch changed 22 code files and the gate read the first 12 by
name - migrations and page files - so the router, 19th, was never read. Its
imports of names nothing defined failed the service's start in three test
rounds running, one missing name a round, while one read would have named them
all. Pyright reads the whole project whichever file it is asked about, so the
file-by-file reads also cost a project-wide run each: 2 s a file, 45 s a batch.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.analysis import language_service as service
from app.graph import engineering


def _batch(tmp_path, monkeypatch, names):
    for name in names:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x = 1\n")
    monkeypatch.setattr(engineering.ci, "changed_since", lambda root, since: sorted(names))
    monkeypatch.setattr(engineering, "_what_the_compiler_says", lambda *a, **k: [])
    monkeypatch.setattr(engineering, "_what_the_manifests_do_not_declare", lambda *a, **k: [])


def test_a_broken_router_late_in_name_order_is_read_in_one_run(tmp_path, monkeypatch):
    names = [f"shop/migrations/versions/{n:03d}_step.py" for n in range(10)] + \
            [f"shop/frontend/Page{n}.tsx" for n in range(9)] + \
            ["shop/shop_pkg/routers/tasks.py", "shop/shop_pkg/main.py", "shop/tests/test_tasks.py"]
    _batch(tmp_path, monkeypatch, names)
    (tmp_path / "shop/shop_pkg/routers/tasks.py").write_text("x = 1\nfrom shop_pkg.auth import get_current_user\n")
    runs = []

    def diagnostics(project):
        runs.append(project)
        return [{"file": str(tmp_path / "shop/shop_pkg/routers/tasks.py"), "rule": "reportAttributeAccessIssue",
                 "severity": "error", "message": '"get_current_user" is unknown import symbol',
                 "range": {"start": {"line": 1}}}]

    monkeypatch.setattr(service, "_pyright_diagnostics", diagnostics, raising=False)
    monkeypatch.setattr(service, "underlined", lambda *a, **k: service.Underlined())
    monkeypatch.setattr("app.tools.repository.pinned_project_directory", lambda root: "shop")

    found = engineering.underlined_in_the_batch({}, str(tmp_path), "base")

    (defect,) = found
    assert defect.description.startswith('shop/shop_pkg/routers/tasks.py line 2: "get_current_user" is unknown import symbol')
    assert "`from shop_pkg.auth import get_current_user`" in defect.reproduction_steps
    assert "Pyright" in defect.actual_behavior
    assert runs == [tmp_path / "shop"], "one Pyright run reads every Python file of the batch"


def test_the_cap_on_file_by_file_reads_falls_on_tests_not_on_the_product(tmp_path, monkeypatch):
    names = [f"web/__tests__/t{n:02d}.test.ts" for n in range(engineering.MOST_FILES_UNDERLINED + 2)] + ["web/src/store.ts"]
    _batch(tmp_path, monkeypatch, names)
    read = []

    def underlined(root, target, content, project=None):
        read.append(target.relative_to(tmp_path).as_posix())
        if target.name == "store.ts":
            return SimpleNamespace(here=[{"line": 1, "message": "Cannot find name 'render'.", "text": "x = 1"}])
        return service.Underlined()

    monkeypatch.setattr(service, "underlined", underlined)

    found = engineering.underlined_in_the_batch({}, str(tmp_path), "base")

    assert [d.affected_files for d in found] == [["web/src/store.ts"]]
    assert read[0] == "web/src/store.ts" and len(read) == engineering.MOST_FILES_UNDERLINED
