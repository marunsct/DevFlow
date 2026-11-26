"""The code graph says which names a file uses of which other file, by name from the syntax trees (KG.3).

Before it, the graph knew what a file imports, not what it uses of it: a fixer could be told the handler imports the
store, not that it calls the store's `Create`; and in a Go package, whose files use each other without importing, it
knew no edge between `main.go` and the router it calls. A name is stated as a use of one file only when that file is
the one it can be; a name several files may define is marked ambiguous and never stated.

The projects are real products' files (`tests/captured/projects/README.md`); every expected edge was worked out by
reading them.
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


_JAVA = "src/main/java/app/notes_api/"
_KOTLIN = "src/main/kotlin/app/notes_api/"

#: (project, a file, exactly the names it uses of other files and the file each is) - by reading the files.
USES = [
    ("go-notes-api", "server.go", {
        "Create": "store/store.go", "Delete": "store/store.go", "Get": "store/store.go",
        "GetNotes": "store/store.go", "Note": "store/store.go", "Store": "store/store.go", "Update": "store/store.go",
    }),
    # `NewRouter` is in the same package's `server.go`, which `main.go` uses without importing.
    ("go-notes-api", "main.go", {"NewRouter": "server.go", "NewStore": "store/store.go"}),
    # The controller's own `createNote` calls the service's: a receiver other than the object itself.
    ("java-notes-api", f"{_JAVA}controller/NoteController.java", {
        "Note": f"{_JAVA}model/Note.java", "NoteRequest": f"{_JAVA}dto/NoteRequest.java",
        "NoteService": f"{_JAVA}service/NoteService.java", "createNote": f"{_JAVA}service/NoteService.java",
        "deleteNote": f"{_JAVA}service/NoteService.java", "getAll": f"{_JAVA}service/NoteService.java",
        "getById": f"{_JAVA}service/NoteService.java", "updateNote": f"{_JAVA}service/NoteService.java",
    }),
    ("kotlin-notes-api", f"{_KOTLIN}service/NoteService.kt", {
        "Note": f"{_KOTLIN}model/Note.kt", "NoteRepository": f"{_KOTLIN}repository/NoteRepository.kt",
        "ResourceNotFoundException": f"{_KOTLIN}exception/ResourceNotFoundException.kt",
        "findAll": f"{_KOTLIN}repository/NoteRepository.kt", "findById": f"{_KOTLIN}repository/NoteRepository.kt",
    }),
    ("csharp-notes-api", "src/App/Program.cs", {
        "Create": "src/App/Data/NotesStore.cs", "Delete": "src/App/Data/NotesStore.cs",
        "GetById": "src/App/Data/NotesStore.cs", "Note": "src/App/Models/Note.cs",
        "NotesStore": "src/App/Data/NotesStore.cs", "ReadAll": "src/App/Data/NotesStore.cs",
        "Update": "src/App/Data/NotesStore.cs",
    }),
    ("rust-notes-api", "src/router.rs", {
        "AppState": "src/state.rs", "create_handler": "src/handlers.rs", "delete_handler": "src/handlers.rs",
        "get_handler": "src/handlers.rs", "list_handler": "src/handlers.rs", "update_handler": "src/handlers.rs",
    }),
    # `Service.create_note` calls `DB.create_note`: its own name, another module's definition.
    ("ruby-notes-api", "lib/notes_api/service.rb", {
        "DB": "lib/notes_api/db.rb", "create_note": "lib/notes_api/db.rb", "delete_note": "lib/notes_api/db.rb",
        "fetch_note": "lib/notes_api/db.rb", "list_notes": "lib/notes_api/db.rb", "update_note": "lib/notes_api/db.rb",
    }),
    # `findById` is the interface's the handler names, not the implementation's it never names.
    ("php-notes-api", "src/Handlers/GetNoteHandler.php", {
        "NoteId": "src/Domain/NoteId.php", "NoteRepository": "src/Infrastructure/NoteRepository.php",
        "findById": "src/Infrastructure/NoteRepository.php", "from": "src/Domain/NoteId.php",
    }),
    ("typescript-notes-api", "src/routes.ts", {
        "Store": "src/store.ts", "createNote": "src/store.ts", "deleteNote": "src/store.ts",
        "getAllNotes": "src/store.ts", "getNoteById": "src/store.ts", "updateNote": "src/store.ts",
        "validateNoteBody": "src/validation.ts",
    }),
    ("python-wordstats", "wordstats/cli.py", {
        "analyze": "wordstats/analyzer.py", "get_top_words": "wordstats/analyzer.py",
    }),
]


@pytest.mark.parametrize(("project", "file", "uses"), USES, ids=[f"{p}:{f}" for p, f, _ in USES])
def test_a_file_uses_exactly_the_names_of_other_files_it_calls_and_names(tmp_path, project, file, uses):
    graph = _built(tmp_path, project)

    assert graph[f"{project}/{file}"]["uses"] == {name: f"{project}/{target}" for name, target in uses.items()}


@pytest.mark.parametrize(("project", "file", "name", "candidates"), [
    # Both modules define `create_note`, and `app.rb` names both.
    ("ruby-notes-api", "app.rb", "create_note", ["lib/notes_api/db.rb", "lib/notes_api/service.rb"]),
    # `getTitle` is the request's and the model's; the controller holds both.
    ("java-notes-api", f"{_JAVA}controller/NoteController.java", "getTitle",
     [f"{_JAVA}dto/NoteRequest.java", f"{_JAVA}model/Note.java"]),
    # `s.Load()` on a store whose type `main.go` never names: the store's, most likely, but not known.
    ("go-notes-api", "main.go", "Load", ["store/store.go"]),
])
def test_a_name_that_may_be_another_file_s_is_ambiguous_and_never_stated(tmp_path, project, file, name, candidates):
    graph = _built(tmp_path, project)

    node = graph[f"{project}/{file}"]
    assert name not in node["uses"]
    assert node["ambiguous"][name] == [f"{project}/{c}" for c in candidates]


def test_a_variable_named_like_a_module_it_does_not_import_is_not_a_use_of_it(tmp_path):
    """`handlers.rs` binds `State(state)`; `lib.rs` declares `mod state`, and `handlers.rs` does not import `lib.rs`."""
    graph = _built(tmp_path, "rust-notes-api")

    handlers = graph["rust-notes-api/src/handlers.rs"]
    assert "state" not in handlers["uses"] and "rust-notes-api/src/lib.rs" not in handlers["uses"].values()
    assert handlers["uses"] == {"AppState": "rust-notes-api/src/state.rs"}


def test_a_definition_knows_what_calls_it_and_what_it_calls(tmp_path):
    graph = _built(tmp_path, "go-notes-api")

    store, server = graph["go-notes-api/store/store.go"], graph["go-notes-api/server.go"]
    assert store["used_by"]["Create"] == ["go-notes-api/server.go"]
    assert store["called_by"]["Store.Create"] == [["go-notes-api/server.go", "createHandler"]]
    assert ["Create", "go-notes-api/store/store.go"] in server["calls"]["createHandler"]
    assert ["writeJSON", "go-notes-api/server.go"] in server["calls"]["createHandler"]
    assert ["Delete", "go-notes-api/store/store.go"] not in server["calls"]["createHandler"]


def test_a_file_used_only_by_name_from_its_own_package_is_used_by_it(tmp_path):
    """The router `server.go` is imported by nothing; `main.go` of the same package calls it."""
    graph = _built(tmp_path, "go-notes-api")

    router = graph["go-notes-api/server.go"]
    assert router["imported_by"] == []
    assert router["used_by"] == {"NewRouter": ["go-notes-api/main.go"]}
    assert router["called_by"]["NewRouter"] == [["go-notes-api/main.go", "main"]]
