"""A deliberate change put back leaves no cache holding the change.

Measured on one run: the mutation check changed a file, Python compiled the change, and the file was put back within
the same second at the same size; the compiled change still matched the file's size and time, so the product ran a
change already undone and failed 14 of 17 tests whose code was clean.
"""
from __future__ import annotations

import os
import py_compile
import subprocess
import sys
import time

from app.acceptance import mutation


def _at_the_start_of_a_second() -> None:
    """Begin early in a second, so a change and its restore made at once fall in the same second."""
    while time.time() % 1 > 0.3:
        time.sleep(0.05)


def test_the_file_put_back_is_newer_than_the_change_by_whole_seconds(tmp_path):
    path = tmp_path / "app.py"
    _at_the_start_of_a_second()
    path.write_text("ANSWER = 1 != 1\n")  # the change, made now
    changed_at = path.stat().st_mtime
    mutation._restore_and_close_the_journal(tmp_path, path, b"ANSWER = 1 == 1\n")
    assert path.stat().st_mtime >= changed_at + 1.5


def test_python_does_not_run_the_change_after_it_is_put_back(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    module = package / "answer.py"
    _at_the_start_of_a_second()
    module.write_bytes(b"VALUE = 1 != 1\n")  # the change, the same size as the original
    py_compile.compile(str(module), invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)

    mutation._restore_and_close_the_journal(tmp_path, module, b"VALUE = 1 == 1\n")

    out = subprocess.run([sys.executable, "-c", "import pkg.answer as a; print(a.VALUE)"], cwd=tmp_path,
                         capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert out.stdout.strip() == "True", "the change, compiled before it was put back, ran"
