"""A dependency added to a manifest below the project's top folder is installed before the next measurement.

Measured on a C# run: drafting added a package to `src/App/App.csproj`; the install check read only manifests at the
project's top folder, so nothing installed it, and every start and unit run - without a network, by design - failed
restoring it (NU1301). The product never started.
"""
from __future__ import annotations

from app.stacks import contract


def test_a_nested_project_file_change_changes_the_manifest_digest(tmp_path):
    (tmp_path / "notes-api" / "src" / "App").mkdir(parents=True)
    project_file = tmp_path / "notes-api" / "src" / "App" / "App.csproj"
    project_file.write_text('<Project Sdk="Microsoft.NET.Sdk.Web"></Project>')
    before = contract._the_manifests(tmp_path, "notes-api")

    project_file.write_text('<Project Sdk="Microsoft.NET.Sdk.Web"><ItemGroup>'
                            '<PackageReference Include="Microsoft.Data.Sqlite" Version="8.0.10" /></ItemGroup></Project>')

    assert contract._the_manifests(tmp_path, "notes-api") != before


def test_installed_and_built_folders_are_not_read(tmp_path):
    (tmp_path / "app" / "node_modules" / "left-pad").mkdir(parents=True)
    (tmp_path / "app" / "package.json").write_text("{}")
    before = contract._the_manifests(tmp_path, "app")

    (tmp_path / "app" / "node_modules" / "left-pad" / "package.json").write_text('{"version": "2"}')

    assert contract._the_manifests(tmp_path, "app") == before
