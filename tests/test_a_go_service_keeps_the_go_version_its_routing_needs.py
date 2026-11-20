"""The standard-library Go service keeps `go.mod`'s `go` line at 1.22 or later: routing by method and path needs it.

Measured on one run: a backend work order rewrote `go.mod` to `go 1.21`, every route answered 404, and the product did
not start for the acceptance suite until a fixer found the module version.
"""
from __future__ import annotations

import re

import pytest

from app.stacks import pack_named

PACK = pack_named("go-http-api")


def _kept(text: str) -> list[str]:
    return [line for pattern, line in PACK.required_signatures.get("go.mod", ()) if not re.search(pattern, text, re.M)]


def test_a_go_line_lowered_below_1_22_is_told_to_be_put_back():
    assert _kept("module notes-api\n\ngo 1.21\n") == [f"go {PACK.required_signatures['go.mod'][0][1].split()[1]}"]


@pytest.mark.parametrize("line", ["go 1.22", "go 1.26", "go 1.26.1", "go 1.30"])
def test_a_go_line_at_1_22_or_later_is_kept_as_written(line):
    assert _kept(f"module notes-api\n\n{line}\n") == []
