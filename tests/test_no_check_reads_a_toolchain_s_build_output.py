"""No check reads a toolchain's build output: a folder its manifest beside it proves generated.

Measured on a Rust run: the release checks read cargo's generated docs under `target/doc` ("references
`./static.files/${f}`, which does not exist") and the mutation probe changed their JavaScript, so the run's mutation
score measured nothing.
"""
from __future__ import annotations

from pathlib import Path

from app.acceptance.mutation import source_files
from app.analysis.walk import files_under


def _a_project(root: Path, manifest: str) -> Path:
    (root / manifest).write_text("x")
    for relative in ("src/main.rs", "target/doc/search-index.js", "target/doc/help.html", "src/target/aim.js"):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text("const a = 1 === 2;\n")
    return root


def test_the_build_output_beside_its_manifest_is_never_walked(tmp_path):
    found = {path.relative_to(tmp_path).as_posix() for path in files_under(_a_project(tmp_path, "Cargo.toml"))}

    assert not any(path.startswith("target/") for path in found)
    assert {"src/main.rs", "src/target/aim.js"} <= found  # a folder of that name the project owns is its own


def test_a_folder_of_that_name_with_no_manifest_beside_it_is_the_project_s(tmp_path):
    found = {path.relative_to(tmp_path).as_posix() for path in files_under(_a_project(tmp_path, "package.json"))}

    assert "target/doc/search-index.js" in found


def test_the_mutation_probe_never_changes_the_build_output(tmp_path):
    changed = {path.relative_to(tmp_path).as_posix() for path in source_files(_a_project(tmp_path, "Cargo.toml"))}

    assert not any(path.startswith("target/") for path in changed)
