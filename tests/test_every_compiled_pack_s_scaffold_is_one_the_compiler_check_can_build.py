"""Every pack in a compiled language lays out a scaffold the harness's compiler check can build.

Measured on the C# runs: the check looked for a project file at the project's top, the C# pack puts its project
files under `src/App` and `tests/UnitTests`, and the check never ran - every C# rewrite went uncompiled until a
test round. A check that cannot see a pack's layout now fails here, not in a run.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis import compiler_check
from app.stacks.packs import ALL_PACKS

SUFFIX = {checker.language: checker.suffixes[0] for checker in compiler_check.CHECKERS}
#: Checkers that need something the scaffold does not hold until its dependencies are installed.
NEEDS_AN_INSTALL = {"php"}
COMPILED = [pack for pack in ALL_PACKS if pack.language in SUFFIX and pack.language not in NEEDS_AN_INSTALL]


def test_there_are_compiled_packs_to_check():
    assert {pack.language for pack in COMPILED} >= {"csharp", "java", "go", "rust"}


@pytest.mark.parametrize("pack", COMPILED, ids=lambda pack: pack.name)
def test_the_scaffold_has_a_compile_command(tmp_path: Path, pack):
    project = tmp_path / "notes"
    for relative, content in pack.render("notes", "Notes", None).items():
        (project / relative).parent.mkdir(parents=True, exist_ok=True)
        (project / relative).write_text(content)

    chosen = compiler_check.checker_for(project, [f"notes/changed{SUFFIX[pack.language]}"])

    assert chosen is not None, f"{pack.name}: no compile command for its own layout"
    assert chosen[0].language == pack.language
