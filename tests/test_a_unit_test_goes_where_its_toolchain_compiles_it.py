"""A unit test goes where its toolchain compiles it, and a file that is not code is given none.

Measured on one Java run: the testing work order the harness wrote named every test straight under the unit directory
(`src/test/NoteServiceTest.java`); Maven compiles only the tests under `src/test/java/`, so no unit test ever ran and
the run's unit command printed nothing to count. The same work order gave the manifest `pom.xml` a test,
`src/test/pomTest.java`.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.analysis import work_orders
from app.analysis.work_orders import with_a_testing_work_order
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CODE = "notes-api/src/main/java/app/notes_api"


def _plan(files):
    order = SpecialistTask(specialist_role="backend", title="Routes", task_description="Serve the notes.", files=files,
                           interfaces=["GET /notes -> 200"], test_cases=["given no notes, GET /notes answers []"])
    return MilestonePlanOutput.model_construct(selected_sprint_goal="Notes", delegated_tasks=[order])


def _testing_files(monkeypatch, tmp_path, pack, files):
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {}))
    monkeypatch.setattr(work_orders, "_pinned_project_directory", lambda root: "notes-api")
    plan, added = with_a_testing_work_order(_plan(files), tmp_path)
    assert added
    return plan.delegated_tasks[-1].files


def test_a_java_test_mirrors_its_code_s_package_and_the_manifest_gets_none(monkeypatch, tmp_path):
    files = _testing_files(monkeypatch, tmp_path, pack_named("java-spring-api"), [
        f"{CODE}/service/NoteService.java", f"{CODE}/Application.java", "notes-api/pom.xml",
        "notes-api/src/main/resources/application.properties",
    ])
    assert files == ["notes-api/src/test/java/app/notes_api/service/NoteServiceTest.java",
                     "notes-api/src/test/java/app/notes_api/ApplicationTest.java"]


def test_a_pack_whose_tests_do_not_mirror_its_code_names_them_as_before(monkeypatch, tmp_path):
    pack = SimpleNamespace(unit_dir="tests", unit_pattern="*.test.ts", unit_test=("npm", "test"))
    files = _testing_files(monkeypatch, tmp_path, pack, ["notes-api/src/app.ts", "notes-api/package.json"])
    assert files == ["notes-api/tests/app.test.ts"]


def test_a_test_outside_the_compiled_root_is_no_unit_test(tmp_path):
    from app.graph.delivery import _a_unit_test_file_exists

    pack = pack_named("java-spring-api")
    project = tmp_path / "notes-api"
    (project / "src/test").mkdir(parents=True)
    (project / "src/test/NoteServiceTest.java").write_text("class NoteServiceTest {}")
    assert not _a_unit_test_file_exists(project, pack)
    placed = project / "src/test/java/app/notes_api/NoteServiceTest.java"
    placed.parent.mkdir(parents=True)
    placed.write_text("class NoteServiceTest {}")
    assert _a_unit_test_file_exists(project, pack)


def test_every_builder_is_told_where_a_test_goes(tmp_path):
    from app.agents.shared_facts import facts_from_the_workspace

    contract.write(tmp_path, pack_named("java-spring-api"), "notes-api", "Notes", scaffolded=True)
    (tmp_path / "notes-api").mkdir(exist_ok=True)
    told = [line for line in facts_from_the_workspace(tmp_path) if "mirrors its code" in line]
    assert told == ["- A unit test's path mirrors its code's: the test of `notes-api/src/main/java/<folders>/<Name>` is "
                    "`notes-api/src/test/java/<the same folders>/` - only tests there are compiled and run."]
    assert not BANNED.search(told[0])


def test_a_pack_that_names_no_mirror_tells_nothing_more(tmp_path):
    from app.agents.shared_facts import facts_from_the_workspace

    contract.write(tmp_path, pack_named("python-http-api"), "notes-api", "Notes", scaffolded=True)
    (Path(tmp_path) / "notes-api").mkdir(exist_ok=True)
    assert not [line for line in facts_from_the_workspace(tmp_path) if "mirrors its code" in line]
