"""The C# service's project file is held to the ASP.NET Core SDK at every round, wherever its errors are reported.

Measured on two C# runs: `App.csproj` was rewritten to `Sdk="Microsoft.NET.Sdk"`, which drops ASP.NET Core and its
implicit usings; the compiler then reported `HttpContext`, `IResult` and `Results` missing in every source file.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.graph import acceptance_nodes
from app.stacks import contract, entry_exports, pack_named

WEB = '<Project Sdk="Microsoft.NET.Sdk.Web">\n  <PropertyGroup>\n    <TargetFramework>net8.0</TargetFramework>\n  </PropertyGroup>\n</Project>\n'


def _a_csharp_project(tmp_path, monkeypatch, project_file):
    monkeypatch.setenv("PACK_ENTRY_EXPORTS_KEPT", "on")
    pack = pack_named("csharp-aspnet-api")
    contract.write(tmp_path, pack, "notes-api", "Notes", None, scaffolded=True)
    for relative, text in pack.render("notes-api", "Notes", None).items():
        (tmp_path / "notes-api" / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "notes-api" / relative).write_text(text)
    if project_file is not None:
        (tmp_path / "notes-api" / "src" / "App" / "App.csproj").write_text(project_file)
    return {"repository": SimpleNamespace(root_path=str(tmp_path))}


@pytest.mark.parametrize("project_file, raised", [
    (None, False),  # the scaffold's own
    (WEB, False),
    (WEB.replace("Microsoft.NET.Sdk.Web", "Microsoft.NET.Sdk"), True),
], ids=["the-scaffold", "web-sdk-rewritten", "plain-sdk"])
def test_a_project_file_without_the_web_sdk_is_raised_against_itself(tmp_path, monkeypatch, project_file, raised):
    state = _a_csharp_project(tmp_path, monkeypatch, project_file)

    found = [d for d in acceptance_nodes.pack_contract_defects(state) if entry_exports.NO_LONGER_DECLARES in d.description]

    assert bool(found) is raised
    if raised:
        assert found[0].affected_files == ["notes-api/src/App/App.csproj"]
        assert '`<Project Sdk="Microsoft.NET.Sdk.Web">`' in found[0].description
        assert entry_exports.still_raised(str(tmp_path), found[0].description) is True
