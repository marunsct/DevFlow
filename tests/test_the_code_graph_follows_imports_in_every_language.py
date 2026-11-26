"""The code graph reads definitions and imports from each file's syntax tree, in every language of the table (KG.2).

Before it, the graph followed imports in Python and JavaScript/TypeScript only: in a Go, Java, Kotlin, C#, Rust, Ruby
or PHP product every file imported nothing and was imported by nothing, so a fixer was told no file its handler
imports, a sliced memory held only the files named, and the map ranked every module as used by none. Definitions came
from one line pattern for all of them, which read Ruby's `def self.create_note` as a definition of `self`.

The projects are real products' files (`tests/captured/projects/README.md`; Kotlin's is the one written by hand).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.analysis import project_graph

PROJECTS = Path(__file__).parent / "captured" / "projects"


def _built(tmp_path: Path, name: str) -> dict:
    shutil.copytree(PROJECTS / name, tmp_path / name)
    (tmp_path / ".project-directory").write_text(name)
    return project_graph.build(tmp_path)


#: (project, a file, exactly the project files it imports) - worked out by reading the files.
EDGES = [
    ("go-notes-api", "server.go", ["store/store.go"]),
    ("go-notes-api", "main.go", ["store/store.go"]),
    ("java-notes-api", "src/main/java/app/notes_api/service/NoteService.java", [
        "src/main/java/app/notes_api/exception/ResourceNotFoundException.java",
        "src/main/java/app/notes_api/model/Note.java",
        "src/main/java/app/notes_api/repository/NoteRepository.java",
    ]),
    ("java-notes-api", "src/main/java/app/notes_api/controller/NoteController.java", [
        "src/main/java/app/notes_api/dto/NoteRequest.java",
        "src/main/java/app/notes_api/model/Note.java",
        "src/main/java/app/notes_api/service/NoteService.java",
    ]),
    ("kotlin-notes-api", "src/main/kotlin/app/notes_api/service/NoteService.kt", [
        "src/main/kotlin/app/notes_api/exception/ResourceNotFoundException.kt",
        "src/main/kotlin/app/notes_api/model/Note.kt",
        "src/main/kotlin/app/notes_api/repository/NoteRepository.kt",
    ]),
    ("csharp-notes-api", "src/App/Program.cs", ["src/App/Data/NotesStore.cs", "src/App/Models/Note.cs"]),
    ("csharp-notes-api", "src/App/Data/NotesStore.cs", ["src/App/Models/Note.cs"]),
    ("rust-notes-api", "src/lib.rs", ["src/handlers.rs", "src/models.rs", "src/router.rs", "src/state.rs"]),
    ("rust-notes-api", "src/router.rs", ["src/handlers.rs", "src/state.rs"]),
    ("rust-notes-api", "src/main.rs", ["src/lib.rs"]),
    ("ruby-notes-api", "app.rb", ["lib/notes_api.rb"]),
    ("ruby-notes-api", "lib/notes_api.rb", ["lib/notes_api/db.rb", "lib/notes_api/service.rb"]),
    ("php-notes-api", "src/Handlers/GetNoteHandler.php", [
        "src/Domain/NoteId.php", "src/Infrastructure/NoteRepository.php",
    ]),
    ("php-notes-api", "public/index.php", ["src/Service.php"]),
]


@pytest.mark.parametrize(("project", "file", "imports"), EDGES, ids=[f"{p}:{f}" for p, f, _ in EDGES])
def test_a_file_s_imports_are_the_project_files_it_names(tmp_path, project, file, imports):
    graph = _built(tmp_path, project)

    assert graph[f"{project}/{file}"]["imports"] == [f"{project}/{i}" for i in imports]


@pytest.mark.parametrize(("project", "file", "importers"), [
    ("go-notes-api", "store/store.go", ["main.go", "server.go"]),
    ("java-notes-api", "src/main/java/app/notes_api/model/Note.java", [
        "src/main/java/app/notes_api/controller/NoteController.java",
        "src/main/java/app/notes_api/repository/NoteRepository.java",
        "src/main/java/app/notes_api/service/NoteService.java",
    ]),
    ("rust-notes-api", "src/state.rs", ["src/handlers.rs", "src/lib.rs", "src/router.rs"]),
    ("ruby-notes-api", "lib/notes_api/db.rb", ["lib/notes_api.rb", "lib/notes_api/service.rb"]),
])
def test_a_file_knows_what_imports_it(tmp_path, project, file, importers):
    graph = _built(tmp_path, project)

    assert sorted(graph[f"{project}/{file}"]["imported_by"]) == [f"{project}/{i}" for i in importers]


def test_a_namespace_opened_whole_names_only_the_files_whose_names_are_used(tmp_path):
    """A `using` opens a namespace whole; every file of it as a neighbour would swamp a large codebase's graph."""
    models = tmp_path / "csharp-notes-api" / "src" / "App" / "Models"
    shutil.copytree(PROJECTS / "csharp-notes-api", tmp_path / "csharp-notes-api")
    (models / "Archive.cs").write_text("namespace App.Models;\n\npublic class Archive\n{\n}\n")
    (tmp_path / ".project-directory").write_text("csharp-notes-api")

    graph = project_graph.build(tmp_path)

    assert graph["csharp-notes-api/src/App/Program.cs"]["imports"] == [
        "csharp-notes-api/src/App/Data/NotesStore.cs", "csharp-notes-api/src/App/Models/Note.cs"]


