"""The map of what each file defines holds C#, Java and PHP product files (deep review of the parsers, finding 2).

A definition line was read only when it began with `export`, `pub`, `async` or the keyword itself, so `public class`,
`final class` and `public function` were not definitions and a file with none was left out of the map unnamed.
Measured on real product files: no C# file of 42, no Java file of 91 and 39 PHP files of 55 were in the map - the
localiser named no product file on a C# run. The sources here are those runs' own files.
"""
from __future__ import annotations

from pathlib import Path

from app.agents.project_memory import map_of

SOURCES = Path(__file__).parent / "captured" / "sources"


def _the_map() -> dict[str, str]:
    shown = map_of({f"src/{path.name}": path.read_text(encoding="utf-8") for path in sorted(SOURCES.iterdir())})
    return {line.split(": ", 1)[0][2:]: line.split(": ", 1)[1] for line in shown.splitlines()}


def test_each_file_is_in_the_map_with_the_classes_it_declares():
    entries = _the_map()

    assert "class NoteService" in entries["src/NoteService.java"]
    assert "class SQLiteRepository" in entries["src/SQLiteRepository.cs"]
    assert "final class PdoNoteRepository" in entries["src/PdoNoteRepository.php"]


def test_a_php_class_s_methods_are_listed():
    assert "public function findById(NoteId $id): ?Note" in _the_map()["src/PdoNoteRepository.php"]
