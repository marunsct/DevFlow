"""A suite whose runner crashed in the setup's own file goes to the setup stage, not to the suite's writers (LF.1594).

Measured on one run: the acceptance suite's runner was a JUnit wrapper the setup stage wrote and the harness kept. It
crashed on the first failing test, the suite wrote no report, and the review sent the suite back to its writers five
times. Each round found the tests right, named the crash in the kept runner as a blocker ("the harness's file, which I
may not change"), and the run failed with "the acceptance suite cannot run or load".

Now, when the suite wrote no report and the error was raised inside a file the proven setup provides
(`runner_check.the_setup_s_runner_crashed`), the review hands the crash to the scaffold node: the setup stage is asked
to repair that file, with the traceback; the runner is checked against a failing and a raising test as a setup's proof
checks it; a runner that passes is kept again as the setup's, and the suite is reviewed again in the same round. No
suite round is spent on it. A runner still crashing after `MAX_REPAIRS` stops the run and says which file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.stacks import contract, runner_check

logger = logging.getLogger(__name__)

#: How many times the setup stage is asked to repair its runner in one run.
MAX_REPAIRS = 2
#: The scaffold result's key that holds a crash still to repair.
CRASHED = "runner_crashed"
#: Where a runner file waiting for its repair is held, in the proven setup's record, so it is not put back as kept.
RELEASED = "released_runner"
STAGE = "stack_setup_runner"


def pending(state: Any) -> bool:
    """Whether a crash of the setup's runner waits for its repair."""
    return bool((state.get("scaffold_result") or {}).get(CRASHED))


def send_for_repair(state: Any, root: str | Path, result: Any) -> dict[str, Any] | None:
    """The fields that send a suite run whose runner crashed in the setup's own file to its repair; None otherwise.

    A run already given `MAX_REPAIRS` repairs is stopped, naming the file: the suite's writers cannot change it.
    """
    if getattr(result, "ran", True):
        return None
    crash = runner_check.the_setup_s_runner_crashed(root, str(getattr(result, "output", "") or ""))
    if crash is None:
        return None
    previous = dict(state.get("scaffold_result") or {})
    done = int(previous.get("runner_repairs") or 0)
    if done >= MAX_REPAIRS:
        return _stopped(crash.file, crash.traceback, done)
    logger.warning("The acceptance suite's runner crashed in the setup's own %s (line %d); sent to the setup stage, "
                   "not to the suite's writers", crash.file, crash.line)
    return {"stage": "scaffold", "scaffold_result": {**previous, CRASHED: {
        **crash.as_dict(), "command": str(getattr(result, "command", "") or ""), "problem": ""}}}


def _stopped(file: str, why: str, done: int) -> dict[str, Any]:
    return {"stage": "failed", "error": (
        f"The acceptance suite's runner `{file}`, which the project's test setup provides, still cannot report a "
        f"failing test after {done} repair(s) by the setup stage, so the suite never writes a report: {why[-1500:]}")}


def request(project: str, crash: dict[str, Any], report: str, command: str, files: list[str]) -> dict[str, Any]:
    """What the setup stage is asked: the file, the traceback, and what a runner must do with a failing test."""
    file = str(crash.get("file") or "")
    again = str(crash.get("problem") or "")
    text = (
        f"The project's test runner crashed. The acceptance suite ran through `{command}` and wrote no report, because "
        f"`{project}/{file}` - a file of the project's test setup - raised an error at line "
        f"{crash.get('line')}:\n\n{str(crash.get('traceback') or '')[-2500:]}\n\n"
        f"Change `{project}/{file}` so that every failing test and every test that raises an error is written into "
        f"its JUnit report at `{project}/{report}` as failed, and the run goes on to the next test instead of "
        "stopping. The suite's tests are not at fault: before the product is built most of them fail, which is "
        f"expected. Change only the setup's runner files ({', '.join(f'`{project}/{name}`' for name in files)}); "
        "leave the tests, the product and the declaration as they are. When you are done, run "
        f"`{command}` once: it must write the report although tests fail. The harness then runs the runner with one "
        "test that fails and one that raises, and its report must name both as failed."
        + (f"\n\nThe last change did not hold: {again}" if again else "")
    )
    return {"messages": [{"role": "user", "content": text}]}


def _record(root: str | Path) -> dict[str, Any] | None:
    record = contract.read(root)
    return record if record and isinstance(record.get("setup"), dict) else None


def _write(root: str | Path, record: dict[str, Any]) -> None:
    (Path(root) / contract.CONTRACT_FILE).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def release(root: str | Path, file: str) -> None:
    """Hold `file` out of the setup's kept files while it is repaired, so the stage may change it and nothing puts it back."""
    record = _record(root)
    if record is None:
        return
    kept = record["setup"].setdefault("kept", {})
    if file in kept:
        record["setup"].setdefault(RELEASED, {})[file] = kept.pop(file)
        _write(root, record)


