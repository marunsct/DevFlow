"""Code passed on the command line runs from a recorded throwaway file (owner's decision, 2026-10-20).

`python -c` and `node -e` were refused ("it can execute arbitrary code. Put the
code in a file ... named `tmp-<what it checks>`"); measured, 10 such refusals on
one run, 35 on another, each a model call - and the advice was rarely followed.
The harness now does what the advice says: the snippet is saved as a `tmp-`
file in the project, where it is readable afterwards and swept before the next
test round and at release, and that file is run.
"""
from __future__ import annotations

import re

import pytest

from app.analysis.file_kinds import is_scratch
from app.tools.agent_toolkit import build_terminal_command_tool

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture
def ran(monkeypatch):
    calls = []
    from app.tools.sandbox import SandboxExecutor

    monkeypatch.setattr(SandboxExecutor, "execute", staticmethod(
        lambda **kw: calls.append((kw["command"], kw.get("working_directory"))) or {"returncode": "0"}))
    return calls


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / ".project-directory").write_text("shop\n")
    (tmp_path / "shop").mkdir()
    return tmp_path


def _run(workspace, argv, working_directory=None):
    tool = build_terminal_command_tool(str(workspace), "backend")
    return tool.func(command=argv, working_directory=working_directory)


def test_python_code_runs_from_a_file_in_the_project(workspace, ran):
    result = _run(workspace, ["task-management/.venv/bin/python", "-c", "import sys; print(sys.argv)", "a", "b"])

    [(argv, where)] = ran
    assert where is None
    assert argv[0] == "task-management/.venv/bin/python" and argv[2:] == ["a", "b"]
    assert argv[1].startswith("shop/tmp-") and argv[1].endswith(".py") and is_scratch(argv[1])
    assert (workspace / argv[1]).read_text() == "import sys; print(sys.argv)\n"
    assert argv[1] in result["note"] and not BANNED.search(result["note"])


def test_node_code_runs_from_a_file_in_the_working_directory(workspace, ran):
    _run(workspace, ["node", "-e", "console.log(require('fs').existsSync('package.json'))"], working_directory="shop")

    [(argv, where)] = ran
    assert where == "shop" and argv[0] == "node" and len(argv) == 2
    assert argv[1].startswith("tmp-") and argv[1].endswith(".cjs")
    assert "existsSync" in (workspace / "shop" / argv[1]).read_text()


def test_a_printed_expression_is_printed(workspace, ran):
    _run(workspace, ["node", "-p", "1 + 1"], working_directory="shop")

    [(argv, _where)] = ran
    assert "console.log" in (workspace / "shop" / argv[1]).read_text()


def test_other_commands_run_as_they_are(workspace, ran):
    _run(workspace, ["npm", "test"], working_directory="shop")

    assert ran == [(["npm", "test"], "shop")]


def test_the_saved_file_is_swept_before_the_next_test_round(workspace, ran):
    """Measured on one gate run: seven `tmp-inline-` files sat in the product. The
    sweep removes only a file the project memory says a stage wrote, and these
    were written by the command itself."""
    from app.tools.repository import clear_the_throwaways_left_behind

    _run(workspace, ["python3", "-c", "print(1)"])
    [(argv, _)] = ran
    assert (workspace / argv[1]).exists()

    assert clear_the_throwaways_left_behind(workspace) == [argv[1]]
    assert not (workspace / argv[1]).exists()


def test_the_tool_says_what_it_does_with_code_on_the_command_line(workspace):
    """It said such code was refused and to write, run and delete a file - three
    calls for what one now does."""
    description = build_terminal_command_tool(str(workspace), "backend").description

    assert "are refused" not in description and "tmp-inline-" in description
    assert not BANNED.search(description[description.index("Code passed"):description.index("the harness removes the file")])


def test_every_language_the_sandbox_refuses_code_for_runs_it_from_a_file(workspace, ran):
    """Owner, 2026-10-20: a fix that works for one language works for the others, from the
    harness's own tables. The rewrite knew only Python and Node, while the sandbox refuses
    code on the command line for Ruby, PHP, Elixir and Scala too."""
    _run(workspace, ["ruby", "-e", "puts File.exist?('Gemfile')"])
    _run(workspace, ["php", "-r", "echo PHP_VERSION;"])

    (ruby, _), (php, _) = ran
    assert ruby[0] == "ruby" and ruby[1].endswith(".rb") and is_scratch(ruby[1])
    assert (workspace / ruby[1]).read_text() == "puts File.exist?('Gemfile')\n"
    assert php[1].endswith(".php") and (workspace / php[1]).read_text() == "<?php\necho PHP_VERSION;\n"


def test_the_table_covers_every_program_refused_for_code_in_an_argument():
    from app.tools.sandbox import _WHY_THE_ARGUMENT_IS_REFUSED, CODE_AS_A_FILE

    refused = {program for program, why in _WHY_THE_ARGUMENT_IS_REFUSED.items() if why == "eval"}
    # Code beside a build: a file is not the same command, so the refusal stands.
    assert refused - set(CODE_AS_A_FILE) == {"rake", "mix"}


def test_the_description_names_every_language_it_rewrites(workspace):
    description = build_terminal_command_tool(str(workspace), "backend").description

    for named in ("`python -c`", "`node -e`", "`ruby -e`", "`php -r`"):
        assert named in description
    assert "{code_flags}" not in description
