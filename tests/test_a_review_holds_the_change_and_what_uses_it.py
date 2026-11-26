"""A review's changed files that do not fit its request are given as their changed definitions and their uses (KG.8).

Measured: a security review whose changed files did not fit its source budget was told to open them itself, and 71% of
its input was re-reading (a code review 46%). With `REVIEWS_HOLD_THE_CHANGE_AND_ITS_USES` on, each such file is given
as the definitions holding changed lines, whole and numbered, each with the signatures of what uses it in other files;
files that fit are shown whole as before.

The project is a real Go product's files (`tests/captured/projects/go-notes-api`); the lines were read from them.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.agents import security_reviewer

PROJECTS = Path(__file__).parent / "captured" / "projects"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
STORE = "go-notes-api/store/store.go"
SERVER = "go-notes-api/server.go"
#: Room for the server's 4,819 characters and not the store's 5,825 beside them.
BUDGET = 5_000


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.delenv("SWITCH_OVERRIDES_FROM_SETTINGS", raising=False)
    monkeypatch.setenv("REVIEWS_HOLD_THE_CHANGE_AND_ITS_USES", "on")
    shutil.copytree(PROJECTS / "go-notes-api", tmp_path / "go-notes-api")
    (tmp_path / ".project-directory").write_text("go-notes-api")
    return tmp_path


def _security_request(root: Path, monkeypatch) -> str:
    monkeypatch.setattr(security_reviewer, "SOURCE_BUDGET", BUDGET)
    request = security_reviewer.build_security_review_request([SERVER, STORE], "read only", str(root))
    return request["messages"][-1]["content"]


def test_a_file_past_the_security_review_s_budget_is_given_as_its_definitions_and_their_callers(workspace,
                                                                                              monkeypatch):
    request = _security_request(workspace, monkeypatch)
    assert "130: func (s *Store) Create(title string, body string) (Note, error) {" in request
    assert ("`go-notes-api/server.go` lines 54-81: func createHandler(s *store.Store) func(http.ResponseWriter, "
            "*http.Request) {") in request
    assert f"--- {STORE} (not shown: the budget for this request is full) ---" not in request


def test_with_the_switch_off_the_file_is_left_to_be_opened(workspace, monkeypatch):
    monkeypatch.setenv("REVIEWS_HOLD_THE_CHANGE_AND_ITS_USES", "off")
    request = _security_request(workspace, monkeypatch)
    assert f"--- {STORE} (not shown: the budget for this request is full) ---" in request
    assert "130: func (s *Store) Create(" not in request


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def test_only_the_definitions_holding_a_changed_line_are_given(workspace):
    from app.agents import reviews_hold_the_change

    _git(workspace, "init", "-q")
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-qm", "accepted")
    since = _git(workspace, "rev-parse", "HEAD")
    path = workspace / STORE
    path.write_text(path.read_text().replace("func (s *Store) Create(title string, body string) (Note, error) {",
                                             "func (s *Store) Create(title string, body string) (Note, error) {\n"
                                             "\t// trimmed by the caller"), encoding="utf-8")
    text, given = reviews_hold_the_change.section(workspace, [STORE], since)
    assert given == [STORE]
    assert "131: \t// trimmed by the caller" in text
    assert "38: func NewStore(dataDir string) *Store {" not in text


def test_what_the_section_says_uses_no_product_word(workspace, monkeypatch):
    request = _security_request(workspace, monkeypatch)
    said = request[request.index("--- The changed definitions of the files not shown whole above"):]
    prose = "\n".join(line for line in said.splitlines() if not re.match(r"^\d+: |^- `", line))
    assert not BANNED.search(prose)
