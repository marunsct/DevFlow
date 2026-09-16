"""A `find` this stage already replaced is answered with what replaced it.

Measured on run f81808a4, `specialist_testing_3`. It sent one `find` six
times - `t.equal(initial.length, 0, 'initial list is empty')` - varying the
`replace` each time as it worked out the node:test assertion API. The edit
succeeded once; the other five were answered with a character diff comparing
its `find` against the replacement it had written itself.

`_already_applied` does not catch this: it wants the whole edit re-sent, same
`find` and same `replace`. Here only the `find` repeats.
"""

import pytest

from app.tools.repository import (
    RepositoryToolError,
    edit_approved_artifact,
    read_text_file,
)

LINE = "t.equal(initial.length, 0, 'initial list is empty');\n"


@pytest.fixture
def project(tmp_path):
    (tmp_path / "a.test.js").write_text(f"import t from 'node:test';\n{LINE}", encoding="utf-8")
    return tmp_path


def _edit(root, find, replace):
    return edit_approved_artifact(root, "a.test.js", find, replace)


def test_the_measured_case(project):
    read_text_file(project, "a.test.js")
    _edit(project, LINE.rstrip("\n"), "assert.strictEqual(initial.length, 0);")

    with pytest.raises(RepositoryToolError) as caught:
        _edit(project, LINE.rstrip("\n"), "t.assert.strictEqual(initial.length, 0);")

    message = str(caught.value)
    assert "already replaced it earlier in this stage" in message
    assert "assert.strictEqual(initial.length, 0);" in message
    assert "These lines differ" not in message


def test_it_says_what_to_send_instead(project):
    read_text_file(project, "a.test.js")
    _edit(project, LINE.rstrip("\n"), "assert.ok(true);")

    with pytest.raises(RepositoryToolError) as caught:
        _edit(project, LINE.rstrip("\n"), "assert.ok(false);")

    assert "send the text above as `find`" in str(caught.value)


def test_a_passage_this_stage_never_replaced_keeps_the_diff(project):
    read_text_file(project, "a.test.js")

    with pytest.raises(RepositoryToolError) as caught:
        _edit(project, "t.equal(initial.length, 1, 'wrong');", "x")

    assert "already replaced it earlier in this stage" not in str(caught.value)


def test_re_sending_the_whole_edit_keeps_its_own_message(project):
    """`_already_applied` is the better answer when `replace` is there too.

    It needs a replacement long enough to prove its presence is not a
    coincidence - `_REPLACE_LONG_ENOUGH_TO_RECOGNISE`, 24 characters - so the
    replacement here is a realistic full line rather than a short call.
    """
    long_enough = "assert.strictEqual(initial.length, 0, 'the list starts empty');"
    read_text_file(project, "a.test.js")
    _edit(project, LINE.rstrip("\n"), long_enough)

    with pytest.raises(RepositoryToolError) as caught:
        _edit(project, LINE.rstrip("\n"), long_enough)

    assert "already been applied" in str(caught.value)


def test_a_short_replacement_falls_to_the_replacement_record(project):
    """`_already_applied` cannot vouch for a short `replace`; this check can.

    It knows the stage made the edit rather than inferring it from the file,
    so it answers where the older check has to stay silent.
    """
    read_text_file(project, "a.test.js")
    _edit(project, LINE.rstrip("\n"), "assert.ok(1);")

    with pytest.raises(RepositoryToolError) as caught:
        _edit(project, LINE.rstrip("\n"), "assert.ok(1);")

    assert "already replaced it earlier in this stage" in str(caught.value)


def test_the_second_edit_to_the_same_place_works_as_described(project):
    """The advice has to actually work: send the replacement back as `find`."""
    read_text_file(project, "a.test.js")
    _edit(project, LINE.rstrip("\n"), "assert.ok(true);")

    result = _edit(project, "assert.ok(true);", "assert.ok(false);")

    assert result["status"] == "edited"
    assert "assert.ok(false);" in (project / "a.test.js").read_text(encoding="utf-8")


def test_another_stage_does_not_inherit_the_record(project):
    from app.tools import seen_content

    read_text_file(project, "a.test.js")
    _edit(project, LINE.rstrip("\n"), "assert.ok(true);")
    seen_content.forget_everything()

    with pytest.raises(RepositoryToolError) as caught:
        _edit(project, LINE.rstrip("\n"), "assert.ok(false);")

    assert "already replaced it earlier in this stage" not in str(caught.value)
