"""A file a stage writes with an interpreter line (`#!`) is executable.

No role may run `chmod`. Measured on one run: a builder whose specification
said "chmod +x start.sh" was refused, so a launcher written from scratch
could not be run as `./start.sh`.
"""

from __future__ import annotations

import os

from app.tools.repository import write_approved_artifact


def test_a_launcher_is_executable_and_anything_else_is_not(tmp_path):
    write_approved_artifact(tmp_path, "notes/start.sh", "#!/bin/sh\nexec node src/index.js\n")
    write_approved_artifact(tmp_path, "notes/src/index.js", "console.log('hi')\n")

    assert os.access(tmp_path / "notes" / "start.sh", os.X_OK)
    assert not os.access(tmp_path / "notes" / "src" / "index.js", os.X_OK)
