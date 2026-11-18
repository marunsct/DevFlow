"""A Slim service installs PHPStan, so the compile check names an invented method or a misplaced namespace at the write.

Measured on one Slim run: three invented `Slim\\App` methods and a namespace declared after other code each stopped
the product starting and were found only by the next test round - five reverts. The compile check ran PHPStan only when
the project had installed it, and the Slim pack did not install it.
"""
from __future__ import annotations

import json

from app.analysis import compiler_check
from app.stacks import pack_named


def test_the_slim_pack_installs_phpstan_for_development():
    pack = pack_named("php-slim-api")
    manifest = json.loads(pack.filled_files(pack.files, "notes-api", "Notes", None)["composer.json"])

    assert "phpstan/phpstan" in manifest["require-dev"]


def test_phpstan_reads_the_front_controller_folder_as_well(tmp_path):
    (tmp_path / "vendor" / "bin").mkdir(parents=True)
    (tmp_path / "vendor" / "bin" / "phpstan").write_text("")
    for folder in ("src", "public", "tests"):
        (tmp_path / folder).mkdir()

    argv = compiler_check._phpstan(tmp_path)

    assert argv[:2] == ["vendor/bin/phpstan", "analyse"] and argv[-3:] == ["src", "public", "tests"]
