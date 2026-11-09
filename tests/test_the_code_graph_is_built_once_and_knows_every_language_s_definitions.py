"""The code graph is built once while the project is unchanged, and holds definitions in every language.

It was built afresh on every `neighbourhood`, `where_is` and `who_uses` - each
fix request and each `code_graph` call read every source file of the project.
On a ten-file product that cost nothing; on a large codebase it was a full read
per call. And it read only Python and JavaScript-family files, so in a Go,
Java, Rust, Ruby, PHP, C# or Swift project `where_is` found nothing and sent the
agent to search.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.analysis import project_graph
from app.analysis.reachability import FAMILIES

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _go_and_java(root: Path) -> Path:
    (root / ".project-directory").write_text("shop")
    (root / "shop" / "internal").mkdir(parents=True)
    (root / "shop" / "internal" / "store.go").write_text(
        "package internal\n\ntype Store struct{}\n\nfunc (s *Store) LoadItems() []string {\n\treturn nil\n}\n\n"
        "func NewStore() *Store {\n\treturn &Store{}\n}\n"
    )
    (root / "shop" / "Billing.java").write_text("package shop;\n\npublic final class Billing {\n}\n")
    return root


def test_where_is_finds_a_definition_in_a_language_without_an_import_reader(tmp_path):
    root = _go_and_java(tmp_path)

    assert project_graph.where_is(root, "LoadItems") == ["shop/internal/store.go"]
    assert project_graph.where_is(root, "NewStore") == ["shop/internal/store.go"]
    assert project_graph.where_is(root, "Billing") == ["shop/Billing.java"]


def test_who_uses_says_it_does_not_follow_imports_in_that_language(tmp_path):
    root = _go_and_java(tmp_path)

    used = project_graph.who_uses(root, "shop/internal/store.go")

    assert used["imported_by"] == [] and "Store" in used["defines"]
    assert "does not follow imports" in used["note"]
    assert not BANNED.search(used["note"])


def test_reachability_still_reads_only_the_languages_it_reads(tmp_path):
    assert set(FAMILIES) == {"python", "script"}


def test_an_unchanged_project_is_not_read_again(tmp_path, monkeypatch):
    root = _go_and_java(tmp_path)
    (root / "shop" / "app.py").write_text("def serve():\n    pass\n")
    first = project_graph.build(root)
    reads = []
    original = Path.read_text

    def counting(self, *args, **kwargs):
        reads.append(self.name)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)
    again = project_graph.build(root)

    assert again == first
    assert "serve" in first["shop/app.py"]["defines"]
    assert "app.py" not in reads and "store.go" not in reads


def test_a_changed_file_is_read_again(tmp_path):
    root = _go_and_java(tmp_path)
    project_graph.build(root)
    store = root / "shop" / "internal" / "store.go"
    store.write_text(store.read_text() + "\nfunc DropItems() {}\n")
    os.utime(store, ns=(store.stat().st_atime_ns, store.stat().st_mtime_ns + 1_000_000))

    assert project_graph.where_is(root, "DropItems") == ["shop/internal/store.go"]


def test_the_graph_file_is_not_rewritten_when_nothing_changed(tmp_path):
    root = _go_and_java(tmp_path)
    project_graph.build(root)
    written = root / project_graph.GRAPH_FILE
    before = written.stat().st_mtime_ns
    project_graph._BUILT.clear()

    project_graph.build(root)

    assert written.stat().st_mtime_ns == before
