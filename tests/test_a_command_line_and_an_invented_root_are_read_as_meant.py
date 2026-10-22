"""A command line sent as one string, and a write under an invented root, are read as meant.

Measured on one run on a local model: 53 failed calls were command lines like
`cd /workspace/notes-api && node --test x 2>&1 | head -80`, and 25 were writes
to `/workspace/notes-api/acceptance/api.spec.ts`, refused as outside the suite.
"""

from __future__ import annotations

import pytest

from app.agents.workspace_paths import rewrite_tool_arguments


@pytest.fixture
def root(tmp_path):
    (tmp_path / "notes-api" / "acceptance").mkdir(parents=True)
    return str(tmp_path)


@pytest.mark.parametrize("sent, argv, directory", [
    (["cd /workspace/notes-api && node --test 'acceptance/**/*.spec.ts' 2>&1 | head -80"],
     ["node", "--test", "acceptance/**/*.spec.ts"], "notes-api"),
    (["cd /workspace && node --version"], ["node", "--version"], None),
    ("npm run build", ["npm", "run", "build"], "keep"),
    (["cd notes-api && npx tsc --noEmit | tail -20"], ["npx", "tsc", "--noEmit"], "notes-api"),
])
def test_a_command_line_becomes_its_argv_and_directory(root, sent, argv, directory):
    out = rewrite_tool_arguments("run_terminal_command", {"command": sent, "working_directory": "keep"}, root)

    assert out["command"] == argv
    assert out.get("working_directory") == directory


def test_a_line_that_needs_a_shell_is_left_to_be_refused(root):
    sent = {"command": ["ls -la && find . -maxdepth 3 -type f"]}

    assert rewrite_tool_arguments("run_terminal_command", sent, root) == sent


def test_an_argv_already_split_is_untouched(root):
    sent = {"command": ["npm", "test"], "working_directory": "notes-api"}

    assert rewrite_tool_arguments("run_validation", sent, root) == sent


def test_a_new_file_under_an_invented_root_is_written_where_meant(root):
    out = rewrite_tool_arguments("write_artifact", {"relative_path": "/workspace/notes-api/acceptance/api.spec.ts"}, root)

    assert out["relative_path"] == "/notes-api/acceptance/api.spec.ts"
    kept = {"relative_path": "/notes-api/acceptance/api.spec.ts"}
    assert rewrite_tool_arguments("write_artifact", kept, root)["relative_path"] == kept["relative_path"]
