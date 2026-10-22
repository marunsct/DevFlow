"""The release's re-read of the files does not judge the locked suite's own files (plan item AO.5).

The suite ran moments earlier and its result stands; a static reading of its
files can only second-guess it. A problem that names the locked directory is
left out, and the rest are kept as completion gaps.
"""
from __future__ import annotations

from app.acceptance import suite
from app.graph import delivery


def test_a_problem_about_the_locked_suite_is_left_out_and_the_rest_kept(tmp_path, monkeypatch):
    import app.analysis.integration_checks as checks

    monkeypatch.setattr(suite, "is_locked", lambda root: True)
    monkeypatch.setattr(suite, "relative_directory", lambda root: "notes/acceptance")
    monkeypatch.setattr(checks, "problems_that_break_the_product", lambda *a, **k: [
        "notes/acceptance/api.spec.js calls /v2/notes, which nothing serves",
        "notes/src/store.js imports ./missing, which does not exist",
    ])

    gaps = delivery._what_the_release_re_check_finds({}, str(tmp_path))

    assert gaps == ["At release, reading the files still finds: notes/src/store.js imports ./missing, which does not exist"]


def test_with_no_locked_suite_nothing_is_left_out(tmp_path, monkeypatch):
    import app.analysis.integration_checks as checks

    monkeypatch.setattr(suite, "is_locked", lambda root: False)
    monkeypatch.setattr(checks, "problems_that_break_the_product", lambda *a, **k: ["notes/acceptance/x.js broken"])

    assert len(delivery._what_the_release_re_check_finds({}, str(tmp_path))) == 1
