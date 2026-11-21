"""A Go project whose top folder declares two package names is given the one-package-per-folder rule as its cause.

Measured on one Go run: `server_test.go` said `package server` and `store.go` said `package store` beside `main.go`'s
`package main`; the product did not start for the acceptance suite and the first fix left the package lines as they were.
"""
from __future__ import annotations

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes


def test_two_package_names_in_one_folder_are_given_the_rule(tmp_path):
    contract.write(tmp_path, pack_named("go-http-api"), "notes-api", "Notes")
    said = "[WebServer] found packages main (main.go) and server (server.go) in /workspace/notes-api"

    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description="The product does not start for the acceptance suite.", severity="major",
        reproduction_steps="sh start.sh", expected_behavior="it answers", actual_behavior=said, affected_files=[],
        owner="backend")])

    assert KNOWN_CAUSE in defect.actual_behavior and "one package" in defect.actual_behavior