def test_an_import_of_a_package_from_outside_the_project_names_no_file(tmp_path):
    graph = _built(tmp_path, "java-notes-api")

    assert graph["java-notes-api/src/main/java/app/notes_api/Application.java"]["imports"] == []


@pytest.mark.parametrize(("project", "file", "row"), [
    ("go-notes-api", "store/store.go", ["method", "Load", 48, 77, "Store"]),
    ("go-notes-api", "store/store.go", ["struct", "Store", 29, 35, ""]),
    ("java-notes-api", "src/main/java/app/notes_api/service/NoteService.java", ["method", "createNote", 20, 27, "NoteService"]),
    ("csharp-notes-api", "src/App/Data/NotesStore.cs", ["method", "GetById", 35, 41, "NotesStore"]),
    ("rust-notes-api", "src/lib.rs", ["function", "app", 13, 18, ""]),
    ("ruby-notes-api", "lib/notes_api/service.rb", ["method", "create_note", 8, 21, "Service"]),
    ("php-notes-api", "src/Service.php", ["method", "createApp", 34, 118, "Service"]),
    ("kotlin-notes-api", "src/main/kotlin/app/notes_api/service/NoteService.kt", ["method", "getAll", 16, 17, "NoteService"]),
])
def test_each_definition_says_its_kind_its_lines_and_what_it_sits_in(tmp_path, project, file, row):
    graph = _built(tmp_path, project)

    assert row in graph[f"{project}/{file}"]["definitions"]


def test_a_ruby_singleton_method_is_defined_by_its_own_name(tmp_path):
    graph = _built(tmp_path, "ruby-notes-api")

    defines = graph["ruby-notes-api/lib/notes_api/service.rb"]["defines"]
    assert "create_note" in defines and "self" not in defines


def test_a_file_the_grammar_cannot_wholly_read_still_lists_its_definitions(tmp_path):
    store = tmp_path / "csharp-notes-api" / "src" / "App" / "Data" / "NotesStore.cs"
    text = (PROJECTS / "csharp-notes-api/src/App/Data/NotesStore.cs").read_text()
    broken = text.replace("public Note? GetById(int id)\n    {", "public Note? GetById(int id)\n    {{ ((", 1)
    assert broken != text
    shutil.copytree(PROJECTS / "csharp-notes-api", tmp_path / "csharp-notes-api")
    store.write_text(broken)
    (tmp_path / ".project-directory").write_text("csharp-notes-api")

    graph = project_graph.build(tmp_path)

    names = [row[1] for row in graph["csharp-notes-api/src/App/Data/NotesStore.cs"]["definitions"]]
    assert "Delete" in names and "Save" in names
    assert graph["csharp-notes-api/src/App/Data/NotesStore.cs"]["imports"] == ["csharp-notes-api/src/App/Models/Note.cs"]


def test_python_and_script_files_keep_their_imports_and_definitions(tmp_path):
    (tmp_path / ".project-directory").write_text("app")
    (tmp_path / "app" / "web").mkdir(parents=True)
    (tmp_path / "app" / "store.py").write_text("def save(note):\n    pass\n")
    (tmp_path / "app" / "main.py").write_text("from store import save\n\ndef create():\n    save(1)\n")
    (tmp_path / "app" / "web" / "api.ts").write_text("export const load = async () => 1;\n")
    (tmp_path / "app" / "web" / "page.ts").write_text("import { load } from './api';\nexport function show() {}\n")

    graph = project_graph.build(tmp_path)

    assert graph["app/main.py"]["imports"] == ["app/store.py"]
    assert graph["app/main.py"]["defines"] == ["create"]
    assert graph["app/web/page.ts"]["imports"] == ["app/web/api.ts"]
    assert graph["app/web/api.ts"]["defines"] == ["load"]
    assert ["function", "create", 3, 4, ""] in graph["app/main.py"]["definitions"]
