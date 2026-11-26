"""A write that removes, renames or re-parameters a definition other files use names those files and lines (plan KG.7).

Measured: a builder that renamed a function learned that another file still called the old name only when the build
or a test failed rounds later; the next work order heard of it from the harness's interface notes, the author never.
With `USES_NAMED_AT_THE_WRITE` on, the write's own reply names each file the code graph shows using the old form, and
the lines, once a stage.

The project is a real Go product's files (`tests/captured/projects/go-notes-api`); the lines were read from them.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from langchain_core.messages import ToolMessage

from app.tools.uses_named_at_the_write import build_middleware

PROJECTS = Path(__file__).parent / "captured" / "projects"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
STORE = "go-notes-api/store/store.go"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.delenv("SWITCH_OVERRIDES_FROM_SETTINGS", raising=False)
    monkeypatch.setenv("USES_NAMED_AT_THE_WRITE", "on")
    shutil.copytree(PROJECTS / "go-notes-api", tmp_path / "go-notes-api")
    (tmp_path / ".project-directory").write_text("go-notes-api")
    return tmp_path


class _Request:
    def __init__(self, path: str) -> None:
        self.tool_call = {"name": "write_artifact", "args": {"relative_path": path, "content": "..."}, "id": "w1"}


def _written(middleware, root: Path, change) -> str:
    """A write of the store as a stage makes it: the file changed by `change`, the tool's reply after the middleware."""
    def handler(_request):
        path = root / STORE
        path.write_text(change(path.read_text(encoding="utf-8")), encoding="utf-8")
        return ToolMessage(content='{"status": "written"}', tool_call_id="w1")

    return middleware.wrap_tool_call(_Request(STORE), handler).content


def _renamed(text: str) -> str:
    return text.replace("func (s *Store) Create(", "func (s *Store) Add(")


def _reparametered(text: str) -> str:
    return text.replace("func NewStore(dataDir string) *Store {", "func NewStore(dataDir string, readOnly bool) *Store {")


def test_a_renamed_method_names_the_file_and_line_that_still_call_it(workspace):
    reply = _written(build_middleware(str(workspace)), workspace, _renamed)
    assert "it no longer defines `Store.Create`, which `go-notes-api/server.go` line 73 still uses" in reply


def test_new_parameters_name_the_file_and_line_that_call_the_old_form(workspace):
    reply = _written(build_middleware(str(workspace)), workspace, _reparametered)
    assert "it changed the parameters of `NewStore`, which `go-notes-api/main.go` line 26 still uses" in reply


def test_it_is_said_once_a_stage(workspace):
    middleware = build_middleware(str(workspace))
    _written(middleware, workspace, _renamed)
    again = _written(middleware, workspace, lambda text: text.replace("func (s *Store) Add(", "func (s *Store) Put("))
    assert "Store.Create" not in again


def test_a_change_inside_a_body_says_nothing(workspace):
    reply = _written(build_middleware(str(workspace)), workspace,
                     lambda text: text.replace("func NewStore(dataDir string) *Store {",
                                               "func NewStore(dataDir string) *Store {\n\t_ = dataDir"))
    assert reply == '{"status": "written"}'


def test_with_the_switch_off_the_reply_is_the_write_s_own(workspace, monkeypatch):
    monkeypatch.setenv("USES_NAMED_AT_THE_WRITE", "off")
    assert _written(build_middleware(str(workspace)), workspace, _renamed) == '{"status": "written"}'


def test_the_note_uses_no_product_word(workspace):
    reply = _written(build_middleware(str(workspace)), workspace, _renamed)
    note = reply.split('{"status": "written"}', 1)[1]
    assert "Other files use what this write changed" in note and not BANNED.search(note)
