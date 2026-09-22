"""A refusal must not assert a fact the harness elsewhere disproves.

`npx serve -p 3000 --cors` was refused sixteen times across the stored runs
with "There is also no browser to open the page with. To check the page, read
the files and assert on them from a test."

Both halves are false in a workspace with Playwright - which is the workspace
the harness's own checks push every UI product toward. Run-35424714's
`playwright.config.ts` carried `webServer: { command: 'npx serve .' }`, started
it, logged "Accepting connections at http://localhost:3000" and ran 34 browser
tests with real passes and failures. The same program, in the same container,
refused to the agent and granted to the test runner.

The remedy was worse than the false fact: "read the files and assert on them
from a test" describes the hand-built DOM that `_refuse_a_hand_built_dom_again`
refuses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tools.sandbox import (
    CommandNotAllowed,
    _any_manifest_declares_a_browser_runner,
    _how_to_serve_the_page_instead,
    validate_command,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "todo-app").mkdir()
    return tmp_path


def _manifest(where: Path, packages: dict) -> None:
    where.mkdir(parents=True, exist_ok=True)
    (where / "package.json").write_text(
        json.dumps({"name": "p", "devDependencies": packages}), encoding="utf-8"
    )


def test_a_server_is_still_refused(workspace: Path) -> None:
    """It would sit until the timeout. That half was always right."""
    with pytest.raises(CommandNotAllowed) as raised:
        validate_command(["npx", "serve", "-p", "3000"], "backend_specialist", workspace)

    assert "runs until it is stopped" in str(raised.value)


def test_with_playwright_it_names_the_route_that_works(workspace: Path) -> None:
    _manifest(workspace / "todo-app", {"@playwright/test": "^1.40.0"})

    with pytest.raises(CommandNotAllowed) as raised:
        validate_command(["npx", "serve", "."], "backend_specialist", workspace)
    message = str(raised.value)

    assert "webServer" in message
    assert "playwright.config.ts" in message


def test_it_stops_claiming_there_is_no_browser(workspace: Path) -> None:
    _manifest(workspace / "todo-app", {"@playwright/test": "^1.40.0"})

    message = _how_to_serve_the_page_instead(str(workspace))

    assert "browsers do run" in message
    assert "no browser" not in message


def test_it_does_not_send_the_stage_to_build_a_dom(workspace: Path) -> None:
    """The old remedy is refused by another part of this same harness."""
    _manifest(workspace / "todo-app", {"@playwright/test": "^1.40.0"})

    message = _how_to_serve_the_page_instead(str(workspace))

    assert "read the files and assert on them" not in message
    assert "global.document" in message


def test_without_a_runner_it_says_how_to_get_one(workspace: Path) -> None:
    _manifest(workspace / "todo-app", {"eslint": "^9.0.0"})

    message = _how_to_serve_the_page_instead(str(workspace))

    assert "npm install -D @playwright/test" in message
    assert "webServer" in message


def test_the_manifest_is_found_in_a_subdirectory(workspace: Path) -> None:
    """Every run so far has put the product in a directory of its own, and
    `validate_command` has only the workspace root to search from."""
    _manifest(workspace / "todo-app", {"playwright": "^1.40.0"})

    assert _any_manifest_declares_a_browser_runner(str(workspace))


def test_a_root_manifest_counts_too(workspace: Path) -> None:
    _manifest(workspace, {"@playwright/test": "^1.40.0"})

    assert _any_manifest_declares_a_browser_runner(str(workspace))


def test_no_manifest_anywhere_is_not_a_browser(workspace: Path) -> None:
    assert not _any_manifest_declares_a_browser_runner(str(workspace))


def test_an_unreadable_manifest_is_not_a_browser(workspace: Path) -> None:
    (workspace / "todo-app" / "package.json").write_text("{not json", encoding="utf-8")

    assert not _any_manifest_declares_a_browser_runner(str(workspace))


def test_a_missing_root_is_not_a_browser() -> None:
    assert not _any_manifest_declares_a_browser_runner("/nowhere/at/all")


# --- the correction that belongs before the call, not after it ------------


def test_the_tool_says_code_goes_in_a_file() -> None:
    """`node -e` was refused 54 times across fourteen runs - the largest class
    of command failure. The refusal works: 27 of those were followed
    immediately by a `write_artifact`. It costs a model call each time, and
    the tool's own description never mentioned it."""
    from app.tools.agent_toolkit import build_terminal_command_tool

    description = build_terminal_command_tool(".", "backend_specialist").description or ""

    assert "node -e" in description
    assert "write_artifact" in description
    assert "reviewable" in description


def test_the_tool_says_where_a_server_belongs() -> None:
    from app.tools.agent_toolkit import build_terminal_command_tool

    description = build_terminal_command_tool(".", "backend_specialist").description or ""

    assert "webServer" in description
    assert "until the" in description
