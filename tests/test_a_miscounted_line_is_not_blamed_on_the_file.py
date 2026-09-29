""""The numbering has moved since you read it" blamed a change that never happened.

`replace_lines` refuses when the line it was told to expect is not at
`start_line`. The refusal said the numbering had moved since the caller read the
file. Often nothing moved: the caller miscounted.

Measured on one run's `specialist_backend_0`: it read `app.js`, sent
`let filterMode = 'all';` as line 151 when it was line 154, and was told the
numbering had moved. The file had not changed. The stage believed its copy was
stale, read the file twice more - both reads reported "has not changed since" -
and then rewrote all 295 lines with `write_artifact` instead of resending the
call at the position the refusal had already given it.

The refusal cannot tell the two cases apart from the file alone, so it names
both and says the position it reports is the file as it is now.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    RepositoryToolError,
    replace_approved_lines,
    write_approved_artifact,
)

BODY = "".join(f"line {n}\n" for n in range(1, 11))


@pytest.fixture
def untouched(tmp_path: Path) -> Path:
    write_approved_artifact(tmp_path, "app/a.txt", BODY)
    return tmp_path


def _refusal(root: Path) -> str:
    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(root, "app/a.txt", 4, 5, "changed\n", "line 7")
    return str(caught.value)


def test_it_does_not_claim_the_file_changed(untouched: Path):
    assert "numbering has moved since you read it" not in _refusal(untouched)


def test_it_names_a_miscount_as_a_cause(untouched: Path):
    assert "the line was counted wrong" in _refusal(untouched)


def test_it_still_names_a_change_as_a_cause(untouched: Path):
    """A file another edit lengthened is the other half, and still happens."""
    assert "the file changed after you read it" in _refusal(untouched)


def test_it_still_gives_the_position(untouched: Path):
    message = _refusal(untouched)

    assert "It is line 7 now, 3 lines further down" in message
    assert "start_line=7" in message


def test_nothing_was_written(untouched: Path):
    _refusal(untouched)

    assert (untouched / "app/a.txt").read_text(encoding="utf-8") == BODY
