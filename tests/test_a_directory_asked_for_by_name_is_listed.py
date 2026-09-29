"""Listing a directory that listings hide shows what is in it.

One run's `test_round_1` listed its project's `node_modules` to see whether the
install had happened. Every entry was inside a hidden directory, so the answer
was "No files found", and the stage ran the install again. The same stage had
first listed `node_modules/.package-lock.json` and been told only
"not_a_directory".
"""

from __future__ import annotations

from pathlib import Path

from app.agents.workspace_backend import WorkspaceBackend


def _backend(root: Path) -> WorkspaceBackend:
    return WorkspaceBackend(str(root), virtual_mode=True)


def _paths(result: object) -> list[str]:
    entries = getattr(result, "entries", None) or getattr(result, "matches", None) or []
    return [str(e.get("path") if isinstance(e, dict) else getattr(e, "path", e)) for e in entries]


def _installed(root: Path) -> None:
    (root / "app" / "node_modules" / "jest").mkdir(parents=True)
    (root / "app" / "node_modules" / "jest" / "package.json").write_text("{}\n", encoding="utf-8")
    (root / "app" / "src").mkdir()
    (root / "app" / "src" / "index.js").write_text("export {}\n", encoding="utf-8")


def test_the_hidden_directory_itself_is_listed(tmp_path: Path) -> None:
    _installed(tmp_path)

    listed = _paths(_backend(tmp_path).ls("/app/node_modules"))

    assert any("jest" in p for p in listed)


def test_its_parent_still_hides_it(tmp_path: Path) -> None:
    _installed(tmp_path)

    listed = _paths(_backend(tmp_path).ls("/app"))

    assert any(p.rstrip("/").endswith("src") for p in listed)
    assert not any("node_modules" in p for p in listed)


def test_a_search_under_it_finds_what_is_there(tmp_path: Path) -> None:
    _installed(tmp_path)

    found = _paths(_backend(tmp_path).glob("package.json", "/app/node_modules"))

    assert any("jest/package.json" in p for p in found)


def test_a_search_from_the_top_still_skips_it(tmp_path: Path) -> None:
    _installed(tmp_path)

    found = _paths(_backend(tmp_path).glob("*.json", "/"))

    assert not any("node_modules" in p for p in found)


def test_listing_a_file_says_it_is_one(tmp_path: Path) -> None:
    _installed(tmp_path)

    error = str(getattr(_backend(tmp_path).ls("/app/src/index.js"), "error", ""))

    assert "not_a_directory" in error
    assert "is a file, so it exists; read_file reads it" in error
