"""A suite-strength probe that is interrupted leaves nothing broken behind (plan item AL).

The probe breaks a file on purpose and puts it back. A worker that died in
between (a deploy, a crash) left the break in the workspace, and orphan
recovery re-entered the release on the broken tree. The probe now writes down
what it is changing, with a byte copy, before it changes it; the release puts
it back on entry. It also restores bytes, not text (a CRLF file stayed LF), and
no longer breaks lines inside docstrings and comments.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.acceptance import mutation, suite
from app.stacks import contract


def _project(tmp_path, monkeypatch, source: bytes):
    (tmp_path / ".harness").mkdir()
    (tmp_path / "svc" / "src").mkdir(parents=True)
    target = tmp_path / "svc" / "src" / "rules.py"
    target.write_bytes(source)
    pack = SimpleNamespace(kind="http_api", kept_files=())
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {"project": "svc"}))
    monkeypatch.setattr(suite, "is_locked", lambda root: True)
    return target


def _site(target, tmp_path):
    return mutation.sites([target], tmp_path / "svc")[0]


def test_a_probe_interrupted_midway_is_put_back_on_entry(tmp_path, monkeypatch):
    original = b"def adult(age):\n    return age >= 18\n"
    target = _project(tmp_path, monkeypatch, original)

    # The process dies right after the change: nothing restores it.
    mutation._journal_before_changing(tmp_path, tmp_path / "svc", _site(target, tmp_path))
    assert target.read_bytes() != original
    assert (tmp_path / mutation.JOURNAL).is_file()

    assert mutation.restore_an_interrupted_probe(tmp_path) is True

    assert target.read_bytes() == original
    assert not (tmp_path / mutation.JOURNAL).exists()
    assert not (tmp_path / mutation.BACKUP).exists()
    assert mutation.restore_an_interrupted_probe(tmp_path) is False


def test_the_release_puts_it_back_before_it_measures_anything():
    import inspect

    from app.graph import delivery

    source = inspect.getsource(delivery.release)
    assert source.index("restore_an_interrupted_probe(root)") < source.index("suite.run(root)")


def test_a_finished_probe_leaves_no_journal_and_the_same_bytes(tmp_path, monkeypatch):
    original = b"def adult(age):\r\n    return age >= 18\r\n\r\ndef pages(n):\r\n    return n + 1\r\n"
    target = _project(tmp_path, monkeypatch, original)

    mutation.what_the_suite_does_not_notice(
        tmp_path, run=lambda: SimpleNamespace(report=SimpleNamespace(tests=[SimpleNamespace(name="t", outcome="passed")])),
    )

    assert target.read_bytes() == original  # CRLF kept
    assert not (tmp_path / mutation.JOURNAL).exists()


def test_a_line_inside_a_docstring_or_comment_is_never_broken(tmp_path):
    source = (
        '"""Rules.\n\nAn adult is age >= 18 and True.\n"""\n'
        "def adult(age):\n"
        "    return age >= 18  # was > 17\n"
    )
    path = tmp_path / "rules.py"
    path.write_text(source)

    found = mutation.sites([path], tmp_path)

    assert {site["line"] for site in found} == {6}
    assert all(site["original"] == ">=" for site in found)


def test_a_block_comment_is_skipped_in_a_c_like_file(tmp_path):
    path = tmp_path / "rules.js"
    path.write_text("/* a && b\n   still a comment: x === y */\nexport const ok = (a) => a === 1;\n")

    assert {site["line"] for site in mutation.sites([path], tmp_path)} == {3}
