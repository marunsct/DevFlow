"""QA is shown the acceptance smoke test that passed at setup, as the shape its tests copy.

One run's QA spent 149 minutes and 182 calls writing its suite from nothing,
a third of the calls malformed or refused.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from app.acceptance import requests
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _with(monkeypatch, pack, record):
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, record))


def test_a_pack_s_acceptance_smoke_test_is_shown(monkeypatch, tmp_path):
    pack = SimpleNamespace(smoke_files={"tests/smoke.test.ts": "unit", "acceptance/smoke.spec.ts": "test('[AC-0] boots', async () => {})"})
    _with(monkeypatch, pack, {})

    shown = requests._a_test_that_ran_here(tmp_path, "acceptance")

    assert "test('[AC-0] boots'" in shown and "unit" not in shown
    assert not BANNED.search(shown.replace("test('[AC-0] boots', async () => {})", ""))


def test_a_proven_setup_s_kept_example_is_shown(monkeypatch, tmp_path):
    _with(monkeypatch, SimpleNamespace(smoke_files={}), {"setup": {"acceptance_example": "it('[AC-0] starts', () => {})"}})

    assert "it('[AC-0] starts'" in requests._a_test_that_ran_here(tmp_path, "acceptance")


def test_no_example_leaves_the_request_as_it_was(monkeypatch, tmp_path):
    monkeypatch.setattr(contract, "the_pack", lambda root: None)

    assert requests._a_test_that_ran_here(tmp_path, "acceptance") == ""


def test_the_example_is_in_the_author_s_request():
    import inspect

    assert "_a_test_that_ran_here(repo_root, acceptance_dir)" in inspect.getsource(requests.build_author_request)
