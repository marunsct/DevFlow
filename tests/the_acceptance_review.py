"""The acceptance review run on a workspace with a suite in it: the suite's runner and the QA lead stood in for.

For behaviour tests of `acceptance_review`, the node that sends a suite back to its writers or locks it. Only the
edges are replaced - the sandbox that runs the suite (`suite.run` returns what the test says was measured), the QA
lead's model (`_run_gated_agent` answers with the review the test gives) and the contract probes that start the
product at the lock. Every check of the suite runs for real on the files in the workspace, and the suite's own
state under `.harness/` is real.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence
from unittest.mock import patch

from app.acceptance import junit, suite
from app.acceptance.suite import AcceptanceResult
from app.stacks import contract, pack_named

CONFIG = {"configurable": {"thread_id": "t", "run_id": "r"}}
#: Where the suite keeps its own state: its criteria, its lock, the send-backs it has spent.
SAVED = ".harness/acceptance.json"

#: A test no product can pass: it compares the response's `status` method itself with 201.
NO_PRODUCT_CAN_PASS = """import { test, expect } from '@playwright/test';
test('[AC-1] creates', async ({ request }) => {
  const response = await request.post('/notes', { data: { title: 'a', body: 'b' } });
  expect(response.status).toBe(201);
});
"""
#: The same test written so a working product passes it.
A_FAIR_TEST = NO_PRODUCT_CAN_PASS.replace("response.status)", "response.status())")
#: How the suite's runner reports the test, failing and passing.
FAILED = ("api.spec.js › [AC-1] creates", "failed", "Error: expect(received).toBe(expected)")
PASSED = ("api.spec.js › [AC-1] creates", "passed")


def a_service_suite(root: Path, text: str, name: str = "api.spec.js", criteria: Sequence[str] = ("AC-1",)) -> Path:
    """A service project in `notes/` whose acceptance suite is one spec file holding `text`, for `criteria`."""
    from app.acceptance.criteria import Criterion

    contract.write(root, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = root / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")
    suite.save_criteria(root, [Criterion(id=each, text=f"{each} holds", source="brief") for each in criteria])
    return root


def measured(*tests: tuple[str, str] | tuple[str, str, str]) -> AcceptanceResult:
    """A suite that ran, with each test as (name, outcome[, message])."""
    return AcceptanceResult(ran=True, exit_code=0 if all(t[1] == "passed" for t in tests) else 1, report=junit.Report(
        tests=[junit.TestResult(name=t[0], outcome=t[1], message=t[2] if len(t) > 2 else "") for t in tests]))


def qa_lead(approved: bool, *findings: str) -> Any:
    """What the QA lead answers when it reads the suite."""
    from app.agents.acceptance_reviewer import AcceptanceReviewOutput

    return AcceptanceReviewOutput(approved=approved, findings=list(findings))


def reviewed(
    root: Path,
    result: AcceptanceResult,
    *,
    rounds: int = 1,
    saved: dict[str, Any] | None = None,
    review: Any = None,
    interface_contract: Sequence[str] = (),
    specification: Any = None,
    brief: str = "",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """`acceptance_review`'s update for round `rounds`, and each request the QA lead was sent.

    `saved` is merged into the suite's own saved state first (what earlier send-backs left there); `specification`,
    when given, stands in for one holding only `interface_contract`; `brief` is the brief's text."""
    from app.graph import acceptance_nodes

    if saved:
        kept = json.loads((root / SAVED).read_text(encoding="utf-8")) if (root / SAVED).is_file() else {}
        (root / SAVED).write_text(json.dumps({**kept, **saved}), encoding="utf-8")
    asked: list[dict[str, Any]] = []

    def the_qa_lead(state, config, **kwargs):
        asked.append(kwargs)
        return {"__acceptance_review__": review if review is not None else qa_lead(True)}

    state = {
        "repository": SimpleNamespace(root_path=str(root)),
        "acceptance_round": rounds,
        "technical_specification": specification if specification is not None
        else SimpleNamespace(interface_contract=list(interface_contract)),
        **({"document": SimpleNamespace(text=brief)} if brief else {}),
    }
    ctx = SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=str(root), allow_subdirectories=True)
    with patch.object(suite, "run", lambda repo_root, **kwargs: result), \
            patch("app.agents.acceptance_reviewer.create_acceptance_reviewer_agent", lambda **kwargs: None), \
            patch("app.agents.reviews_without_reasoning.the_review_model", lambda model: model), \
            patch("app.acceptance.interface_contract.probe_at_the_lock", lambda repo_root: []), \
            patch("app.graph.workflow._run_gated_agent", the_qa_lead):
        update = acceptance_nodes.acceptance_review(state, CONFIG, ctx)
    return update, asked


def saved_state(root: Path) -> dict[str, Any]:
    """The suite's own saved state."""
    return json.loads((root / SAVED).read_text(encoding="utf-8"))


def recorded_checks(root: Path) -> list[str]:
    """The check each recorded finding was raised by, in order (`.harness/check-findings.jsonl`)."""
    path = root / ".harness" / "check-findings.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line)["check"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
