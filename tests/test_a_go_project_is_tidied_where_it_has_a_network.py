"""A Go project's modules are tidied by its install, the one command that has a network.

Measured on one Go run: the drafted `go.mod` did not match the imports, every build and unit run said "updates to
go.mod needed; to update it: go mod tidy", and the guide told the fixers to run it - but only the install has a network,
so no fixer could, and the product never started. One Go pack's install tidied first; two did not.
"""
from __future__ import annotations

import pytest

from app.stacks import pack_named

GO_PACKS = ["go-http-api", "go-gin-api", "go-cli", "go-library"]


@pytest.mark.parametrize("name", GO_PACKS)
def test_every_go_pack_tidies_before_it_builds(name):
    pack = pack_named(name)

    assert pack.install[0] == ("go", "mod", "tidy")
    assert ("go", "build", "./...") in pack.install
