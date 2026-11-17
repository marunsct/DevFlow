"""The mutation probe changes a Rust or C# product's code, and never a type's parameters.

Measured on a Rust run: `.rs` was not a source the probe knew, so it found nothing to change and the run had no
mutation score.
"""
from __future__ import annotations

import pytest

from app.acceptance.mutation import sites, source_files


@pytest.mark.parametrize("name, code", [
    ("src/storage.rs", "pub fn find(notes: Vec<Note>, id: u64) -> Option<Note> {\n    notes.into_iter().find(|n| n.id == id)\n}\n"),
    ("Storage.cs", "public Note? Find(List<Note> notes, long id) {\n    return notes.Find(n => n.Id == id);\n}\n"),
], ids=["rust", "csharp"])
def test_its_comparison_is_changed_and_its_type_parameters_are_not(tmp_path, name, code):
    (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / name).write_text(code)

    found = sites(source_files(tmp_path), tmp_path)

    changed = {(site["file"], site["line"]) for site in found}
    assert (name, 2) in changed
    assert all(site["line"] != 1 for site in found)  # the signature's `<` opens type parameters
