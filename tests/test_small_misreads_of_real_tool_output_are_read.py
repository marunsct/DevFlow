"""Three shapes real tools print that their readers missed (deep review of the parsers, 2026-11-25, finding 6).

Each input is a real one, captured from runs (`tests/captured/`):

- a status checked with `toContain` - `expect([400, 422]).toContain(res.status())` prints "Expected value: 500" and
  "Received array: [400, 422]" - gave no wrong answer, so the failures it shares with others were not one cause;
- the tool layer's own refusal of a call missing an argument ("Error invoking tool ... Field required") was the one
  refusal shape the count of a stage's refused calls did not read, so such a call could be sent without end;
- rustc's names a crate lacks (E0433 "could not find", E0425 "in crate", E0599 on a crate's type, E0432 for a crate
  never declared) were read as naming nothing, so the installed crate's own files were never asked.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.acceptance.first_failing_step import the_wrong_answer
from app.agents.settled_answer import IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL, _a_tool_refused_identically
from app.analysis.installed_packages import missing_in

CAPTURED = Path(__file__).parent / "captured"


def _captured(name: str):
    return json.loads((CAPTURED / name).read_text(encoding="utf-8"))


def test_a_status_outside_the_list_a_test_allowed_is_the_wrong_answer():
    messages = _captured("playwright-1.64-status-not-in-a-to-contain-list.json")

    assert sorted(the_wrong_answer(message) for message in messages) == ["404", "404", "409", "500"]


@pytest.mark.parametrize("refused", ["edit_artifact", "read_file"])
def test_a_call_the_tool_layer_refuses_again_and_again_is_a_loop(refused):
    call, result = [record for record in _captured("tool-calls-refused-by-the-tool-layer.json")
                    if record["tool"] == refused]
    messages = []
    for n in range(IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL):
        messages.append(AIMessage(content="", tool_calls=[{"id": f"c{n}", "name": refused, "args": call["args"]}]))
        messages.append(ToolMessage(tool_call_id=f"c{n}", content=result["content"]))

    assert _a_tool_refused_identically(messages) == (refused, IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL)


def _rustc(start: str) -> str:
    return next(line.strip() for line in (CAPTURED / "rustc-names-not-found.txt").read_text().splitlines()
                if line.startswith(start))


@pytest.mark.parametrize(("line", "crate", "name"), [
    ("error[E0433]: failed to resolve: could not find `SqlitePoolOptions` in `sqlx`", "sqlx", "SqlitePoolOptions"),
    ("error[E0433]: failed to resolve: could not find `TestClient` in `axum`", "axum", "TestClient"),
    ("error[E0425]: cannot find function `app_with_store` in crate", "notes_api", "app_with_store"),
    ("error[E0432]: unresolved import `http_body_util`", "http_body_util", ""),
    ("error[E0599]: no variant or associated item named `QueryReturnsNoRows`", "rusqlite", "QueryReturnsNoRows"),
    ("error[E0599]: no method named `as_ref` found for struct `tokio::sync::RwLockReadGuard", "tokio", "as_ref"),
])
def test_a_name_rustc_says_a_crate_lacks_is_read(line, crate, name):
    missing = missing_in(_rustc(line))

    assert (missing.package, missing.name, missing.family) == (crate, name, "rust")


@pytest.mark.parametrize("line", [
    "error[E0432]: unresolved import `crate::models::AppState`",
    "error[E0599]: no method named `as_array` found for struct `StatusCode`",
])
def test_a_rustc_name_with_no_crate_in_it_names_no_package(line):
    """The product's own path, or a type written without its crate: there is no installed package to ask."""
    assert missing_in(_rustc(line)) is None


def test_a_real_playwright_failure_opening_with_its_header_line_still_gives_its_status():
    """Playwright's message opens with the test's own header line; the status assertion below it is still read."""
    rate_limited, refused, asserted = _captured("playwright-1.64-failed-tests-a-helper-threw-in.json")

    assert the_wrong_answer(asserted) == "429"
