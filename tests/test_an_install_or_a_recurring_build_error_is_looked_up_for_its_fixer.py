"""A fixer of an install that failed, or of a build error the round before had too, is shown what others found for it
(plan WL.4, triggers T2 and T3, behind `WEB_LOOKUP_WHEN_STUCK`).

Owner, 2026-11-20: agents look things up when they struggle with setup or bugs. Measured the same night: the Rust, Java
and C# runs repeated one compiler error round after round (E0502, CS1503), and an install error the registry note did
not explain reached the fixer with nothing but the installer's words. The harness looks such an error up once per run,
sends only the cleaned error line, and records each lookup in the defect ledger.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

import the_fix_stage

from app.graph import stuck_lookup
from app.tools import lookups

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

COMPILE_ERROR = ("The product does not build: src/Notes/NoteStore.cs(41,17): error CS1503: Argument 1: cannot convert "
                 "from 'string' to 'int' [/workspace/run-notes/notes-api/notes-api.csproj]")
INSTALL_NOTE = ("`npm install` failed after the project's manifest changed; it said:\n"
                "npm error code ERESOLVE\n"
                "npm error ERESOLVE could not resolve: peer react@\"^17.0.0\" from react-widgets@4.2.0 at "
                "/workspace/run-notes/notes-web/node_modules\n; it ended:\nnpm error A complete log is in "
                "/home/agent/.npm/_logs/debug-0.log")
NO_SUCH_VERSION_NOTE = ("`npm install` failed after the project's manifest changed. The registry's current release of "
                        "`async-mutex` is 0.5.0: pin that; it said:\nnpm error notarget No matching version found for "
                        "async-mutex@^2.3.0.\n")


@pytest.fixture
def outside(monkeypatch, tmp_path):
    """Every request a lookup sends out: Stack Exchange answers one accepted question, every other source nothing."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("STACKEXCHANGE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    stuck_lookup._DONE.clear()  # noqa: SLF001
    sent: list[str] = []

    def fetch(url, headers):
        sent.append(url)
        if "/search/advanced" in url:
            return 200, json.dumps({"items": [{"accepted_answer_id": 7, "title": "Cannot convert string to int",
                                               "link": "https://stackoverflow.com/q/7", "last_activity_date": 0}]})
        if "/answers/" in url:
            return 200, json.dumps({"items": [{"answer_id": 7, "body": "<p>Parse the route value first.</p>"}]})
        return 200, '{"items": []}'

    monkeypatch.setattr(lookups, "_get", fetch)
    yield sent
    stuck_lookup._DONE.clear()  # noqa: SLF001


@pytest.fixture
def ledger(monkeypatch):
    recorded: list[dict] = []
    monkeypatch.setattr("app.observability.transcript.record", lambda *a, **k: recorded.append(k))
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "run-x")
    return recorded


def _the_request_in_round(root, round_, defect):
    _, seen = the_fix_stage.run(root, the_fix_stage.a_state(root, defect, test_round=round_))
    return seen.requests[-1]


def _a_compile_defect():
    return the_fix_stage.a_defect("The product does not build", actual_behavior=COMPILE_ERROR)


def test_a_build_error_the_round_before_had_too_is_looked_up_for_the_next_fixer(tmp_path, monkeypatch, outside,
                                                                                ledger):
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")

    first = _the_request_in_round(tmp_path, 1, _a_compile_defect())
    asked_after_the_first = list(outside)
    second = _the_request_in_round(tmp_path, 2, _a_compile_defect())

    assert asked_after_the_first == [] and "What others found" not in first, "new this round: nothing looked up"
    assert "What others found for this error" in second and "Parse the route value first." in second
    assert not BANNED.search(second[len(the_fix_stage.BASE_REQUEST):])
    [query] = {re.search(r"[?&]q=([^&]+)", url).group(1) for url in outside if "/search/advanced" in url}
    assert "CS1503" in query
    lookup = [entry for entry in ledger if entry.get("event") == "lookup"]
    assert len(lookup) == 1 and "T3" in lookup[0]["detail"]


def test_what_leaves_for_a_recurring_build_error_is_the_cleaned_error_alone(tmp_path, monkeypatch, outside):
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    root = tmp_path / "run-notes"
    root.mkdir()

    _the_request_in_round(root, 1, _a_compile_defect())
    _the_request_in_round(root, 2, _a_compile_defect())

    sent = " ".join(outside)
    assert "CS1503" in sent
    for private in ("run-notes", "workspace", "notes-api.csproj", "NoteStore"):
        assert private not in sent


def test_an_install_error_the_registry_does_not_explain_is_looked_up_at_its_first_fix(tmp_path, monkeypatch, outside,
                                                                                      ledger):
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    defect = the_fix_stage.a_defect("The project's dependencies do not install", actual_behavior=INSTALL_NOTE)

    request = _the_request_in_round(tmp_path, 1, defect)

    assert "What others found for this error" in request
    sent = " ".join(outside)
    assert "ERESOLVE" in sent and "workspace" not in sent and ".npm" not in sent
    assert [entry["detail"].split(":")[0] for entry in ledger if entry.get("event") == "lookup"] == ["T2 install"]


def test_a_version_that_does_not_exist_is_left_to_the_registry_s_answer(tmp_path, monkeypatch, outside):
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    defect = the_fix_stage.a_defect("The project's dependencies do not install", actual_behavior=NO_SUCH_VERSION_NOTE)

    request = _the_request_in_round(tmp_path, 1, defect)

    assert outside == [] and "What others found" not in request


def test_with_lookups_off_neither_an_install_nor_a_recurring_build_error_sends_a_request(tmp_path, monkeypatch,
                                                                                        outside):
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "off")
    install = the_fix_stage.a_defect("The project's dependencies do not install", actual_behavior=INSTALL_NOTE)

    requests = [_the_request_in_round(tmp_path, 1, _a_compile_defect()),
                _the_request_in_round(tmp_path, 2, _a_compile_defect()),
                _the_request_in_round(tmp_path, 3, install)]

    assert outside == [] and not any("What others found" in request for request in requests)


def test_a_setup_sent_back_is_looked_up_once_and_not_when_off(tmp_path, monkeypatch, outside):
    problem = ("the install failed: `cargo build` exited 101: error: failed to run custom build command for "
               "`openssl-sys v0.9.103` at /workspace/run-notes/target")
    stack = SimpleNamespace(language="Rust", framework="Axum")

    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "off")
    off = stuck_lookup.for_a_failed_setup(tmp_path, problem, stack)
    asked_when_off = list(outside)
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    shown = stuck_lookup.for_a_failed_setup(tmp_path, problem, stack)
    again = stuck_lookup.for_a_failed_setup(tmp_path, problem, stack)

    assert off == "" and asked_when_off == []
    assert "What others found for this error" in shown and again == shown
    assert len([url for url in outside if "/search/advanced" in url]) == 1, "once per error per run"
    assert "openssl-sys" in " ".join(outside) and "workspace" not in " ".join(outside)


@pytest.mark.parametrize("line, signature", [
    ("src/main.rs:12:5: error[E0502]: cannot borrow `notes` as mutable", "E0502"),
    ("src/app.ts(3,7): error TS2345: Argument of type 'string' is not assignable", "TS2345"),
    ("Main.java:12: error: incompatible types: String cannot be converted to int",
     "error: incompatible types: string cannot be converted to int"),
])
def test_a_build_error_is_known_again_by_its_code_or_its_message(line, signature):
    assert [found for found, _ in stuck_lookup.build_errors_in(f"The build failed:\n{line}")] == [signature]
