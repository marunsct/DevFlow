"""A fix that leaves a manifest unreadable in its own format is reverted, even when nothing passed before it.

Measured on a C# run: a fixer wrote the program's C# into `App.csproj`. Nothing had passed before the fix, so nothing
"broke", and it stood; every later round failed "MSB4025: The project file could not be loaded".
"""
from __future__ import annotations

import subprocess

import pytest

from app import ci
from app.graph import engineering

CSPROJ = '<Project Sdk="Microsoft.NET.Sdk.Web">\n  <PropertyGroup>\n    <TargetFramework>net8.0</TargetFramework>\n  </PropertyGroup>\n</Project>\n'


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def _a_project_and_its_fix(root, name, before, after):
    (root / "app").mkdir()
    (root / "app" / name).write_text(before)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")
    base = _git(root, "rev-parse", "HEAD")
    (root / "app" / name).write_text(after)  # the fix
    return base


@pytest.mark.parametrize("name, before, after, reverted", [
    ("App.csproj", CSPROJ, "var builder = WebApplication.CreateBuilder(args);\n", True),
    ("package.json", '{"name": "notes"}\n', '{"name": "notes",\n', True),
    ("Cargo.toml", '[package]\nname = "notes"\n', '[package\nname = "notes"\n', True),
    ("App.csproj", CSPROJ, CSPROJ.replace("net8.0", "net9.0"), False),
], ids=["csharp-code-in-the-project-file", "json-cut-short", "toml-unclosed", "a-readable-edit"])
def test_the_fix_is_reverted_only_when_it_left_the_manifest_unreadable(tmp_path, monkeypatch, name, before, after, reverted):
    base = _a_project_and_its_fix(tmp_path, name, before, after)
    nothing_passes = ci.Snapshot(label="s", unit={"u1": "failed"}, unit_ran=True, problem="it did not start")
    monkeypatch.setattr(ci, "load", lambda root, which: nothing_passes)
    monkeypatch.setattr(ci, "take", lambda root, label: nothing_passes)  # the project's own tests are the edge
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)

    broke = engineering.after_a_fix(str(tmp_path), base, "defect_fix_1_1", "start it")

    assert any("unreadable" in item for item in broke) is reverted, broke
    assert ((tmp_path / "app" / name).read_text() == before) is reverted


def test_a_manifest_unreadable_before_the_fix_is_not_its(tmp_path, monkeypatch):
    base = _a_project_and_its_fix(tmp_path, "package.json", '{"name": ', '{"name": "x",')
    nothing_passes = ci.Snapshot(label="s", unit={"u1": "failed"}, unit_ran=True, problem="it did not start")
    monkeypatch.setattr(ci, "load", lambda root, which: nothing_passes)
    monkeypatch.setattr(ci, "take", lambda root, label: nothing_passes)
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)

    assert engineering.after_a_fix(str(tmp_path), base, "defect_fix_1_1", "x") == []
