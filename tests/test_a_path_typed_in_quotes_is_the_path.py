"""A path a stage sends wrapped in quotes is the path inside them.

Measured on one run: a builder sent `working_directory='"notes-api"'` and
`relative_path='"/notes-api/src/store.ts"'`, the quotes taken as part of the
name, and was told four times that the directory and the file did not exist.
"""

from __future__ import annotations

from app.agents.workspace_paths import rewrite_tool_arguments


def test_one_pair_of_quotes_around_a_path_is_taken_off():
    from app.agents.workspace_paths import unquoted

    assert unquoted('"notes-api"') == "notes-api"
    assert unquoted("'src/app.ts'") == "src/app.ts"
    assert unquoted("`notes-api`") == "notes-api"
    assert unquoted("notes-api") == "notes-api"
    assert unquoted('"half') == '"half'


def test_every_tool_s_path_arguments_are_unquoted(tmp_path):
    (tmp_path / "notes-api").mkdir()
    command = rewrite_tool_arguments(
        "run_terminal_command", {"command": ["npm", "test"], "working_directory": '"notes-api"'}, str(tmp_path)
    )
    edit = rewrite_tool_arguments(
        "replace_lines", {"relative_path": '"notes-api/src/store.ts"', "start_line": 1}, str(tmp_path)
    )

    assert command["working_directory"] == "notes-api"
    assert command["command"] == ["npm", "test"], "a command's own arguments are its business"
    assert edit["relative_path"].endswith("notes-api/src/store.ts") and '"' not in edit["relative_path"]
