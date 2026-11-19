"""A C# project laid out the pack's way - its project files under `src/` and `tests/` - is compiled after a change.

Measured on the C# runs: with nothing at the project's top, the compiler check never ran; three rewrites in a row
each fixed one compile error and wrote the next, with no compiler feedback between them.
"""
from __future__ import annotations

from pathlib import Path

from app.analysis import compiler_check


def _laid_out(root: Path) -> None:
    (root / "notes-api" / "src" / "App").mkdir(parents=True)
    (root / "notes-api" / "src" / "App" / "App.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk.Web"/>\n')
    (root / "notes-api" / "src" / "App" / "Program.cs").write_text("var x = 1;\n")
    (root / "notes-api" / "tests" / "UnitTests").mkdir(parents=True)
    (root / "notes-api" / "tests" / "UnitTests" / "UnitTests.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup><ProjectReference Include="../../src/App/App.csproj" />'
        "</ItemGroup></Project>\n")
    (root / "notes-api" / "src" / "App" / "obj").mkdir()
    (root / "notes-api" / "src" / "App" / "obj" / "Stale.csproj").write_text("<Project/>\n")


def test_the_project_that_references_the_others_is_built(tmp_path):
    _laid_out(tmp_path)
    ran = []

    def run(command, category, project):
        ran.append(command)
        return {"returncode": 1, "stdout": "/workspace/notes-api/src/App/Program.cs(17,42): error CS1503: Argument 1: "
                                            "cannot convert from 'string' to 'int' [/workspace/notes-api/src/App/App.csproj]",
                "stderr": ""}

    found = compiler_check.findings(tmp_path, "notes-api", ["notes-api/src/App/Program.cs"], run=run)

    assert ran and ran[0][:3] == ["dotnet", "build", "tests/UnitTests/UnitTests.csproj"]
    assert found and found[0]["code"] == "CS1503"


def test_a_project_file_at_the_top_is_built_as_before(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "Api.csproj").write_text("<Project/>\n")
    ran = []

    compiler_check.findings(tmp_path, "api", ["api/Program.cs"], run=lambda c, k, p: ran.append(c) or {"returncode": 0})

    assert ran == [["dotnet", "build", "--nologo", "-v", "q", "-clp:NoSummary"]]
