"""A command-line program in Python, on the standard library's argparse."""

from __future__ import annotations

from app.stacks import StackPack
from app.stacks.packs import _python

PYPROJECT = """[project]
name = "{{project}}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
{{project}} = "{{package}}.cli:main"
"""

REQUIREMENTS_DEV = """pytest>=8
pytest-timeout>=2
"""

CLI = '''"""The program's command line."""

import argparse
import sys

from {{package}} import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="{{project}}", description="{{title}}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the program; the return value is its exit status."""
    parser = build_parser()
    parser.parse_args(sys.argv[1:] if argv is None else argv)
    return 0
'''

MAIN = '''from {{package}}.cli import main

raise SystemExit(main())
'''

CONFTEST = '''"""Runs the program the way a user does. The harness owns this file.

`run_cli("add", "x")` runs `python -m {{package}} add x` as its own process in
the test's own empty directory and returns the finished process: `.returncode`,
`.stdout` and `.stderr`. The test itself works in that directory too, so a file
it writes by a relative name is the file the program finds by that name.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent


@pytest.fixture
def run_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def run(*args: str, input: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
        environment = {**os.environ, "PYTHONPATH": str(PROJECT), "HOME": str(tmp_path), **(env or {})}
        return subprocess.run(
            [sys.executable, "-m", "{{package}}", *args],
            cwd=tmp_path, input=input, env=environment,
            capture_output=True, text=True, timeout=60,
        )

    return run
'''

SMOKE_UNIT = '''import pytest

from {{package}}.cli import main


def test_the_version_option_exits_cleanly():
    with pytest.raises(SystemExit) as finished:
        main(["--version"])
    assert finished.value.code == 0
'''

SMOKE_ACCEPTANCE = '''def test_the_program_runs(run_cli):
    finished = run_cli("--version")
    assert finished.returncode == 0
    assert "{{project}}" in finished.stdout
'''

GUIDE = _python.UNIT_GUIDE + """
The program's entry point is `main(argv)` in `{{package}}/cli.py`; it returns the
exit status and `python -m {{package}}` runs it. Write output with `print` (errors
to `sys.stderr`) and return a non-zero status on failure. A unit test calls
`main([...])` and reads output through pytest's `capsys`."""

ACCEPTANCE_GUIDE = """Acceptance tests go in `acceptance/`, named `test_<feature>.py`, as pytest
functions. Take the `run_cli` fixture and run the program exactly as a user
would: `finished = run_cli("add", "Buy milk")`, then check `finished.returncode`,
`finished.stdout` and `finished.stderr`. Each test runs in its own empty
directory (pytest's `tmp_path`, which is also the program's working directory
and HOME, and the test's own while it uses `run_cli`), so a file the test writes
by a relative name (`Path("input.txt").write_text(...)`) is the file the program
finds as `input.txt`, files the program writes there are the test's to read, and
nothing carries between tests. To prove something persists, run the program twice.
""" + _python.NAMING

PACK = StackPack(
    known_errors=_python.PYTHON_KNOWN_ERRORS,
    name="python-cli",
    title="Command-line program in Python",
    kind="cli",
    language="python",
    frameworks=("argparse", "click", "typer", "standard library"),
    files={
        "pyproject.toml": PYPROJECT,
        "requirements.txt": "",
        "requirements-dev.txt": REQUIREMENTS_DEV,
        "pytest.ini": _python.PYTEST_INI,
        ".gitignore": _python.GITIGNORE,
        "{{package}}/__init__.py": '"""{{title}}."""\n\n__version__ = "0.1.0"\n',
        "{{package}}/__main__.py": MAIN,
        "{{package}}/cli.py": CLI,
        "acceptance/conftest.py": CONFTEST,
    },
    install=_python.INSTALL,
    unit_test=_python.UNIT_TEST,
    acceptance_test=_python.ACCEPTANCE_TEST,
    unit_report="test-results/unit.xml",
    acceptance_report="test-results/acceptance.xml",
    unit_dir="tests",
    acceptance_dir="acceptance",
    acceptance_pattern="test_*.py",
    unit_pattern="test_*.py",
    unit_test_names=_python.UNIT_TEST_NAMES,
    test_helpers=_python.TEST_HELPERS,
    kept_files=("pytest.ini", "acceptance/conftest.py"),
    kept_scripts={},
    smoke_files={
        "tests/test_scaffold_smoke.py": SMOKE_UNIT,
        "acceptance/test_scaffold_smoke.py": SMOKE_ACCEPTANCE,
    },
    guide=GUIDE,
    acceptance_guide=ACCEPTANCE_GUIDE,
    stack={
        "language": "Python",
        "framework": "None (standard library argparse)",
        "frontend_framework": "",
        "testing_framework": "pytest for unit tests, pytest running the program as a process for acceptance tests",
    },
    check_families=frozenset({"python"}),
    test_bugs=_python.TEST_BUGS,
    ci_setup=_python.CI_SETUP,
)
