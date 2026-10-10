"""Tests that the scaffold stage is not skipped when contract was inferred.

Before the scaffold stage runs, architecture stages and file checks can infer
the stack pack and record stack-pack.json in .harness. The scaffold node must
still run to scaffold the project files and prove them with smoke tests, rather
than skipping scaffolding because a contract record already exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from langchain_core.runnables import RunnableConfig

from app.graph import acceptance_nodes as nodes
from app.stacks import contract


def test_scaffold_runs_even_if_contract_was_already_inferred(tmp_path: Path, monkeypatch) -> None:
    # 1. Setup workspace with decisions and technology stack, exactly as
    # stack_selector and architecture stages leave it.
    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir(parents=True)
    decisions = [
        {
            "id": "DR-1",
            "point": "stack",
            "decision": "JavaScript",
            "options": ["Browser app in plain JavaScript modules"],
            "rationale": "browser-javascript",
        }
    ]
    (harness_dir / "decisions.json").write_text(json.dumps(decisions), encoding="utf-8")
    (tmp_path / ".project-directory").write_text("sample-app\n", encoding="utf-8")

    # 2. Simulate workspace checks or file operations in architecture stages
    # that infer the contract before scaffold runs.
    inferred = contract.the_pack(tmp_path)
    assert inferred is not None
    assert contract.read(tmp_path) is not None

    calls = []

    def fake_scaffold(root, pack, project, title, package=None):
        calls.append((pack.name, project, title))
        return SimpleNamespace(ok=True, problem="")

    monkeypatch.setattr("app.stacks.scaffold.scaffold", fake_scaffold)
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)

    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "stack_pack": "browser-javascript",
        "product_intake": SimpleNamespace(product_name="Sample App"),
    }
    config: RunnableConfig = {"configurable": {}}
    ctx = SimpleNamespace()

    update = nodes.scaffold(state, config, ctx)

    # Scaffolding must run!
    assert calls == [("browser-javascript", "sample-app", "Sample App")]
    assert update["stage"] == "acceptance_author"
    assert "scaffold_result" in update
    assert update["scaffold_result"]["ok"] is True
