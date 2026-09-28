"""What a timed-out command is told depends on what this workspace has.

Measured on one run. `npx playwright test` timed out and was answered
with "there is no browser to open a page with ... To check a page, read the
file and assert on its contents from a test". Seven minutes later
`npx playwright test --project=Desktop` ran 34 tests in the same sandbox, with
real passes and real failures.

The advice was not merely wrong about the environment. "Read the file and
assert on its contents from a test" describes the hand-built DOM that
`a_dom_built_by_hand` refuses - one part of the harness telling a stage to do
what another part stops it doing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.sandbox import (
    _TIMEOUT_ADVICE,
    _TIMEOUT_ADVICE_WITH_A_BROWSER,
    _a_browser_runner_is_installed,
    _timeout_advice,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    return tmp_path


def _manifest(where: Path, packages: dict) -> None:
    import json

    (where / "package.json").write_text(
        json.dumps({"name": "p", "devDependencies": packages}), encoding="utf-8"
    )


def test_a_workspace_with_playwright_is_told_browsers_work(workspace: Path) -> None:
    _manifest(workspace / "app", {"@playwright/test": "^1.40.0"})

    assert _a_browser_runner_is_installed(str(workspace), "app")
    assert _timeout_advice(str(workspace), "app") == _TIMEOUT_ADVICE_WITH_A_BROWSER


def test_it_names_what_to_try_instead(workspace: Path) -> None:
    _manifest(workspace / "app", {"playwright": "^1.40.0"})

    advice = _timeout_advice(str(workspace), "app")

    assert "--project=" in advice
    assert "webServer" in advice


def test_it_does_not_ask_for_the_thing_the_harness_refuses(workspace: Path) -> None:
    _manifest(workspace / "app", {"@playwright/test": "^1.40.0"})

    advice = _timeout_advice(str(workspace), "app")

    assert "global.document" in advice
    assert "refused elsewhere" in advice
    assert "read the file and assert on its contents" not in advice


def test_a_workspace_without_one_reads_as_before(workspace: Path) -> None:
    _manifest(workspace / "app", {"eslint": "^9.0.0"})

    assert not _a_browser_runner_is_installed(str(workspace), "app")
    assert _timeout_advice(str(workspace), "app") == _TIMEOUT_ADVICE


def test_no_manifest_at_all_reads_as_before(workspace: Path) -> None:
    assert _timeout_advice(str(workspace), "app") == _TIMEOUT_ADVICE


def test_the_manifest_may_be_above_the_working_directory(workspace: Path) -> None:
    """`npm test` from a subdirectory of a project that installed it."""
    _manifest(workspace, {"@playwright/test": "^1.40.0"})

    assert _a_browser_runner_is_installed(str(workspace), "app")


def test_a_runtime_dependency_counts_too(workspace: Path) -> None:
    import json

    (workspace / "app" / "package.json").write_text(
        json.dumps({"name": "p", "dependencies": {"playwright": "^1.40.0"}}),
        encoding="utf-8",
    )

    assert _a_browser_runner_is_installed(str(workspace), "app")


def test_an_unreadable_manifest_is_not_a_browser(workspace: Path) -> None:
    (workspace / "app" / "package.json").write_text("{not json", encoding="utf-8")

    assert not _a_browser_runner_is_installed(str(workspace), "app")


def test_both_timeout_messages_use_it() -> None:
    """The timeout itself and the refusal to repeat it say the same thing.

    Two call sites with different parameter names - `_execute_here` holds the
    workspace as `workspace` and its subdirectory as `run_in` - so this counts
    calls rather than one spelling of the arguments."""
    import inspect

    from app.tools import sandbox

    source = inspect.getsource(sandbox)
    calls = source.count("+ _timeout_advice(")

    assert calls == 2, f"expected both timeout messages to choose the advice, found {calls}"
