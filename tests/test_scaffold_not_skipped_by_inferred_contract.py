"""The scaffold stage is not skipped because a contract record is already there.

A contract can be on disk before the scaffold stage runs - one run's lookup
wrote a guessed one, which no longer happens, and a scaffold that could not be
proven writes an unproven one. The scaffold node runs on whether its own
result says it succeeded, not on whether a record exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from langchain_core.runnables import RunnableConfig

from app.graph import acceptance_nodes as nodes
from app.stacks import contract


def test_scaffold_runs_even_if_a_contract_record_is_there(tmp_path: Path, monkeypatch) -> None:
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

    # 2. A contract record is already on disk before the scaffold runs.
    from app.stacks import pack_named

    contract.write(tmp_path, pack_named("browser-javascript"), "sample-app", "Sample App", scaffolded=False)
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
