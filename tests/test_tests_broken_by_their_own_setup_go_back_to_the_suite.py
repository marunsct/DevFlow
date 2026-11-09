"""Tests failing in a setup they share, calling a library with arguments it rejects, are the suite's to fix.

Measured on one run: 18 tests failed at setup with `Client.__init__() got an unexpected keyword argument 'app'`, a test
library's call the installed version no longer takes, and six fix stages went at the product for about 45 minutes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.acceptance import junit, suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SAID = ('failed on setup with "TypeError: Client.__init__() got an unexpected keyword argument \'app\'" '
        '@pytest.fixture def client(): """httpx TestClient talking to the app"""')


def _project(root: Path, product: str) -> Path:
    project = root / "bookmarks"
    (project / "acceptance").mkdir(parents=True)
    (project / "acceptance" / "run.json").write_text(json.dumps({"command": ["run"], "report": "r.xml"}))
    (project / "app.py").write_text(product)
    (root / ".project-directory").write_text("bookmarks\n")
    return project


def _ran(*tests):
    return suite.AcceptanceResult(ran=True, report=junit.Report(tests=list(tests), found=True))


def _failed(name, message=SAID):
    return junit.TestResult(name=name, outcome="failed", message=message)


def test_a_library_call_the_shared_setup_gets_wrong_is_named(tmp_path):
    _project(tmp_path, "from fastapi import FastAPI\\napp = FastAPI()\\n")
    [found] = suite.tests_broken_by_their_own_setup(tmp_path, _ran(_failed("test_a"), _failed("test_b"), _failed("test_c")))
    assert "3 tests fail in the setup they share" in found and "`Client`" in found
    assert not BANNED.search(found)


def test_a_call_to_the_product_s_own_code_is_the_product_s(tmp_path):
    _project(tmp_path, "class Client:\\n    def __init__(self):\\n        pass\\n")
    assert suite.tests_broken_by_their_own_setup(tmp_path, _ran(_failed("test_a"), _failed("test_b"))) == []


def test_one_test_alone_or_a_failure_after_setup_is_not_named(tmp_path):
    _project(tmp_path, "app = 1\\n")
    assert suite.tests_broken_by_their_own_setup(tmp_path, _ran(_failed("test_a"))) == []
    later = "TypeError: Client.__init__() got an unexpected keyword argument 'app'"
    assert suite.tests_broken_by_their_own_setup(tmp_path, _ran(_failed("a", later), _failed("b", later))) == []


def test_it_reopens_the_suite_like_any_test_that_cannot_pass(tmp_path, monkeypatch):
    from app.acceptance import spec_dry_run

    monkeypatch.setattr(spec_dry_run, "findings", lambda root: [])
    _project(tmp_path, "app = 1\\n")
    found = suite.tests_that_cannot_pass(tmp_path, _ran(_failed("test_a"), _failed("test_b")))
    assert any("fail in the setup they share" in f for f in found)
