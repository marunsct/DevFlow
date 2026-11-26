"""A run of a browser suite that cannot finish within a command's limit is held to a short limit per test, or refused
for a narrower one (LF.1589).

Measured on a page product, in the stage that writes its acceptance suite: `npm run test:e2e`, then
`npx playwright test`, then `npx playwright test --reporter=line --workers=4` - one whole-suite run under three
spellings - each ran out of the 300-second limit: a quarter of an hour and three calls. Nothing was built yet, so every
test waited its full limit for elements that did not exist. Each spelling differed from the last, so the refusal of an
exact repeat never fired, and the timeout's own advice named `--reporter=line` as a smaller part. The commands, the
project's scripts and the spec are captured in `tests/captured/suite_run_out_of_its_limit.json`.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.acceptance.suite import STATE_FILE
from app.observability.transcript import asked_for
from app.stacks import test_runners
from app.tools.sandbox import SandboxExecutor, _ledger_path

CAPTURED = json.loads(
    (Path(__file__).parent / "captured" / "suite_run_out_of_its_limit.json").read_text(encoding="utf-8"))
PROJECT = "list-app"
WRITER = "acceptance_author_0"
WHOLE = CAPTURED["whole_suite_runs"]
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def a_workspace(root: Path, *, locked: bool = False) -> Path:
    """The captured project: its scripts, its browser runner and the head of its one spec file."""
    project = root / PROJECT
    (project / "e2e").mkdir(parents=True)
    (project / "package.json").write_text(json.dumps({
        "name": PROJECT, "type": "module", "scripts": CAPTURED["package_json_scripts"],
        "devDependencies": CAPTURED["dev_dependencies"],
    }), encoding="utf-8")
    (project / "e2e" / "app.spec.js").write_text(CAPTURED["spec_head"], encoding="utf-8")
    state = {"project": PROJECT, "acceptance_dir": CAPTURED["acceptance_dir"]}
    if locked:
        state.update(lock={}, lock_version=1)
    (root / STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    (root / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
    return project


def timed_out(root: Path, command: list[str], *, stage: str = WRITER) -> None:
    """The ledger's record of a run that used the whole 300 seconds, as the sandbox writes it."""
    path = _ledger_path(str(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": datetime.now(timezone.utc).isoformat(), "role": "testing_specialist", "stage": stage,
        "command": command, "working_directory": PROJECT, "category": "test", "returncode": None,
        "error": CAPTURED["timeout_error"], "by": "agent", "duration_seconds": 300.4,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


@pytest.fixture
def ran(monkeypatch):
    """The commands that reached the container, in order; each fails as an unbuilt product's suite does."""
    commands: list[list[str]] = []

    def _run(cls, command, *args, **kwargs):
        commands.append([str(part) for part in command])
        return {"returncode": "1", "stdout": "1 failed", "stderr": ""}

    monkeypatch.setattr(SandboxExecutor, "_run", classmethod(_run))
    return commands


def run(root: Path, command: list[str], stage: str = WRITER) -> dict:
    with asked_for(stage):
        return SandboxExecutor.execute(command, str(root), "testing_specialist", "test", working_directory=PROJECT)


# --- which tests a command runs ------------------------------------------------------------------------------------


@pytest.mark.parametrize("command", WHOLE, ids=[" ".join(c) for c in WHOLE])
def test_each_captured_spelling_of_the_whole_suite_chooses_no_tests(tmp_path, command):
    project = a_workspace(tmp_path)

    call = test_runners.read(command, project)

    assert call is not None and call.runner.name == "playwright"
    assert test_runners.selection(call) == frozenset()


@pytest.mark.parametrize("command", CAPTURED["narrow_runs"], ids=[" ".join(c) for c in CAPTURED["narrow_runs"]])
def test_a_captured_run_by_criterion_id_chooses_its_tests(tmp_path, command):
    project = a_workspace(tmp_path)

    call = test_runners.read(command, project)

    assert test_runners.selection(call) == frozenset({f"--grep={command[-1]}"})


def test_a_command_of_no_runner_in_the_table_is_not_read(tmp_path):
    project = a_workspace(tmp_path)

    assert test_runners.read(["npm", "test"], project) is None


# --- (a) the suite's writer, before anything is built -------------------------------------------------------------


def test_the_writer_s_whole_suite_run_holds_each_test_to_a_short_limit(tmp_path, ran):
    a_workspace(tmp_path)

    outcome = run(tmp_path, ["npm", "run", "test:e2e"])

    assert ran == [["npm", "run", "test:e2e", "--", "--timeout=5000"]]
    assert "5 seconds" in outcome["note"] and "nothing the suite checks is built yet" in outcome["note"]
    assert not BANNED.search(outcome["note"])


def test_a_launched_run_takes_the_limit_without_a_separator(tmp_path, ran):
    a_workspace(tmp_path)

    run(tmp_path, ["npx", "playwright", "test", "--reporter=line", "--workers=4"])

    assert ran == [["npx", "playwright", "test", "--reporter=line", "--workers=4", "--timeout=5000"]]


@pytest.mark.parametrize("stage, locked", [(WRITER, True), ("test_round_0", False)],
                         ids=["once the suite was locked", "in another stage"])
def test_the_run_is_left_as_it_is_where_the_product_may_be_built(tmp_path, ran, stage, locked):
    a_workspace(tmp_path, locked=locked)

    run(tmp_path, ["npm", "run", "test:e2e"], stage=stage)

    assert ran == [["npm", "run", "test:e2e"]]


# --- (b) the same tests again in the stage they ran out of the limit in -------------------------------------------


@pytest.mark.parametrize("again", WHOLE[1:], ids=[" ".join(c) for c in WHOLE[1:]])
def test_another_spelling_of_a_timed_out_run_is_refused_with_a_narrower_one(tmp_path, ran, again):
    a_workspace(tmp_path, locked=True)
    timed_out(tmp_path, WHOLE[0])

    outcome = run(tmp_path, again)

    assert ran == []
    assert "npm run test:e2e" in outcome["error"] and "300-second limit" in outcome["error"]
    assert f"{' '.join(again)} --grep AC-6" in outcome["error"]
    assert f"{' '.join(again)} e2e/app.spec.js" in outcome["error"]
    assert not BANNED.search(outcome["error"])


def test_the_refusal_says_what_the_added_words_do_not_change(tmp_path, ran):
    a_workspace(tmp_path, locked=True)
    timed_out(tmp_path, WHOLE[1])

    outcome = run(tmp_path, WHOLE[2])

    assert "`--reporter=line --workers=4`" in outcome["error"]
    assert "does not choose which tests run" in outcome["error"]


@pytest.mark.parametrize("again, stage", [(CAPTURED["narrow_runs"][1], WRITER), (WHOLE[1], "test_round_0")],
                         ids=["a narrower run", "another stage"])
def test_a_narrower_run_or_another_stage_s_run_goes_ahead(tmp_path, ran, again, stage):
    a_workspace(tmp_path, locked=True)
    timed_out(tmp_path, WHOLE[0])

    run(tmp_path, again, stage=stage)

    assert ran == [again]


def test_a_change_to_the_product_since_lets_the_whole_run_be_tried_again(tmp_path, ran):
    project = a_workspace(tmp_path, locked=True)
    timed_out(tmp_path, WHOLE[0])
    page = project / "index.html"
    page.write_text("<!doctype html>\n", encoding="utf-8")
    later = time.time() + 5
    os.utime(page, (later, later))

    run(tmp_path, WHOLE[1])

    assert ran == [WHOLE[1]]


def test_a_change_to_the_suite_alone_does_not(tmp_path, ran):
    project = a_workspace(tmp_path, locked=True)
    timed_out(tmp_path, WHOLE[0])
    spec = project / "e2e" / "app.spec.js"
    later = time.time() + 5
    os.utime(spec, (later, later))

    run(tmp_path, WHOLE[1])

    assert ran == []


def test_a_run_stopped_at_a_shorter_retry_limit_does_not_count(tmp_path, ran):
    a_workspace(tmp_path, locked=True)
    path = _ledger_path(str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(), "stage": WRITER, "command": WHOLE[0],
        "working_directory": PROJECT, "category": "test", "error": CAPTURED["timeout_error"].replace("300", "60"),
        "by": "agent", "duration_seconds": 60.2,
    }) + "\n", encoding="utf-8")

    run(tmp_path, WHOLE[1])

    assert ran == [WHOLE[1]]


# --- the timeout's own advice ---------------------------------------------------------------------------------------


def test_the_timeout_advice_does_not_offer_a_reporter_as_a_smaller_part(tmp_path, ran):
    """The third captured run took `--reporter=line` from the advice as a smaller part, and ran every test again."""
    a_workspace(tmp_path, locked=True)
    timed_out(tmp_path, ["npx", "playwright", "test", "e2e/app.spec.js"], stage="test_round_0")

    outcome = run(tmp_path, ["npx", "playwright", "test", "e2e/app.spec.js"], stage="test_round_0")

    assert "browser runner installed" in outcome["error"]
    assert "--reporter=line" not in outcome["error"]
    assert "--grep AC-1" in outcome["error"]
    assert not BANNED.search(outcome["error"])
