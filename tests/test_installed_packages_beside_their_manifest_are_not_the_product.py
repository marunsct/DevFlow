"""Packages a toolchain installed beside its manifest are never read as the product's code.

Deep review 2026-11-18, item E3: twelve lists of "folders that are not the product" each differed, and the walk every
check shares knew cargo's `target/` and .NET's `bin/` and `obj/` but not Composer's `vendor/`, Bundler's `vendor/` or
Gradle's `build/`. A check walking a PHP product then read the frameworks Composer installed - the release's
development-server check among them, where a framework's own `php -S` command named the product's server.
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.walk import files_under
from app.graph import delivery


def _write(root: Path, *paths: str, text: str = "x") -> None:
    for name in paths:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)


def _relative(paths, root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in paths}


def test_a_walk_leaves_out_what_a_toolchain_installed_beside_its_manifest(tmp_path):
    _write(tmp_path, "api/composer.json", "api/src/App.php", "api/vendor/slim/slim/App.php",
           "svc/Gemfile", "svc/app.rb", "svc/vendor/bundle/ruby/3.3.0/gems/sinatra/base.rb",
           "jvm/build.gradle.kts", "jvm/src/main/kotlin/App.kt", "jvm/build/classes/App.class")

    found = _relative(files_under(tmp_path), tmp_path)

    assert {"api/src/App.php", "svc/app.rb", "jvm/src/main/kotlin/App.kt"} <= found
    assert not any("/vendor/" in path or path.startswith("jvm/build/") for path in found)


def test_a_folder_with_no_manifest_beside_it_is_walked(tmp_path):
    """A page's own `vendor/` script folder is the product's."""
    _write(tmp_path, "site/index.html", "site/vendor/chart.js", "site/build/notes.md")

    assert {"site/vendor/chart.js", "site/build/notes.md"} <= _relative(files_under(tmp_path), tmp_path)


def test_a_framework_s_development_server_under_vendor_is_not_the_product_s(tmp_path):
    (tmp_path / ".project-directory").write_text("notes")
    _write(tmp_path, "notes/composer.json", text="{}")
    _write(tmp_path, "notes/public/index.php", text="<?php\n$app->run();\n")
    _write(tmp_path, "notes/vendor/laravel/framework/ServeCommand.php", text="<?php\n$command = 'php -S ';\n")

    assert delivery._a_development_server(tmp_path) == []
