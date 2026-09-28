"""An edit whose `find` went stale says so, instead of diffing the lines.

Measured on one run, `specialist_ui_ux_0`: the stage wrote package.json,
ran `npm install --save-dev jest-environment-jsdom`, then edited the file with
the text it had written. npm had reformatted the manifest and added a
dependency. The diff it got back was accurate to the character and never said
the one useful thing - read it again, it is not what you wrote - and the stage
abandoned the edit.
"""

import pytest

from app.tools.repository import (
    RepositoryToolError,
    edit_approved_artifact,
    read_text_file,
    write_approved_artifact,
)

MANIFEST = '{\n  "name": "todo",\n  "main": "app.js",\n  "devDependencies": {\n    "jest": "^29.5.0"\n  }\n}\n'
AFTER_NPM = (
    '{\n  "name": "todo",\n  "main": "app.js",\n  "devDependencies": {\n'
    '    "jest": "^29.5.0",\n    "jest-environment-jsdom": "^30.5.1"\n  }\n}\n'
)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "package.json").write_text(MANIFEST, encoding="utf-8")
    return tmp_path


def _edit(root, find, replace):
    return edit_approved_artifact(root, "package.json", find, replace)


def test_a_command_that_rewrote_the_file_is_named_as_the_reason(project):
    read_text_file(project, "package.json")
    (project / "package.json").write_text(AFTER_NPM, encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        _edit(project, '    "jest": "^29.5.0"\n', '    "jest": "^30.0.0"\n')

    message = str(caught.value)
    assert "changed after you last read it" in message
    assert "Read the file again" in message


def test_it_fires_for_a_file_the_stage_wrote_rather_than_read(project):
    """The measured case began with a write, not a read."""
    write_approved_artifact(project, "package.json", MANIFEST)
    (project / "package.json").write_text(AFTER_NPM, encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        _edit(project, '    "jest": "^29.5.0"\n', '    "jest": "^30.0.0"\n')

    assert "changed after you last read it" in str(caught.value)


def test_a_file_nobody_touched_still_gets_the_diff(project):
    """No false positive: an edit that is simply wrong keeps its old message."""
    read_text_file(project, "package.json")

    with pytest.raises(RepositoryToolError) as caught:
        _edit(project, '    "jest": "^99.0.0"\n', '    "jest": "^30.0.0"\n')

    message = str(caught.value)
    assert "changed after you last read it" not in message
    assert "must match exactly" in message


def test_an_edit_the_stage_never_read_is_not_blamed_on_a_command(project):
    """Never read, never written: a different mistake, with its own message."""
    with pytest.raises(RepositoryToolError) as caught:
        _edit(project, '    "jest": "^99.0.0"\n', '    "jest": "^30.0.0"\n')

    assert "changed after you last read it" not in str(caught.value)


def test_a_successful_edit_refreshes_what_the_stage_has_seen(project):
    """Otherwise the edit's own change looks like a command rewriting the file."""
    read_text_file(project, "package.json")
    _edit(project, '"name": "todo"', '"name": "tasks"')

    with pytest.raises(RepositoryToolError) as caught:
        _edit(project, '    "jest": "^99.0.0"\n', '    "jest": "^30.0.0"\n')

    assert "changed after you last read it" not in str(caught.value)


def test_a_correct_edit_after_re_reading_succeeds(project):
    """The advice the message gives has to actually work."""
    read_text_file(project, "package.json")
    (project / "package.json").write_text(AFTER_NPM, encoding="utf-8")
    with pytest.raises(RepositoryToolError):
        _edit(project, '    "jest": "^29.5.0"\n', '    "jest": "^30.0.0"\n')

    read_text_file(project, "package.json")
    result = _edit(project, '"jest": "^29.5.0",', '"jest": "^30.0.0",')

    assert result["status"] == "edited"
    assert '"jest": "^30.0.0",' in (project / "package.json").read_text(encoding="utf-8")
