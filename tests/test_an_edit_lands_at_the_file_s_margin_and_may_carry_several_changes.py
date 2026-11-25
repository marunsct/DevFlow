"""Edits that land (plan FX.6 of the fixers-and-context research, LF.1422-LF.1423).

Measured on one medium run's failing fixers, both at their last calls:

- an edit's `find` and `replace` both carried two spaces more than the file - the read's gutter copied as
  indentation. The passage matched ignoring indentation, the replacement was written two spaces too deep, and the
  file no longer parsed ("unexpected indent"): refused, defect left open;
- an edit used a name the file did not import. The language service refused it twice, correctly, and the refusal
  said to add the import "in an edit of its own" with two calls left; the same change was sent again instead.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

from app.tools.agent_toolkit import build_artifact_edit_tool
from app.tools.edit_indentation import reindented
from app.tools.repository import _how_to_name_what_is_not_defined, edit_approved_artifact

_BANNED = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.IGNORECASE)

_MODULE = '''import logging


def migrate(connection, context_impl):
    def _do_run(connection, context_impl):
        """Delegate actual migration execution."""
        context_impl.start_transaction(connection=connection)

    return _do_run
'''


@pytest.fixture()
def workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "database.py").write_text(_MODULE, encoding="utf-8")
    return tmp_path


def test_a_replacement_sent_two_spaces_deeper_than_the_file_is_written_at_the_file_s_margin(workspace):
    sent_find = ('      def _do_run(connection, context_impl):\n'
                 '          """Delegate actual migration execution."""\n'
                 '          context_impl.start_transaction(connection=connection)')
    sent_replace = ('      def _do_run(connection, context_impl):\n'
                    '          """Run the migrations."""\n'
                    '          context_impl.run_migrations()')

    result = edit_approved_artifact(workspace, "svc/database.py", sent_find, sent_replace)

    assert "error" not in result
    text = (workspace / "svc" / "database.py").read_text(encoding="utf-8")
    ast.parse(text)
    assert "    def _do_run(connection, context_impl):\n        \"\"\"Run the migrations.\"\"\"\n" \
           "        context_impl.run_migrations()\n" in text


def test_a_replacement_sent_shallower_than_the_file_is_moved_right_by_the_same_amount(workspace):
    sent_find = ('def _do_run(connection, context_impl):\n'
                 '    """Delegate actual migration execution."""\n'
                 '    context_impl.start_transaction(connection=connection)')
    sent_replace = ('def _do_run(connection, context_impl):\n'
                    '    context_impl.run_migrations()')

    edit_approved_artifact(workspace, "svc/database.py", sent_find, sent_replace)

    text = (workspace / "svc" / "database.py").read_text(encoding="utf-8")
    ast.parse(text)
    assert "    def _do_run(connection, context_impl):\n        context_impl.run_migrations()\n" in text


@pytest.mark.parametrize("region, find", [
    ("    a()\n        b()", "  a()\n  b()"),          # lines off by different amounts
    ("\ta()\n\tb()", "    a()\n    b()"),              # tabs against spaces
])
def test_a_replacement_is_left_as_sent_when_the_margins_do_not_differ_by_one_amount(region, find):
    assert reindented(region, find, "  c()\n  d()") == "  c()\n  d()"


def test_a_replacement_too_shallow_to_move_left_is_left_as_sent():
    assert reindented("a()\nb()", "    a()\n    b()", "  c()\n    d()") == "  c()\n    d()"


def _edit(workspace: pathlib.Path, **arguments) -> dict:
    return build_artifact_edit_tool(str(workspace)).invoke({"relative_path": "svc/database.py", **arguments})


def test_one_edit_call_makes_changes_that_parse_only_together(workspace):
    """Each change alone leaves an unclosed bracket and is refused; together the file parses."""
    (workspace / "svc" / "database.py").write_text("def f():\n    return [\n        1,\n    ]\n", encoding="utf-8")
    alone = _edit(workspace, find="    return [", replace="    return (")
    assert "error" in alone

    result = _edit(workspace, changes=[{"find": "    return [", "replace": "    return ("},
                                       {"find": "    ]", "replace": "    )"}])

    assert "error" not in result
    assert (workspace / "svc" / "database.py").read_text(encoding="utf-8") == "def f():\n    return (\n        1,\n    )\n"


def test_a_change_that_matches_nowhere_writes_none_of_them_and_names_which(workspace):
    result = _edit(workspace, changes=[{"find": "import logging", "replace": "import logging\nimport os"},
                                       {"find": "this text is not in the file at all", "replace": "x = 1"}])

    assert "Change 2 of 2" in result["error"]
    assert (workspace / "svc" / "database.py").read_text(encoding="utf-8") == _MODULE


def test_a_name_not_imported_is_answered_with_one_call_carrying_the_import_and_the_change():
    said = _how_to_name_what_is_not_defined([{"message": '"alembic_command" is not defined'}])
    assert "`changes`" in said and "import" in said
    assert "in an edit of its own" not in said


def test_the_new_words_a_model_reads_name_no_banned_words():
    description = build_artifact_edit_tool("/tmp").description
    said = _how_to_name_what_is_not_defined([{"message": '"X" is not defined'}])
    assert "changes" in description
    assert not _BANNED.search(description) and not _BANNED.search(said)
