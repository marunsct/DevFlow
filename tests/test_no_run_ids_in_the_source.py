"""No run id is hardcoded anywhere in the application source.

A run id names one execution of one brief on one day. In a prompt it is noise
an agent cannot look up; in a comment or docstring it is a reference nobody can
follow once the run history is gone - and a rebuilt database removes it. The
evidence a change was made on belongs in its commit message, where it stays
next to the change it justified.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RUN_ID = re.compile(r"\brun[- ][0-9a-f]{8}\b")
SOURCE = Path(__file__).resolve().parent.parent / "src"


@pytest.mark.parametrize(
    "path",
    sorted(SOURCE.rglob("*.py")),
    ids=lambda p: str(p.relative_to(SOURCE)),
)
def test_the_file_names_no_run(path: Path) -> None:
    found = RUN_ID.findall(path.read_text(encoding="utf-8", errors="replace"))

    assert not found, f"{path.relative_to(SOURCE)} names {sorted(set(found))}"
