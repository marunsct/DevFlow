"""Python stacks are told what pytest-asyncio's strict mode needs; the kept pytest.ini sets no mode.

Measured on one gate run: an async service's unit tests failed to set up round
after round under strict mode ("requested an async fixture"), and the fix tried
was the configuration, a file the harness keeps. Setting `asyncio_mode = auto`
there was tried and taken back: proven with real pytest, auto mode takes
anyio's tests from anyio and runs a trio-parametrised one on asyncio - a fix for
one product that breaks another (owner, 2026-10-20: language- and
framework-agnostic). Strict mode with markers serves both.
"""
from __future__ import annotations

import re
import subprocess
import sys

import pytest

from app.plugins.seed import SEED_INSTRUCTIONS
from app.stacks.packs import _python

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_python_stacks_are_told_the_markers():
    (line,) = [line for line in SEED_INSTRUCTIONS["python"].splitlines() if line.startswith("- Async tests")]

    assert "@pytest.mark.asyncio" in line and "@pytest_asyncio.fixture" in line and "@pytest.mark.anyio" in line
    assert not BANNED.search(line)


def test_the_kept_file_leaves_the_mode_to_its_default():
    assert "asyncio_mode" not in _python.PYTEST_INI


def test_the_markers_it_names_run_an_async_fixture_and_test(tmp_path):
    pytest.importorskip("pytest_asyncio")
    (tmp_path / "pytest.ini").write_text(_python.PYTEST_INI)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_reads.py").write_text(
        "import pytest\nimport pytest_asyncio\n\n@pytest_asyncio.fixture\nasync def session():\n    yield 'db'\n\n"
        "@pytest.mark.asyncio\nasync def test_reads(session):\n    assert session == 'db'\n"
    )

    ran = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=tmp_path, capture_output=True, text=True)

    assert ran.returncode == 0, ran.stdout[-600:]
