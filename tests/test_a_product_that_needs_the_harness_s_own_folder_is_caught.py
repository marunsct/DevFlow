"""A product that names the harness's own home folder is refused at the write and blocks its release.

Measured on a C# run: offline restores failed, a re-planned work order had a `nuget.config` point NuGet at
`/workspace/.agent-home/.nuget/packages/` - the sandbox's own cache - and the product passed its whole suite inside
the harness and failed to restore anywhere else: 0 of 9 hidden tests, and the run was delivered.
"""
from __future__ import annotations

import re

import pytest

from app.completion_verdict import is_blocking
from app.graph import delivery
from app.tools.repository import RepositoryToolError, write_approved_artifact

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
NUGET = ('<configuration><packageSources><add key="local" value="/workspace/.agent-home/.nuget/packages/" />'
         '</packageSources></configuration>\n')


def test_a_product_file_naming_the_harness_s_home_is_refused(tmp_path):
    (tmp_path / "notes-api").mkdir()

    with pytest.raises(RepositoryToolError) as refused:
        write_approved_artifact(tmp_path, "notes-api/nuget.config", NUGET)

    assert not (tmp_path / "notes-api" / "nuget.config").exists()
    assert ".agent-home" in str(refused.value) and not BANNED.search(str(refused.value))


def test_a_product_that_still_names_it_has_a_blocking_gap_at_release(tmp_path):
    (tmp_path / ".project-directory").write_text("notes-api\n")
    (tmp_path / "notes-api").mkdir()
    (tmp_path / "notes-api" / "nuget.config").write_text(NUGET)
    (tmp_path / "notes-api" / ".agent-home" / ".nuget").mkdir(parents=True)
    (tmp_path / "notes-api" / ".agent-home" / ".nuget" / "x.json").write_text('".agent-home"')

    gaps = delivery._the_harness_s_own_folders_named(tmp_path)

    assert gaps and "notes-api/nuget.config" in gaps[0] and ".agent-home/.nuget" not in gaps[0]
    assert is_blocking(gaps[0])


def test_a_product_that_does_not_name_it_has_no_gap(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('hello')\n")

    assert delivery._the_harness_s_own_folders_named(tmp_path) == []
