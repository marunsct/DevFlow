"""Routes, tests and criteria are part of the code graph, and a fixer is localised from it (KG.4, LF.1514).

Before it, "tested by" was true only where an acceptance test imports the product's code: a service is tested over
HTTP, so in a Go, Java, Rust, Ruby or PHP notes service no file was tested by anything. A fixer's localisation scanned
the product's lines at each fix and named the file only, never the definition that answers; a Go route written
`"POST /notes"` (the method inside the quotes) was not read as a route at all (the Go file was found only through an
unrelated `"/notes/"` string beside the word "prefix"). A page product's tests named no file either.

The projects and suites are real products' files (`tests/captured/projects/README.md`); the failures are the
acceptance results those runs stored.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from app.analysis import project_graph

CAPTURED = Path(__file__).parent / "captured"
PROJECTS = CAPTURED / "projects"
SUITES = CAPTURED / "project-tests"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: The stored result of the Go product's run: the create route answered 404.
GO_FAILURE = ("api.spec.js:29:1 › [AC-1][AC-7][AC-8] POST /notes creates a note and returns 201 ─────────────────\n\n"
              "    Error: expect(received).toBe(expected) // Object.is equality\n\n    Expected: 201\n    Received: 404\n\n"
              "      36 |   });\n      37 |\n    > 38 |   expect(response.status()).toBe(201);\n"
              "         |                             ^\n"
              "      39 |   expect(response.headers()['content-type']).toContain('application/json');\n      40 |\n"
              "      41 |   const note = await response.json();\n"
              "        at /workspace/notes-api/acceptance/api.spec.js:38:29\n\n"
              "    Error Context: ../test-results/evidence/api--AC-1-AC-7-AC-8-POST-n-e95b0-ates-a-note-and-returns-201/"
              "error-context.md")
#: The stored result of the Rust product's run: fetching one note answered 500.
RUST_FAILURE = ("crud.spec.js:80:1 › [AC-3][AC-10] GET /notes/{id} returns the note or 404 ────────────────────────\n\n"
                "    Error: expect(received).toBe(expected) // Object.is equality\n\n    Expected: 200\n"
                "    Received: 500\n\n      81 |   // AC-3: fetch the note we created earlier — must exist\n"
                "      82 |   const getRes = await request.get(`/notes/${globalThis._createdNoteId}`);\n"
                "    > 83 |   expect(getRes.status()).toBe(200);\n         |                           ^\n      84 |\n"
                "      85 |   const note = await getRes.json();\n      86 |   expect(note.id).toBe(globalThis._createdNoteId);\n"
                "        at /workspace/notes-api/acceptance/crud.spec.js:83:27\n")
#: A stored page failure of the same brief as the captured page product, naming the control by its label.
PAGE_FAILURE = ("task-workflow.spec.js:183:1 › [AC-5][AC-12] Toggling while Active filter is shown removes item from view \n\n"
                "    TimeoutError: locator.check: Timeout 3000ms exceeded.\n    Call log:\n"
                "      - waiting for getByRole('listitem').first().getByRole('checkbox', { name: 'Done', exact: true })\n"
                "        2 × locator resolved to <input type=\"checkbox\" aria-label=\"Done\"/>\n"
                "        - attempting click action\n          - waiting for element to be visible, enabled and stable\n")
#: The stored result of the captured browser product's run: its rows had no inline edit control.
MARKUP_PAGE_FAILURE = (
    "tasks-ui.spec.js:59:1 › [AC-1][AC-5] a task can be added, edited inline with Save and deleted ────\n\n"
    "    TimeoutError: locator.click: Timeout 3000ms exceeded.\n    Call log:\n"
    "      - waiting for getByRole('listitem').filter({ hasText: 'AC5 flow original' }).getByRole('button', "
    "{ name: 'Edit', exact: true })\n\n\n"
    "      62 |   await addTask(page, 'AC5 flow original', 'AC5 flow desc');\n      63 |\n"
    "    > 64 |   await editButtonIn(page, 'AC5 flow original').click();\n"
    "         |                                                 ^\n"
    "      65 |   const row = rowFor(page, 'AC5 flow original');\n"
    "      66 |   await row.getByLabel('Title', { exact: true }).fill('AC5 flow edited');\n"
    "      67 |   await row.getByRole('button', { name: 'Save', exact: true }).click();\n")


def _project(tmp_path: Path, name: str, with_tests: bool = False) -> Path:
    """The captured project under a workspace whose pinned project directory it is; with its stored suite and unit
    tests laid over it when `with_tests`."""
    shutil.copytree(PROJECTS / name, tmp_path / name)
    if with_tests:
        shutil.copytree(SUITES / name, tmp_path / name, dirs_exist_ok=True)
    (tmp_path / ".project-directory").write_text(name)
    return tmp_path


#: (project, the file declaring a route, method, path, its line, the handler's file, name, first and last line) -
#: worked out by reading the files.
ROUTES = [
    ("go-notes-api", "server.go", "GET", "/notes/{id}", 20, "server.go", "getHandler", 84, 103),
    ("java-notes-api", "src/main/java/app/notes_api/controller/NoteController.java", "POST", "/notes", 30,
     "src/main/java/app/notes_api/controller/NoteController.java", "createNote", 30, 36),
    ("java-notes-api", "src/main/java/app/notes_api/controller/NoteController.java", "DELETE", "/notes/{id}", 58,
     "src/main/java/app/notes_api/controller/NoteController.java", "deleteNote", 58, 62),
    ("rust-notes-api", "src/router.rs", "DELETE", "/notes/{id}", 22, "src/handlers.rs", "delete_handler", 261, 288),
    ("ruby-notes-api", "app.rb", "PUT", "/notes/:id", 90, "app.rb", "", 90, 90),
    ("php-notes-api", "src/Service.php", "GET", "/notes/{id}", 97, "src/Service.php", "", 97, 97),
    ("csharp-notes-api", "src/App/Program.cs", "GET", "/notes/{id}", 101, "src/App/Program.cs", "", 101, 101),
]


@pytest.mark.parametrize(("project", "file", "method", "path", "line", "handler_file", "handler", "first", "last"),
                         ROUTES, ids=[f"{r[0]}:{r[2]} {r[3]}" for r in ROUTES])
def test_a_route_points_at_the_definition_that_handles_it(tmp_path, project, file, method, path, line, handler_file,
                                                          handler, first, last):
    graph = project_graph.build(_project(tmp_path, project))

    rows = [row[:7] for row in graph[f"{project}/{file}"].get("routes", [])]

    assert [method, path, line, f"{project}/{handler_file}", handler, first, last] in rows


#: (project, a file that answers requests, an acceptance test file that requests it, how many request it).
SERVICES = [
    ("go-notes-api", "server.go", "acceptance/api.spec.js", 1),
    ("java-notes-api", "src/main/java/app/notes_api/controller/NoteController.java", "acceptance/notes.spec.js", 1),
    ("rust-notes-api", "src/handlers.rs", "acceptance/crud.spec.js", 4),
    ("ruby-notes-api", "app.rb", "acceptance/notes_api.spec.js", 1),
    ("php-notes-api", "src/Service.php", "acceptance/api.spec.js", 1),
]


@pytest.mark.parametrize(("project", "file", "test", "files"), SERVICES, ids=[s[0] for s in SERVICES])
def test_a_service_s_handler_is_tested_by_the_acceptance_tests_that_request_it(tmp_path, project, file, test, files):
    root = _project(tmp_path, project, with_tests=True)

    shown = project_graph.neighbourhood(root, [f"{project}/{file}"], "H")

    assert f"tested by `{project}/{test}`" in shown
    assert not BANNED.search(shown)
    assert [counts["tests"] for counts in project_graph.reach(root, [f"{project}/{file}"]).values()] == [files]


def test_a_route_carries_the_criteria_of_the_tests_that_request_it(tmp_path):
    graph = project_graph.build(_project(tmp_path, "go-notes-api", with_tests=True))

    deleting = [row for row in graph["go-notes-api/server.go"]["routes"] if row[:2] == ["DELETE", "/notes/{id}"]]

    assert [row[7] for row in deleting] == [["AC-12", "AC-16", "AC-5"]]


def test_a_go_fixer_of_a_failing_request_is_told_the_handler_and_its_lines(tmp_path):
    from app.graph import localised_fix

    root = _project(tmp_path, "go-notes-api", with_tests=True)

    found = localised_fix.where(root, GO_FAILURE)
    shown = localised_fix.section(found)

    assert (found.found, found.how) == (["go-notes-api/server.go"], "route")
    assert "`POST /notes` is answered by `createHandler` in `go-notes-api/server.go`, lines 54-81" in shown
    assert localised_fix.files_in(shown) == ("go-notes-api/server.go", "go-notes-api/store/store.go")
    assert not BANNED.search(shown)


def test_a_route_declared_in_one_file_and_handled_in_another_names_both(tmp_path):
    from app.graph import localised_fix

    found = localised_fix.where(_project(tmp_path, "rust-notes-api", with_tests=True), RUST_FAILURE)

    assert found.found[:2] == ["rust-notes-api/src/handlers.rs", "rust-notes-api/src/router.rs"]
    assert any("`get_handler` in `rust-notes-api/src/handlers.rs`, lines 148-178" in line for line in found.handlers)


def test_a_page_s_selectors_point_at_the_files_that_render_their_text(tmp_path):
    graph = project_graph.build(_project(tmp_path, "react-to-do-list-app"))

    rendering = {file.removeprefix("react-to-do-list-app/"): node["renders"] for file, node in graph.items()
                 if node.get("renders")}

    assert rendering == {
        "src/components/FilterButtons.tsx": ["Active", "All", "Completed"],
        "src/components/TaskForm.tsx": ["Add task", "Description", "Title"],
        "src/components/TaskItem.tsx": ["Delete", "Done", "Edit", "Edit title", "Save"],
    }


def test_a_page_fixer_is_localised_to_the_file_that_renders_the_failing_control(tmp_path):
    from app.graph import localised_fix

    found = localised_fix.where(_project(tmp_path, "react-to-do-list-app"), PAGE_FAILURE)
    said = re.sub(r"`[^`]*`", "", localised_fix.section(found))

    assert (found.found, found.how) == (["react-to-do-list-app/src/components/TaskItem.tsx"], "page")
    assert not BANNED.search(said)


def test_a_page_whose_text_is_in_its_markup_is_localised_to_the_markup_and_the_scripts_it_loads(tmp_path):
    """The stored failure: the product rendered no inline edit control at all, so only the form's label it already
    renders (in the markup) places the failure; the change belongs in the script the markup loads."""
    from app.graph import localised_fix

    found = localised_fix.where(_project(tmp_path, "browser-to-do-list-app"), MARKUP_PAGE_FAILURE)

    assert (found.found, found.how) == (
        ["browser-to-do-list-app/index.html", "browser-to-do-list-app/src/main.js"], "page")
    assert found.files == ["browser-to-do-list-app/index.html", "browser-to-do-list-app/src/main.js",
                           "browser-to-do-list-app/src/storage.js", "browser-to-do-list-app/src/tasks.js"]


def test_a_unit_test_points_at_the_definitions_it_imports_and_names(tmp_path):
    root = _project(tmp_path, "java-notes-api", with_tests=True)
    test = "java-notes-api/src/test/java/app/notes_api/NoteServiceTest.java"
    service = "java-notes-api/src/main/java/app/notes_api/service/NoteService.java"

    graph = project_graph.build(root)

    assert sorted(name for file, name in graph[test]["references"] if file == service) == [
        "NoteService", "createNote", "deleteNote", "getById", "updateNote"]
    assert f"unit tests `{test}`" in project_graph.neighbourhood(root, [service], "H")


def test_a_route_with_its_method_inside_the_quotes_is_a_route():
    from app.acceptance.product_interface import declares_a_route

    assert declares_a_route('\tmux.HandleFunc("GET /notes/{id}", getHandler(s))')


def test_the_effects_say_how_many_calls_a_localised_fixer_made_before_its_first_write():
    records = [
        {"kind": "fixer_localised", "stage": "defect_fix_2_0", "how": "route"},
        {"kind": "tool_call", "stage": "defect_fix_2_0", "tool": "read_file"},
        {"kind": "tool_call", "stage": "defect_fix_2_0", "tool": "grep"},
        {"kind": "tool_call", "stage": "defect_fix_2_0", "tool": "edit_artifact"},
        {"kind": "tool_call", "stage": "defect_fix_2_0", "tool": "read_file"},
        {"kind": "fixer_localised", "stage": "defect_fix_2_1", "how": "none"},
        {"kind": "tool_call", "stage": "defect_fix_2_1", "tool": "read_file"},
    ]

    lines = project_graph.effects_lines(records)

    assert ("     2  KG.4 tool calls before a localised fixer's first write, by how: none 1 (median - calls, 1 wrote "
            "nothing), route 1 (median 2 calls, 0 wrote nothing)") in lines
