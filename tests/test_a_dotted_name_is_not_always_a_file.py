"""`store.read` and `styles.css` have the same shape; only one is a file.

One run's sprint scope read "task-store.mjs: createTask(), parseTask(),
serializeTask(), store.read(), store.write()". The plan gave every file a work
order and was handed back twice, then dispatched as not ready, because no work
order "listed" `store.read` and `store.write`.
"""

from __future__ import annotations

import pytest

from app.analysis.file_kinds import names_a_file
from app.analysis.integration_checks import files_named_in, later_sprint_files_in


@pytest.mark.parametrize(
    "token", ["index.html", "styles.css", "task-store.mjs", "state.test.js", "src/app.py", "schema.sql"]
)
def test_a_file_is_a_file(token: str) -> None:
    assert names_a_file(token)


@pytest.mark.parametrize("token", ["store.read", "store.write", "config.custom", "user.name", "nodot"])
def test_a_member_is_not(token: str) -> None:
    assert not names_a_file(token)


def test_an_extension_the_project_already_uses_counts() -> None:
    assert not names_a_file("model.zig")
    assert names_a_file("model.zig", {"zig"})
    assert names_a_file("model.zig", {".ZIG"})


def test_a_call_is_never_a_file_name() -> None:
    assert files_named_in("call store.read() and then render.js() runs") == set()


def test_the_run_s_scope_names_one_file() -> None:
    scope = (
        "- task-store.mjs: createTask(), parseTask(), serializeTask(), store.read(), store.write()\n"
        "- Unit tests for createTask(), parseTask(), serializeTask(), store.read/write()"
    )

    assert files_named_in(scope) == {"task-store.mjs"}


def test_a_finding_about_a_method_is_not_a_finding_about_a_later_sprint_s_file() -> None:
    """`later_sprint_files_in` reads the same names; a member is not a file there either."""
    finding = "store.read is never called by the page."

    assert later_sprint_files_in(finding, "Build the store.", "Call store.read from index.html.") == []


def test_a_finding_about_a_later_sprint_s_file_is_still_recognised() -> None:
    finding = "The repository contains no index.html entry point."

    assert later_sprint_files_in(finding, "Build the task store.", "Add index.html in the project root.") == [
        "index.html"
    ]
