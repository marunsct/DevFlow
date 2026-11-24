"""The lookup replay set asks each case in the workspace its project had: the dependency gate's record, the stack
facts and the installed package's files (plan HK.4, LF.1309).

Measured before it: the replay asked every case in an empty workspace, so the stuck lookup's local-truth step (the
installed package's own files), its library and release line (the stack facts, the dependency gate) never fired; the
rebuilt lookup scored 1-2 of 23 public cases there, a number that said nothing about the steps a run's workspace feeds.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path, PurePosixPath

import pytest

from app.analysis.installed_packages import missing_in
from app.graph import stuck_lookup
from app.tools import lookups

ROOT = Path(__file__).resolve().parents[1]
REPLAY = json.loads((ROOT / "benchmarks" / "lookup-replay.json").read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in REPLAY["cases"]}


def _scorer():
    spec = importlib.util.spec_from_file_location("replay_lookups", ROOT / "scripts" / "loop" / "replay_lookups.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def the_web(monkeypatch, tmp_path):
    """The web's edge: each query asked is kept, and nothing is found."""
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    asked: list[str] = []

    def look_up(error, stack_words="", private_words=(), **_k):
        asked.append(error)
        return {"query": error, "asked": ["stack exchange"], "found": []}

    monkeypatch.setattr(lookups, "look_up", look_up)
    stuck_lookup._DONE.clear()  # noqa: SLF001
    return asked


@pytest.mark.parametrize("case_id", ["pool-options-under-the-driver-module", "rejection-type-under-its-own-module"])
def test_a_name_the_crate_has_elsewhere_is_answered_from_the_installed_crate_in_the_case_s_workspace(case_id, the_web):
    case = CASES[case_id]

    note = _scorer().through_the_fixer(case)

    assert _scorer().names_the_fix(case, note)
    assert the_web == [], "answered from the installed package, nothing asked of the web"


def test_a_name_the_crate_has_nowhere_is_answered_from_the_installed_crate_without_asking_the_web(the_web):
    note = _scorer().through_the_fixer(CASES["journal-mode-set-by-pragma"])

    assert "installed package" in note and "rusqlite" in note and "no public `JournalMode`" in note
    assert the_web == []


def test_a_declared_library_and_the_release_line_it_runs_are_searched(the_web):
    """The library the error names is one the project declares, at the release the stack facts say it runs."""
    _scorer().through_the_fixer(CASES["query-macros-need-a-database-at-compile-time"])

    assert [query for query in the_web if query.startswith("sqlx 0.8 ")]


def test_an_empty_workspace_is_still_asked_for_comparison(the_web):
    """The replay's old way, kept to compare against: the same case asks the web when its workspace is not laid out."""
    note = _scorer().through_the_fixer(CASES["pool-options-under-the-driver-module"], workspace=False)

    assert note == "" and the_web


@pytest.mark.parametrize("case", REPLAY["cases"], ids=lambda case: case["id"])
def test_each_case_s_workspace_stays_inside_it_and_holds_the_records_a_run_keeps(case):
    files = case["workspace"]

    assert files and all(not PurePosixPath(p).is_absolute() and ".." not in PurePosixPath(p).parts for p in files)
    facts = files[".harness/stack-facts.json"]
    declared = {(d["ecosystem"], d["package"]) for d in facts["dependencies"]}
    gate = files.get(".harness/dependency-gate.json", {})
    assert {tuple(key.split(":", 1)) for key in gate} <= declared
    assert all(verdict["verdict"] == "allowed" for verdict in gate.values())
    assert all(d.get("version") for d in facts["dependencies"])


@pytest.mark.parametrize("case", [c for c in REPLAY["cases"] if missing_in(c["error"])], ids=lambda case: case["id"])
def test_a_case_whose_error_says_a_package_lacks_a_name_holds_that_package_s_installed_files(case):
    package = missing_in(case["error"]).package

    assert [path for path in case["workspace"] if f"/{package}-" in path and path.endswith(".rs")]
