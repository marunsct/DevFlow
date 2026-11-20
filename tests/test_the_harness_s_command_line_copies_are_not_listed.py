"""The harness's copies of command-line code are not listed to a stage, and the scratch rule says they are not its own.

Code passed on a command line is saved to `tmp-inline-<hash>.<ext>` so it can be read afterwards; the harness removes
those files itself. Per-role audit 2026-11-20: a suite writer saw them listed, read "remove scratch files with
`delete_artifact` when done", and called `delete_artifact` 31 times on them, each answered "the harness removes it
itself".
"""

from __future__ import annotations

import re

from app.agents.workspace_backend import WorkspaceBackend
from app.agents.workspace_digest import render_workspace_digest

COPY = "tmp-inline-3f9c2a1b.cjs"


def _workspace(tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "server.js").write_text("export function start() {}\n")
    (tmp_path / "notes" / COPY).write_text("console.log(1)\n")
    return tmp_path


def _listed(result) -> list[str]:
    return [str(entry["path"] if isinstance(entry, dict) else entry.path) for entry in result.entries]


def test_the_workspace_digest_does_not_list_them(tmp_path) -> None:
    digest = render_workspace_digest(_workspace(tmp_path))

    assert "notes/server.js" in digest
    assert "tmp-inline-" not in digest


def test_a_stage_s_ls_does_not_list_them(tmp_path) -> None:
    backend = WorkspaceBackend(root_dir=str(_workspace(tmp_path)), virtual_mode=True)

    listed = _listed(backend.ls("/notes"))

    assert any(path.endswith("server.js") for path in listed)
    assert not any("tmp-inline-" in path for path in listed)


def test_a_stage_s_glob_does_not_find_them(tmp_path) -> None:
    backend = WorkspaceBackend(root_dir=str(_workspace(tmp_path)), virtual_mode=True)

    found = [str(m["path"] if isinstance(m, dict) else m) for m in backend.glob("**/*").matches]

    assert any(path.endswith("server.js") for path in found)
    assert not any("tmp-inline-" in path for path in found)


def test_the_scratch_file_rule_says_the_harness_removes_them_itself() -> None:
    from app.agents.role_agent import SCRATCH_FILES_RULE

    flat = " ".join(SCRATCH_FILES_RULE.split())

    assert "`tmp-inline-*`" in flat and "removes it itself" in flat and "leave it" in flat


def test_the_scratch_file_rule_avoids_the_banned_words() -> None:
    from app.agents.role_agent import SCRATCH_FILES_RULE

    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", SCRATCH_FILES_RULE, re.I)
