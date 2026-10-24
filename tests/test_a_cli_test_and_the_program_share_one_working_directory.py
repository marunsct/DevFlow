"""A command-line acceptance test and the program it runs share one working directory.

Measured on a small-model run: nine of ten locked tests wrote their input file by a relative name
(`pathlib.Path('test.txt').write_text(...)`) in the test's own directory, then ran the program in pytest's `tmp_path`,
where the file was not; the program reported it could not open the file and exited 2. None could pass whatever was
built, and the run stopped at 4 of 14 criteria with the hidden tests at 5 of 8.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

from app.stacks import pack_named

PACKAGE = "tinycli"


def _project(tmp_path, conftest):
    (tmp_path / "acceptance").mkdir()
    (tmp_path / PACKAGE).mkdir()
    (tmp_path / PACKAGE / "__init__.py").write_text("")
    (tmp_path / PACKAGE / "__main__.py").write_text(textwrap.dedent("""
        import sys
        try:
            print(open(sys.argv[1]).read().strip())
        except OSError:
            print("cannot open", file=sys.stderr)
            raise SystemExit(2)
    """))
    (tmp_path / "acceptance" / "conftest.py").write_text(conftest)
    (tmp_path / "acceptance" / "test_relative.py").write_text(textwrap.dedent("""
        import pathlib

        def test_a_file_written_by_a_relative_name_is_found(run_cli):
            pathlib.Path("input.txt").write_text("hello words")
            finished = run_cli("input.txt")
            assert finished.returncode == 0 and finished.stdout.strip() == "hello words"
    """))


def _pytest(tmp_path):
    return subprocess.run([sys.executable, "-m", "pytest", "acceptance", "-q", "-p", "no:cacheprovider"],
                          cwd=tmp_path, capture_output=True, text=True, timeout=120)


def test_a_relative_input_file_is_found_by_the_program(tmp_path):
    conftest = pack_named("python-cli").files["acceptance/conftest.py"].replace("{{package}}", PACKAGE)
    _project(tmp_path, conftest)

    done = _pytest(tmp_path)

    assert done.returncode == 0, done.stdout + done.stderr


def test_the_fixture_before_the_change_could_not_find_it(tmp_path):
    """The old fixture, kept here as it was: the file the test wrote was in another directory."""
    conftest = pack_named("python-cli").files["acceptance/conftest.py"].replace("{{package}}", PACKAGE)
    old = conftest.replace("def run_cli(tmp_path, monkeypatch):\n    monkeypatch.chdir(tmp_path)\n",
                           "def run_cli(tmp_path):\n")
    assert old != conftest
    _project(tmp_path, old)

    assert _pytest(tmp_path).returncode != 0


def test_the_guide_tells_the_author_about_the_shared_directory():
    guide = pack_named("python-cli").acceptance_guide
    assert "Path(\"input.txt\").write_text" in guide and "the test's own while it uses `run_cli`" in guide
