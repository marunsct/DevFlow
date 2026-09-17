"""A reviewer that cannot see the code cannot review it.

`build_security_review_request` gave the security reviewer a list of filenames
and a tool-permissions note. It has read tools and could open each file, but it
answers in two to four model calls, so in practice it never did.

Across every transcript on disk: 33 security reviews, every one
`status: passed` with `findings: []` and `## Findings — _Not specified._`. Not
one finding has ever been recorded by this stage.

Every other reviewer here is already handed its material - the milestone
reviewer gets test evidence, the execution ledger and the cross-file checks;
the architecture reviewer gets the specification. This one got filenames.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.security_reviewer import (
    SOURCE_BUDGET,
    build_security_review_request,
)

SOURCE = "function addTask(t) {\n  document.body.innerHTML = t;\n}\n"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "app.js").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "app" / "index.html").write_text("<button id='go'>Go</button>", encoding="utf-8")
    return tmp_path


def _body(project: Path, files: list[str]) -> str:
    return build_security_review_request(files, "role: security", str(project))[
        "messages"
    ][0]["content"]


def test_the_source_is_in_the_request(project: Path):
    body = _body(project, ["app/app.js"])

    assert "document.body.innerHTML = t;" in body


def test_the_filenames_are_still_listed(project: Path):
    body = _body(project, ["app/app.js"])

    assert "--- Changed files under review ---" in body
    assert "- app/app.js" in body


def test_it_says_this_is_the_code_not_a_summary(project: Path):
    assert "not a summary" in _body(project, ["app/app.js"])


def test_the_tool_permissions_survive(project: Path):
    assert "role: security" in _body(project, ["app/app.js"])


def test_a_lockfile_or_test_is_not_put_in_front_of_it(project: Path):
    """A vulnerability in the product does not live in `package-lock.json`."""
    (project / "app" / "package-lock.json").write_text("{}" * 400, encoding="utf-8")
    (project / "app" / "big.lock").write_text("noise", encoding="utf-8")

    body = _body(project, ["app/big.lock"])

    assert "None of the changed files could be read" in body


def test_a_file_that_does_not_exist_is_skipped_not_fatal(project: Path):
    body = _body(project, ["app/app.js", "app/gone.js"])

    assert "document.body.innerHTML" in body
    assert "gone.js" in body  # still named in the file list


def test_no_readable_files_says_so_and_points_at_the_read_tools(project: Path):
    body = _body(project, ["app/missing.js"])

    assert "Open them with your read tools" in body


def test_the_budget_stops_an_unbounded_request(project: Path):
    big = "x" * (SOURCE_BUDGET + 10)
    (project / "app" / "huge.js").write_text(big, encoding="utf-8")

    body = _body(project, ["app/huge.js", "app/app.js"])

    assert len(body) < SOURCE_BUDGET * 2
    assert "budget for this request is full" in body


def test_the_page_is_reviewed_too(project: Path):
    """An inline handler or a missing escape lives in the HTML as often as the JS."""
    body = _body(project, ["app/index.html"])

    assert "<button id='go'>Go</button>" in body
