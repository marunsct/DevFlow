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


def test_the_gate_names_no_language_of_its_own():
    """Owner, 2026-10-20: language-specific handling lives with the language's own service,
    so the gate treats every language alike. The first version tested for `.py` and named
    Pyright in the gate itself."""
    import inspect

    source = inspect.getsource(engineering.underlined_in_the_batch)

    assert ".py" not in source and "Pyright" not in source and "TypeScript" not in source
    assert service.service_name("app/x.py") == "Pyright"
    assert service.service_name("web/x.ts") == "the TypeScript language service"


def test_the_cap_counts_files_so_one_file_s_findings_leave_room_for_the_rest(tmp_path, monkeypatch):
    """Measured on one gate run: a schemas module's twelve unknown imports would take every place, and the
    router that stopped the service was met a round later."""
    names = ["shop/shop_pkg/schemas/__init__.py", "shop/shop_pkg/routers/auth.py"]
    _batch(tmp_path, monkeypatch, names)
    many = [{"file": str(tmp_path / names[0]), "rule": "reportAttributeAccessIssue", "severity": "error",
             "message": f'"Schema{n}" is unknown import symbol', "range": {"start": {"line": n}}}
            for n in range(engineering.MOST_UNDERLINED_DEFECTS + 4)]
    router = {"file": str(tmp_path / names[1]), "rule": "reportAttributeAccessIssue", "severity": "error",
              "message": '"get_db" is unknown import symbol', "range": {"start": {"line": 0}}}
    monkeypatch.setattr(service, "_pyright_diagnostics", lambda project: [*many, router], raising=False)
    monkeypatch.setattr("app.tools.repository.pinned_project_directory", lambda root: "shop")

    found = engineering.underlined_in_the_batch({}, str(tmp_path), "base")

    assert any("get_db" in d.description for d in found)
    assert sum("Schema" in d.description for d in found) == engineering.MOST_UNDERLINED_DEFECTS + 4


def test_a_name_several_files_import_from_a_module_that_lacks_it_names_the_module(tmp_path, monkeypatch):
    """Measured on one gate run: five routers imported `get_settings` from a settings module that defined
    `Settings` and `settings`; three rounds rewrote the importers and never the module."""
    names = ["shop/shop_pkg/routers/auth.py", "shop/shop_pkg/routers/tasks.py"]
    _batch(tmp_path, monkeypatch, names)
    (tmp_path / "shop/shop_pkg/__init__.py").write_text("")
    (tmp_path / "shop/shop_pkg/config.py").write_text("class Settings:\n    pass\n\nsettings = Settings()\n")
    for name in names:
        (tmp_path / name).write_text("from shop_pkg.config import get_settings\n")
    monkeypatch.setattr(service, "_pyright_diagnostics", lambda project: [
        {"file": str(tmp_path / name), "rule": "reportAttributeAccessIssue", "severity": "error",
         "message": '"get_settings" is unknown import symbol', "range": {"start": {"line": 0}}} for name in names
    ], raising=False)
    monkeypatch.setattr("app.tools.repository.pinned_project_directory", lambda root: "shop")

    found = engineering.underlined_in_the_batch({}, str(tmp_path), "base")

    assert len(found) == 2
    for defect in found:
        assert defect.affected_files[0] == "shop/shop_pkg/config.py"
        assert "`Settings`, `settings`" in defect.expected_behavior and "2 file(s)" in defect.expected_behavior
