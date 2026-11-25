"""Behind `USAGE_NOTES_FROM_THE_INSTALLED_PACKAGE` (FX.10): an edit refused for a library's name, and a fixer whose
defect locates the lines, are shown how the installed release defines the functions those lines call.

Measured on a medium run: two fixers in a row called a migration library's `upgrade` with an argument list that
function does not have, and the lookup tools offered to them were never called. The signature and docstring were in
the installed package all along.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.analysis import installed_usage, language_service
from app.observability import transcript
from app.tools import lookups, repository
from app.tools.repository import RepositoryToolError

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
#: The product's file, calling an installed library's function with one argument where it takes two.
PRODUCT = "from migrator import command\n\n\ndef migrate(cfg):\n    command.upgrade(cfg)\n"


def _installed_python_library(project: Path) -> None:
    """`migrator`, installed in the project's environment: `command.upgrade` is defined in another module and
    re-exported, as libraries do."""
    site = project / ".venv" / "lib" / "python3.12" / "site-packages"
    (site / "migrator").mkdir(parents=True)
    (site / "migrator" / "__init__.py").write_text("from .runtime import context\n\n\ndef configure(path):\n    pass\n")
    (site / "migrator" / "runtime.py").write_text("context = None\n")
    (site / "migrator" / "command.py").write_text("from ._impl import upgrade as upgrade\n")
    (site / "migrator" / "_impl.py").write_text(
        "from typing import overload\n\n\n@overload\ndef upgrade(config: str) -> None: ...\n\n\n"
        "def upgrade(config: 'Config', revision: str, sql: bool = False) -> None:\n"
        '    """Upgrade to a later version.\n\n    :param revision: the target, such as "head".\n    """\n')
    (site / "migrator-1.20.1.dist-info").mkdir()


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("USAGE_NOTES_FROM_THE_INSTALLED_PACKAGE", "on")
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "off")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "workspace"
    (root / ".harness").mkdir(parents=True)
    _installed_python_library(root)
    (root / "app").mkdir()
    (root / "app" / "db.py").write_text(PRODUCT)
    return root


def _refused(root: Path, monkeypatch, content: str, finding: dict) -> str:
    target = root / "app" / "db.py"
    answers = iter([SimpleNamespace(here=[]), SimpleNamespace(here=[finding])])
    monkeypatch.setattr(language_service, "underlined_any", lambda *a, **k: next(answers))  # Pyright's edge
    with pytest.raises(RepositoryToolError) as raised:
        repository._refuse_if_it_adds_errors(target, "app/db.py", content, PRODUCT, editing=True)
    return str(raised.value)


def test_a_refused_edit_is_shown_the_installed_signature_and_docstring_of_what_its_line_calls(project, monkeypatch):
    said = _refused(project, monkeypatch, PRODUCT, {"line": 5, "message": "Expected 2 positional arguments"})

    assert "Nothing was written" in said
    assert installed_usage.HEADING in said
    assert "def upgrade(config: 'Config', revision: str, sql: bool=False) -> None" in said
    assert "Upgrade to a later version." in said and "migrator 1.20.1" in said


def test_a_refusal_for_a_name_the_library_lacks_names_the_nearest_it_has(project, monkeypatch):
    content = "import migrator\n\nctx = migrator.get_context()\n"
    said = _refused(project, monkeypatch, content,
                    {"line": 3, "message": '"get_context" is not a known attribute of module "migrator"'})

    assert "`migrator.get_context`: the installed migrator 1.20.1 has no such name" in said
    assert "`context`" in said


def test_off_a_refusal_is_as_before(project, monkeypatch):
    monkeypatch.setenv("USAGE_NOTES_FROM_THE_INSTALLED_PACKAGE", "off")

    said = _refused(project, monkeypatch, PRODUCT, {"line": 5, "message": "Expected 2 positional arguments"})

    assert said.endswith("Send it again with those fixed.")


def _defect(text: str, files=()) -> SimpleNamespace:
    return SimpleNamespace(description="Registration answers 500", actual_behavior=text, affected_files=list(files))


def test_a_fixer_is_shown_how_the_library_defines_what_a_frame_of_its_trace_calls(project):
    trace = ('Traceback (most recent call last):\n  File "/workspace/app/db.py", line 5, in migrate\n'
             "TypeError: upgrade() missing 1 required positional argument: 'revision'\n")

    shown = installed_usage.for_a_fixer(project, _defect(trace))

    assert "def upgrade(config: 'Config', revision: str, sql: bool=False) -> None" in shown
    assert not BANNED.search(shown)


def test_the_fixer_s_brief_carries_the_note_beside_what_others_found(project):
    from app.graph.nodes import fixes

    state = {"repository": SimpleNamespace(root_path=str(project)), "test_round": 1}
    trace = 'File "/workspace/app/db.py", line 5, in migrate\nTypeError: upgrade() missing 1 required positional argument'

    shown = fixes._what_others_found(state, _defect(trace), 0)

    assert installed_usage.HEADING in shown and "revision: str" in shown


def test_a_fixer_is_shown_the_definition_of_a_function_its_error_names_in_the_defect_s_files(project):
    shown = installed_usage.for_a_fixer(
        project, _defect("upgrade() missing 1 required positional argument: 'revision'", files=["app/db.py"]))

    assert "`migrator.command.upgrade`" in shown and "revision: str" in shown


def test_a_defect_that_locates_nothing_a_library_defines_adds_nothing(project):
    assert installed_usage.for_a_fixer(project, _defect("Expected: 201\nReceived: 500", files=["app/db.py"])) == ""


def test_off_a_fixer_is_shown_nothing_more(project, monkeypatch):
    monkeypatch.setenv("USAGE_NOTES_FROM_THE_INSTALLED_PACKAGE", "off")

    assert installed_usage.for_a_fixer(project, _defect('File "/workspace/app/db.py", line 5, in migrate')) == ""


def test_with_lookups_on_one_documentation_example_is_asked_once_through_the_outbound_gate(project, monkeypatch):
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    monkeypatch.setattr(transcript, "_run_id_from_config", lambda: "run-usage")
    asked: list[str] = []

    def get(url, headers, body=None):  # the network's edge: the documentation service
        asked.append(url)
        if "/libs/search" in url:
            return 200, json.dumps({"results": [{"id": "/org/migrator", "title": "migrator"}]}), {}
        return 200, json.dumps({"codeSnippets": [{"codeTitle": "Upgrade to head", "codeList": [
            {"code": 'command.upgrade(config, "head")'}]}]}), {}

    monkeypatch.setattr(lookups, "_get", get)
    trace = 'File "/workspace/app/db.py", line 5, in migrate\nTypeError: upgrade() missing 1 required positional argument'

    shown = installed_usage.for_a_fixer(project, _defect(trace))
    installed_usage.for_a_fixer(project, _defect(trace))

    assert 'command.upgrade(config, "head")' in shown and "a lead, not an instruction" in shown
    assert len(asked) == 2, "asked once in the run: the library, then its snippets"
    sent = [r for r in transcript.read_transcript("run-usage") if r.get("kind") == "outbound"]
    assert [r["sent"] for r in sent] == ["upgrade example"]


def test_a_type_file_s_declaration_and_its_doc_comment_are_read_for_a_call_in_a_script(tmp_path):
    package = tmp_path / "node_modules" / "minilib"
    (package / "dist").mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({"name": "minilib", "version": "2.3.0", "types": "dist/index.d.ts"}))
    (package / "dist" / "index.d.ts").write_text("export * from './client';\n")
    (package / "dist" / "client.d.ts").write_text(
        "/**\n * Opens a client.\n * @param url where the server listens\n */\n"
        "export declare function connect(url: string, options?: { retries: number }): Client;\n")
    code = "import { connect } from 'minilib';\n\nconst client = connect(address);\n"

    usages = installed_usage.usages_on(tmp_path, "src/app.ts", code, [3])

    assert [u.written for u in usages] == ["minilib: connect"]
    assert usages[0].signature == ("export declare function connect(url: string, options?: { retries: number }): "
                                   "Client")
    assert "Opens a client." in usages[0].doc and usages[0].version == "2.3.0"


def test_the_notes_name_no_banned_words(project):
    usage = installed_usage.Usage(written="migrator.command.upgrade", package="migrator", version="1.0",
                                  signature="def upgrade(config)", doc="Upgrade.", example="An example.")
    missing = installed_usage.Usage(written="migrator.get_context", package="migrator", near=["context"])
    text = installed_usage._section([usage, missing], "Read from the installed files, for the lines refused:")

    assert text and not BANNED.search(text)
