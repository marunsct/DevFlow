"""An import no manifest declares is one bundled defect at the CI gate.

Measured: one run's product imported `jsdom` under an empty
`devDependencies`, a full `node_modules` and a lockfile of thirty-nine
packages - the bare install had landed it somewhere the product's own
commands never read, and a clean install (`npm ci`) provides none of it.
The reconciliation is deterministic - parse the imports, read the
manifests, name the gap - and the CI gate bundles the gaps into one
defect for the fixer instead of a model discovering them in a failing
runner (Initiative K.4).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.analysis import dependency_drift

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def _a_javascript_project(tmp_path: Path, *, manifest: dict | None, code: str) -> Path:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    if manifest is not None:
        (project / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    (project / "src" / "app.js").write_text(code, encoding="utf-8")
    return project


def test_a_javascript_import_no_manifest_declares_is_found(tmp_path: Path) -> None:
    project = _a_javascript_project(
        tmp_path,
        manifest={"dependencies": {"express": "^4.0.0"}},
        code='import express from "express";\nimport { JSDOM } from "jsdom";\n',
    )

    found = dependency_drift.undeclared(project)

    assert [(name, lang) for name, _, lang in found] == [("jsdom", "javascript")]
    assert found[0][1] == str(Path("src") / "app.js")


def test_a_dev_dependency_is_declared(tmp_path: Path) -> None:
    project = _a_javascript_project(
        tmp_path,
        manifest={"devDependencies": {"@playwright/test": "^1.40.0"}},
        code='import { test } from "@playwright/test";\n',
    )

    assert dependency_drift.undeclared(project) == []


def test_a_scoped_package_is_named_whole(tmp_path: Path) -> None:
    project = _a_javascript_project(
        tmp_path,
        manifest={"dependencies": {}},
        code='import { Hono } from "hono";\nimport x from "@acme/widgets/gear";\n',
    )

    names = sorted(name for name, _, _ in dependency_drift.undeclared(project))

    assert names == ["@acme/widgets", "hono"]


def test_without_a_manifest_there_is_nothing_to_reconcile_against(tmp_path: Path) -> None:
    project = _a_javascript_project(
        tmp_path, manifest=None, code='import { JSDOM } from "jsdom";\n'
    )

    assert dependency_drift.undeclared(project) == []


def test_node_builtins_and_relative_specifiers_are_not_dependencies(tmp_path: Path) -> None:
    project = _a_javascript_project(
        tmp_path,
        manifest={"dependencies": {}},
        code=(
            'import fs from "node:fs";\nimport path from "path";\n'
            'import { test } from "node:test";\nimport store from "./store.mjs";\n'
            'import data from "#data";\n'
        ),
    )

    assert dependency_drift.undeclared(project) == []


def test_a_python_import_no_manifest_declares_is_found_by_its_distribution_name(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (project / "app.py").write_text(
        "import fastapi\nimport yaml\nfrom PIL import Image\n", encoding="utf-8"
    )

    found = dependency_drift.undeclared(project)

    # The names a fixer must declare are the distributions', not the imports'.
    assert sorted((name, lang) for name, _, lang in found) == [
        ("pillow", "python"),
        ("pyyaml", "python"),
    ]


def test_python_stdlib_and_project_modules_are_not_dependencies(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "requirements.txt").write_text("flask\n", encoding="utf-8")
    (project / "helper.py").write_text("", encoding="utf-8")
    (project / "src" / "app.py").write_text(
        "import os, sys, json\nimport helper\nimport flask\nfrom pathlib import Path\n",
        encoding="utf-8",
    )

    assert dependency_drift.undeclared(project) == []


def test_a_dash_suffixed_distribution_declares_its_import(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text("psycopg2-binary==2.9\n", encoding="utf-8")
    (project / "db.py").write_text("import psycopg2\n", encoding="utf-8")

    assert dependency_drift.undeclared(project) == []


def test_a_pyproject_manifest_is_read(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "notes"\ndependencies = [\n  "flask>=3",\n]\n',
        encoding="utf-8",
    )
    (project / "app.py").write_text("import flask\nimport requests\n", encoding="utf-8")

    found = dependency_drift.undeclared(project)

    assert [(name, lang) for name, _, lang in found] == [("requests", "python")]


def test_the_gate_bundles_the_drift_into_one_defect(tmp_path: Path) -> None:
    """Every undeclared import of a batch rides one defect, named by package
    and file - not one defect per import, which is how thirteen defects from
    one root cause were measured."""
    import inspect

    from app.graph import engineering

    source = inspect.getsource(engineering)

    assert "_what_the_manifests_do_not_declare" in source
    bundled = inspect.getsource(engineering._what_the_manifests_do_not_declare)
    assert "dependency_drift.undeclared" in bundled
    gate = inspect.getsource(engineering.underlined_in_the_batch)
    assert "_what_the_manifests_do_not_declare" in gate


def test_the_defect_text_is_plain_language() -> None:
    from app.agents.specialists import ReportedDefect

    defect = dependency_drift.the_bundled_defect(
        [("jsdom", "src/app.js", "javascript"), ("pyyaml", "tools/notes.py", "python")],
        owner="backend",
    )

    assert isinstance(defect, ReportedDefect)
    assert "jsdom" in defect.description and "pyyaml" in defect.description
    assert "no manifest declares" in defect.description
    assert defect.severity == "major"
    assert defect.affected_files == ["package.json", "requirements.txt"]
    text = " ".join(str(v) for v in defect.model_dump().values() if v)
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", text, re.IGNORECASE), word


def _installed(project, name, version, *, tops=(), requires=()):
    info = project / ".venv" / "lib" / "python3.12" / "site-packages" / f"{name.replace('-', '_')}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
                                   + "".join(f"Requires-Dist: {r}\n" for r in requires))
    if tops:
        (info / "top_level.txt").write_text("\n".join(tops) + "\n")


def test_an_import_the_installed_packages_name_and_a_required_one_are_declared(tmp_path):
    """Measured on one run: `jose` (what `python-jose` installs) and `starlette` (what
    `fastapi` requires) were reported undeclared, and a fixer that declared `jose` would
    install an unrelated package of that name."""
    from app.analysis import dependency_drift

    project = tmp_path / "shop"
    (project / "shop_pkg").mkdir(parents=True)
    (project / "pyproject.toml").write_text(
        '[project]\nname = "shop"\ndependencies = ["fastapi>=0.149", "python-jose[cryptography]>=3.5.0"]\n')
    (project / "shop_pkg" / "auth.py").write_text(
        "from jose import jwt\nfrom starlette.middleware import Middleware\nimport requests\n")
    _installed(project, "python-jose", "3.5.0", tops=("jose",))
    _installed(project, "fastapi", "0.149.0", requires=("starlette>=0.46.0", "pydantic>=2", 'httpx; extra == "all"'))
    _installed(project, "starlette", "1.9.0", tops=("starlette",))

    found = dependency_drift.undeclared(project)

    assert [name for name, _, _ in found] == ["requests"]


def test_a_bundled_defect_raised_before_is_closed_once_the_reconciliation_finds_them_declared(tmp_path):
    """Measured live: the defect was raised by the reconciliation before it read the installed
    packages, and two fixers in turn "declared" `jose` - each broke the product and was reverted."""
    from app.analysis import dependency_drift
    from app.graph import engineering

    project = tmp_path / "shop"
    (project / "shop_pkg").mkdir(parents=True)
    (tmp_path / ".project-directory").write_text("shop\n")
    (project / "pyproject.toml").write_text('[project]\nname = "shop"\ndependencies = ["python-jose>=3.5.0"]\n')
    (project / "shop_pkg" / "auth.py").write_text("from jose import jwt\nimport requests\n")
    _installed(project, "python-jose", "3.5.0", tops=("jose",))
    stale = dependency_drift.the_bundled_defect([("jose", "shop_pkg/auth.py", "python")], owner="backend")
    real = dependency_drift.the_bundled_defect([("requests", "shop_pkg/auth.py", "python")], owner="backend")

    assert "declared now" in engineering.no_longer_underlined(str(tmp_path), stale.description)
    assert engineering.no_longer_underlined(str(tmp_path), real.description) == ""


def test_the_defect_names_the_manifests_where_the_change_is(tmp_path) -> None:
    """Measured on one gate run: it named the importing files, and the fix rewrote them, not the manifests."""
    (tmp_path / "requirements-dev.txt").write_text("pytest\n")
    (tmp_path / "package.json").write_text("{}")

    defect = dependency_drift.the_bundled_defect(
        [("sqlalchemy", "shop/database.py", "python"), ("axios", "src/api.ts", "javascript"),
         ("bcrypt", "shop/auth.py", "python")],
        owner="backend", project=tmp_path,
    )

    assert defect.affected_files == ["requirements-dev.txt", "package.json"]


def test_a_cause_leads_the_symptoms_it_is_merged_with() -> None:
    from app.agents.specialists import ReportedDefect
    from app.graph.workflow import _one_defect_per_cause

    symptom = ReportedDefect(
        description="`shop/acceptance/orders.spec.js` fails. Its output ends: No module named `sqlalchemy`",
        severity="major", reproduction_steps="Run the suite.", expected_behavior="It passes.",
        actual_behavior="ModuleNotFoundError", affected_files=["shop/database.py"], owner="backend")
    cause = dependency_drift.the_bundled_defect([("sqlalchemy", "shop/database.py", "python")], owner="backend")
    cause = cause.model_copy(update={"affected_files": ["requirements.txt", "shop/database.py"]})

    merged = _one_defect_per_cause([symptom, cause])

    assert len(merged) == 1
    assert merged[0].description.startswith(dependency_drift.OPENING)
    assert merged[0].affected_files[0] == "requirements.txt"

