"""A send-back at the review's limit never costs the run a suite it could have locked, and is once per lock.

Found in a code review: the at-the-limit send-backs (held only in part, no product could pass, too weak) returned a
suite that might not run or might prove nothing; with no rounds left the run failed, although the suite that ran
before the send-back was lockable. The three "once" flags were also never cleared, so a reopened suite never got them.
"""
from __future__ import annotations

import inspect
from unittest import mock

from app.acceptance import suite
from app.graph import acceptance_nodes as nodes


def _suite(tmp_path):
    (tmp_path / ".harness").mkdir()
    folder = tmp_path / "acceptance"
    folder.mkdir()
    first = folder / "a.spec.js"
    first.write_text("test('a', ...)")
    return folder, first


def test_the_suite_before_the_send_back_is_put_back_whole(tmp_path):
    folder, first = _suite(tmp_path)
    with mock.patch.object(suite, "suite_files", side_effect=lambda root: sorted(folder.glob("*.spec.js"))):
        nodes._keep_before_the_send_back(tmp_path)
        first.write_text("broken(")
        (folder / "b.spec.js").write_text("added by the send-back")
        assert nodes._put_back_before_the_send_back(tmp_path) is True
        assert first.read_text() == "test('a', ...)" and not (folder / "b.spec.js").exists()
        assert nodes._put_back_before_the_send_back(tmp_path) is False


def test_the_once_flags_are_cleared_at_the_lock(tmp_path):
    _suite(tmp_path)
    saved = {}
    with mock.patch.object(suite, "_state", return_value={"lock": "x", "strengthened_once": True,
                                                           "cannot_pass_repaired_once": True}), \
            mock.patch.object(suite, "_save_state", side_effect=lambda root, state: saved.update(state=state)):
        nodes._the_send_backs_spent(tmp_path)
    assert saved["state"] == {"lock": "x"}


def test_the_review_puts_the_suite_back_before_it_fails_the_run():
    source = inspect.getsource(nodes.acceptance_review)
    for failure in ("The acceptance suite cannot run or load after", "The acceptance suite proves nothing after"):
        at = source.index(failure)
        assert "_put_back_before_the_send_back(root)" in source[at - 700:at]
    for flag in ("partial_strengthened_once", "cannot_pass_repaired_once", "strengthened_once"):
        at = source.index(f'"{flag}": True')
        assert "_keep_before_the_send_back(root)" in source[at - 300:at]
    lock = source.index("suite.lock(root)")
    assert "_the_send_backs_spent(root)" in source[lock:lock + 200]
