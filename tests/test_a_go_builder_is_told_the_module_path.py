"""A Go service's builders are told its module path, which is not the project folder's name.

Measured on one Go run: the project folder was `notes-api`, `go.mod` said `module notes_api`, and the drafted
`server.go` imported `notes-api/store` - "is not in std" - so the product did not build and no test reached it.
"""

from __future__ import annotations

import re

import pytest

from app.stacks import pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.mark.parametrize("name", ["go-http-api", "go-gin-api"])
def test_the_guide_names_the_module_path_a_subpackage_is_imported_by(name):
    pack = pack_named(name)
    guide = pack.filled(pack.guide, "notes-api", "Notes", "notes_api")
    assert "The module path is `notes_api`" in guide
    assert "imported as `notes_api/store`" in guide
    assert "module notes_api" in pack.render("notes-api", "Notes", "notes_api")["go.mod"]
    assert not BANNED.search(guide)
