"""A compiled toolchain's build output and installed packages stay out of the sprint history; same-named folders of the
product's own stay in.

Deep review 2026-11-18, item E3: the workspace's ignore list named `node_modules/`, `.venv/` and `dist/` but none of
`target/`, `bin/`, `obj/` or `vendor/` - which cannot be ignored by name, since a Node CLI's `bin/` is its own code. A
project whose scaffold wrote no `.gitignore` (a custom stack) committed cargo's and .NET's build output every sprint.
The folders the language table proves generated, by the manifest beside them, are now excluded.
"""

from __future__ import annotations

import subprocess

from app.tools import version_control


def _tracked(root) -> set[str]:
    return set(subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True).stdout.split())


def _write(root, *paths: str) -> None:
    for name in paths:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x")


def test_build_output_beside_its_manifest_is_never_committed(tmp_path):
    assert version_control.initialise_repository(tmp_path)
    _write(tmp_path,
           "api/Cargo.toml", "api/src/main.rs", "api/target/debug/api",
           "svc/src/App/App.csproj", "svc/src/App/Program.cs", "svc/src/App/bin/Debug/App.dll", "svc/src/App/obj/x.json",
           "web/composer.json", "web/src/App.php", "web/vendor/slim/slim/App.php")

    version_control.commit_milestone(tmp_path, sprint=1, goal="first")

    tracked = _tracked(tmp_path)
    assert {"api/src/main.rs", "svc/src/App/Program.cs", "web/src/App.php"} <= tracked
    assert not {"api/target/debug/api", "svc/src/App/bin/Debug/App.dll", "svc/src/App/obj/x.json",
                "web/vendor/slim/slim/App.php"} & tracked


def test_a_same_named_folder_of_the_product_s_own_is_committed(tmp_path):
    """A Node CLI's `bin/` and a source folder called `target/` are the product."""
    assert version_control.initialise_repository(tmp_path)
    _write(tmp_path, "cli/package.json", "cli/bin/cli.js", "cli/src/target/aim.js")

    version_control.commit_milestone(tmp_path, sprint=1, goal="first")

    assert {"cli/bin/cli.js", "cli/src/target/aim.js"} <= _tracked(tmp_path)