def keep_again(root: str | Path, stack: Any = None) -> list[str]:
    """The repaired runner files kept as the setup's again, as they are now, and in the setup library's entry; the names."""
    record = _record(root)
    if record is None:
        return []
    project_root = Path(root) / str(record.get("project") or "")
    released = dict(record["setup"].pop(RELEASED, {}) or {})
    kept = record["setup"].setdefault("kept", {})
    for name in released:
        path = project_root / name
        kept[name] = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else released[name]
    _write(root, record)
    if stack is not None and released:
        from app.stacks import custom_setup

        entry = custom_setup.library_directory() / f"{custom_setup.library_key(stack)}.json"
        try:
            stored = json.loads(entry.read_text(encoding="utf-8"))
            for name in released:
                if name in (stored.get("files") or {}):
                    stored["files"][name] = kept[name]
            entry.write_text(json.dumps(stored), encoding="utf-8")
        except (OSError, ValueError, AttributeError, TypeError):
            logger.debug("No library entry to repair for this stack", exc_info=True)
    return list(released)


def check(root: str | Path, run: Any = None) -> runner_check.Checked:
    """Both of the setup's runners, run with a failing and a raising test, as a setup's proof runs them."""
    from app.stacks.scaffold import sandbox_runner

    record = _record(root) or {}
    setup = record.get("setup") or {}
    project = str(record.get("project") or "")
    run = run or sandbox_runner(root)
    checked = runner_check.Checked(ok=True)
    for label in ("acceptance", "unit"):
        argv = [str(part) for part in setup.get(f"{label}_test") or []]
        if not argv:
            continue
        checked = runner_check.reports_failures(
            Path(root) / project, argv, str(setup.get(f"{label}_report") or ""), str(setup.get(f"{label}_dir") or ""),
            str(setup.get(f"{label}_pattern") or ""), run, project, label)
        if not checked.ok:
            return checked
    return checked


def repair(state: Any, config: RunnableConfig, ctx: Any, run: Any = None) -> dict[str, Any]:
    """Ask the setup stage to repair the runner file that crashed, check it, and review the suite again."""
    from app.acceptance import suite
    from app.agents.specialists import create_specialist_agent
    from app.graph.acceptance_nodes import _root, _stack
    from app.graph.workflow import _handing_on, _run_gated_agent, _the_stage_that_paused
    from app.stacks import custom_setup

    root = _root(state)
    previous = dict(state.get("scaffold_result") or {})
    crash = dict(previous.get(CRASHED) or {})
    attempt = int(previous.get("runner_repairs") or 0)
    record = _record(root)
    if record is None:
        return _handing_on(**_stopped(str(crash.get("file") or "the runner"), "no proven setup is recorded", attempt))
    project = str(record.get("project") or "")
    setup = record["setup"]
    file = str(crash.get("file") or "")
    resuming = str(_the_stage_that_paused(state) or "").startswith(STAGE)
    the_suite = {} if resuming else {path: path.read_text(encoding="utf-8") for path in suite.suite_files(root)
                                     if path.is_file()}
    release(root, file)
    custom_setup.record_the_setup_s_scope(Path(root), project, {file: ""})
    agent = create_specialist_agent(
        "testing", model=ctx.model, checkpointer=ctx.checkpointer, repo_root=ctx.repo_root,
        allow_subdirectories=ctx.allow_subdirectories, setting_up_the_stack=True,
    )
    update = _run_gated_agent(
        state, config, stage_name=f"{STAGE}_{attempt}", agent=agent,
        initial_request=request(project, crash, str(setup.get("acceptance_report") or ""),
                                str(crash.get("command") or " ".join(setup.get("acceptance_test") or [])), [file]),
        output_key="__runner_repair__", next_stage="acceptance_review",
    )
    if "__runner_repair__" not in update:
        if update.get("stage") == "failed":
            return _handing_on(**_stopped(file, str(update.get("error") or "the setup stage did not finish"),
                                          attempt + 1))
        return update  # paused for approval, or retrying
    update.pop("__runner_repair__")
    update.pop("stage", None)
    custom_setup.record_the_setup_s_scope(Path(root), project, None)
    # The suite is its writers': whatever the stage changed in it goes back as it was.
    for path, text in the_suite.items():
        if not path.is_file() or path.read_text(encoding="utf-8", errors="replace") != text:
            path.write_text(text, encoding="utf-8")
    checked = check(root, run)
    done = attempt + 1
    if checked.ok:
        names = keep_again(root, _stack(state))
        logger.info("The setup's runner %s reports failing tests now; the suite is reviewed again", ", ".join(names))
        rest = {key: value for key, value in previous.items() if key != CRASHED}
        return _handing_on(**update, stage="acceptance_review", scaffold_result={**rest, "runner_repairs": done})
    if done >= MAX_REPAIRS:
        stack = _stack(state)
        set_aside = custom_setup.library_directory() / f"{custom_setup.library_key(stack)}.json" if stack else None
        if set_aside is not None and set_aside.is_file():
            (set_aside.parent / "failed").mkdir(parents=True, exist_ok=True)
            set_aside.replace(set_aside.parent / "failed" / set_aside.name)
        return _handing_on(**update, **_stopped(file, checked.problem, done))
    logger.warning("The setup's runner %s still cannot report a failing test; asked again: %s", file, checked.problem)
    return _handing_on(**update, stage="scaffold", scaffold_result={
        **previous, "runner_repairs": done, CRASHED: {**crash, "problem": checked.problem}})


__all__ = ["CRASHED", "MAX_REPAIRS", "check", "keep_again", "pending", "release", "repair", "request", "send_for_repair"]
