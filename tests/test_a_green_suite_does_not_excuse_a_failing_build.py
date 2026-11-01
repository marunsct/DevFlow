"""What a run has: a React pack's contract, a green suite, no judgement model, a build that fails. Through the round and the release.

Only the sandbox's runner is a stand-in; the harness's own names for the check appear nowhere here.
"""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.graph import acceptance_nodes, delivery
from app.stacks import contract, scaffold

COMPILER = "src/App.tsx(3,18): error TS2503: Cannot find namespace 'JSX'."


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    (root / "web" / "src").mkdir(parents=True)
    (root / "web" / "src" / "App.tsx").write_text("export const App = 1;\n")
    (root / "web" / "package.json").write_text(json.dumps({"scripts": {"build": "tsc --noEmit && vite build"}}))
    (root / ".harness").mkdir()
    (root / contract.CONTRACT_FILE).write_text(json.dumps({"pack": "browser-react", "project": "web"}))
    (root / ".gitignore").write_text(".harness/\n")
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "first"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    def runner(_root):
        def run(argv, category, where):
            if list(argv)[:3] == ["npm", "run", "build"]:
                return {"returncode": "2", "stdout": COMPILER, "stderr": ""}
            return {"returncode": "0", "stdout": "", "stderr": ""}
        return run

    monkeypatch.setattr(scaffold, "sandbox_runner", runner)
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda _s: ([], "npx playwright test"))
    monkeypatch.setattr(suite, "last_result", lambda _r: {"ran": True, "failed": 0})
    monkeypatch.setattr(acceptance_nodes, "_owner_for", lambda _s, _t: "frontend")
    monkeypatch.setattr(delivery, "_unit_tests_failing", lambda _r: [])
    return root


def test_the_round_finds_it(project):
    state = {"repository": SimpleNamespace(root_path=str(project))}
    defects = acceptance_nodes.failing_due_defects(state, [])
    assert [d.severity for d in defects] == ["blocking"]
    assert COMPILER in defects[0].actual_behavior


def test_the_release_does_not_complete(project):
    update = delivery.release(
        {"repository": SimpleNamespace(root_path=str(project)), "release_attempts": 0},
        {"configurable": {}},
        SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=str(project), allow_subdirectories=True),
    )
    assert update["stage"] == "technical_lead"
    assert COMPILER in update["revision_comments"][-1]
