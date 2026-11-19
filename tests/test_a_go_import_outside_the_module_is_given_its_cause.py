"""A Go import whose first part is not the module's path is given how Go names a package of this project.

Measured on one Go run: `go.mod` said `module notes-api`, the files imported `notes_api/store`, and `store.go` sat
beside `main.go` as `package main`; Go said "package notes_api/store is not in std", and three test rounds and two
rewrites left the import as it was.
"""
from __future__ import annotations

import pytest

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes

SAID = "main.go:14:2: package notes_api/store is not in std (/usr/local/go/src/notes_api/store)"


@pytest.mark.parametrize("pack", ["go-http-api", "go-gin-api", "go-cli", "go-library"])
def test_every_go_pack_names_the_cause(tmp_path, pack):
    contract.write(tmp_path, pack_named(pack), "notes-api", "Notes")

    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description="The product does not start for the acceptance suite.", severity="major",
        reproduction_steps="sh start.sh", expected_behavior="it starts", actual_behavior=SAID, affected_files=[],
        owner="backend")])

    assert KNOWN_CAUSE in defect.actual_behavior and "`module` line of `go.mod`" in defect.actual_behavior
