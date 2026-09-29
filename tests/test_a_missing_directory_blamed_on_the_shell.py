"""An error that calls a present program missing is about something else.

One run's `specialist_backend_2` ran its Playwright suite and got
`Error: Failed to launch: Error: spawn /bin/sh ENOENT`. It concluded the
container "lacks /bin/sh, which is required for Playwright" and deleted the
end-to-end suite, its config and its server. `/bin/sh` was there: the config's
`webServer.cwd` named a directory that did not exist, and Node reports a child
started in a missing directory by the name of the program it was starting.
"""

from __future__ import annotations

from pathlib import Path

from app.plugins.seed import SEED_INSTRUCTIONS
from app.tools.sandbox import _a_missing_path_that_is_here


def test_a_present_shell_reported_missing_gets_a_note(tmp_path: Path) -> None:
    present = tmp_path / "sh"
    present.write_text("", encoding="utf-8")

    note = _a_missing_path_that_is_here(
        {"stdout": f"Error: Failed to launch: Error: spawn {present} ENOENT\n", "stderr": ""}
    )

    assert f"'{present}' exists in this environment" in note
    assert "most often a working directory that does not exist" in note


def test_the_other_runtimes_wording_is_read_too(tmp_path: Path) -> None:
    present = tmp_path / "python3"
    present.write_text("", encoding="utf-8")

    note = _a_missing_path_that_is_here(
        {"stderr": f"FileNotFoundError: [Errno 2] No such file or directory: '{present}'"}
    )

    assert "exists in this environment" in note


def test_a_path_that_really_is_missing_says_nothing(tmp_path: Path) -> None:
    gone = tmp_path / "not-here"

    assert _a_missing_path_that_is_here({"stderr": f"spawn {gone} ENOENT"}) == ""


def test_the_command_runner_attaches_it() -> None:
    import inspect

    from app.tools import sandbox

    assert "_a_missing_path_that_is_here(outcome)" in inspect.getsource(sandbox)


def test_the_page_stack_says_where_webserver_cwd_is_resolved() -> None:
    page = " ".join(SEED_INSTRUCTIONS["html"].split())

    assert "Its `cwd`, if you give one, is relative to the config file" in page
    assert "spawn /bin/sh ENOENT" in page
