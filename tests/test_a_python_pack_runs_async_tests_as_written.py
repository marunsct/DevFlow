"""A Python pack's kept pytest.ini runs `async def` tests and fixtures as written.

Measured on one gate run: an async service's unit tests failed to set up round
after round under pytest-asyncio's strict mode ("requested an async fixture"),
and the fixer could not change the mode - the file is the harness's.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from app.stacks.packs import _python


def test_the_kept_file_sets_the_mode():
    assert "asyncio_mode = auto" in _python.PYTEST_INI.splitlines()


def test_an_async_fixture_and_test_run_without_markers(tmp_path):
    pytest.importorskip("pytest_asyncio")
    (tmp_path / "pytest.ini").write_text(_python.PYTEST_INI)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_reads.py").write_text(
        "import pytest\n\n@pytest.fixture\nasync def session():\n    yield 'db'\n\n"
        "async def test_reads(session):\n    assert session == 'db'\n"
    )

    ran = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:randomly"], cwd=tmp_path,
                         capture_output=True, text=True)

    assert ran.returncode == 0, ran.stdout[-600:]
