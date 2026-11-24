"""How a fix is judged past its pass count: repaired forward before it is reverted, and progress read from where its
tests fail (LF.1271, LF.1272; deep review of the medium brief, items 2.3 and 2.4).

Measured on one medium run: 34 fix stages, 5 reverted, 2 of them correct fixes. Each correct fix moved the failure to
the next fault behind it - the fixed route then reached a list query that raised ("18 passing to 0"), or the start
broke on an import the fix had added - and the revert threw the correct part away with the fault. Fixes that moved
their tests from 500 to 404, a later step reached, counted as nothing: only the pass count was read.

Two rules:

- **Repaired forward** (`ForwardRepair`, `what_a_repair_is_given`). A fix that stopped the product starting, or its
  unit tests building, where they did before it - or whose broken tests, which passed before it, all stop at one new
  step - is handed back once before it is reverted: that failure, the end of the server's log and its own diff, to the
  fix's own model, which may rewrite only the files the fix changed, within the rewrite's own bounds
  (`rewritten_fixes.MOST_FILES` files, `MOST_PASSES` passes). It is then measured again and judged as any fix is:
  reverted if anything that passed before it still fails. One repair a fix stage; a regression is never kept unrepaired.
- **Moved forward** (`progress`, `moved_forward`). A fix that broke nothing and left its own tests failing is read for
  where they fail now against where they failed before it. One of them passing, failing at a later line of the test,
  or with an answer nearer the one wanted (a thrown error, then a server error, then a refusal, then an assertion on
  what came back) - and none further back - moved forward: the defect stays open with that evidence and the fix is not
  counted as a failed one. Where no failure can be read (no steps, no answers), the fix is judged as before.

Nothing here raises.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from app.acceptance.first_failing_step import Failure, read, where_it_threw, where_the_test_was

logger = logging.getLogger(__name__)

#: Where each fix stage's failing tests are kept as the stage found them, by stage name.
PROFILES_FILE = ".harness/fix-profiles.json"
#: Fix stages kept in that file, the newest last.
MOST_PROFILES = 24
#: Characters of one test's failure kept: its frames are what is read, and the runner keeps the end of a long one.
MOST_MESSAGE = 4000

#: How an attempt that moved its tests forward is recorded, and how its ledger detail begins.
MOVED_FORWARD = "moved forward"
#: The ledger event of a forward repair, whichever way it went.
REPAIRED_FORWARD = "repaired forward"
#: How the ledger detail and the attempt of a fix kept after its repair begin.
REPAIR_HELD = "repaired forward and kept, measured again"
#: How the ledger detail and the attempt of a fix reverted after its repair begin.
REVERTED_AFTER_A_REPAIR = "reverted after a forward repair failed"
#: What of the server's log, the unit run's output and the fix's diff a repair is shown.
LOG_TAIL = 2000
MOST_DIFF = 6000
MOST_FAILURE = 1500

#: An error a test or its helper threw that is an error, not a line of its frames or its source.
_A_RAISED_ERROR = re.compile(r"\b\w*(?:Error|Exception)\b|\bECONN\w+|\brefused\b|\btimed?\s?out\b|\bdid not start\b",
                             re.I)

#: How a repair's request opens, and what it asks for. Read by the fix's own model.
REPAIR_HEADING = "Your change for this defect was measured, and it broke what worked before it."
REPAIR_EXPECTED = (
    "What worked before your change works again, and your change still does what this defect asks. Repair your "
    "change where it broke the product; do not undo the part of it that fixes the defect."
)
REPAIR_STEPS = "The harness measured the product after your change, the way the acceptance suite runs it."
#: How the evidence a kept fix left begins in its defect's actual behaviour, so the next one replaces it.
MOVED_EVIDENCE = "After the last fix, which was kept, its tests moved forward:"


def _plain(value: Any) -> str:
    return str(value or "")


def _bare(key: str) -> str:
    """A snapshot key's own test name: what follows where the test lives."""
    from app.ci import WHERE

    return key.rsplit(WHERE, 1)[-1] if WHERE in key else key


def _its_criteria(defect: Any) -> list[str]:
    from app.acceptance.junit import tags_in

    return [t for t in tags_in(_plain(getattr(defect, "description", ""))) if t.startswith(("AC-", "CR-"))]


def _the_tests(result: dict, criteria: Sequence[str]) -> list[dict]:
    """The tests of `criteria` in a saved suite result, each once, as {name, outcome, message}."""
    found: dict[str, dict] = {}
    for kind in ("criteria", "change_requests"):
        held = result.get(kind) if isinstance(result.get(kind), dict) else {}
        for cid in criteria:
            for test in (held.get(cid) or {}).get("tests") or []:
                if isinstance(test, dict) and test.get("name"):
                    found.setdefault(str(test["name"]), {
                        "name": str(test["name"]), "outcome": _plain(test.get("outcome")),
                        "message": _plain(test.get("message"))[-MOST_MESSAGE:]})
    return list(found.values())


def _the_result_of_the_product_as_it_is(root: str | Path) -> dict | None:
    """The suite's last saved result when it measured the product as it is on disk now; None otherwise."""
    try:
        from app.acceptance import suite
        from app.acceptance.unstable import fingerprint

        result = suite.last_result(root) or {}
        if not result or not result.get("fingerprint") or result.get("fingerprint") != fingerprint(root):
            return None
        return result
    except Exception:  # noqa: BLE001 - nothing to compare with
        return None


def _read_profiles(root: str | Path) -> dict:
    try:
        data = json.loads((Path(root) / PROFILES_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def remember_before(root: str | Path, stage_name: str, defect: Any) -> None:
    """Keep the defect's tests as the fix stage finds them, for `moved_forward`; nothing when the suite's last result
    is not of the product as it is (a fix reverted since it was measured). Never raises."""
    try:
        profiles = _read_profiles(root)
        profiles.pop(stage_name, None)
        criteria = _its_criteria(defect)
        result = _the_result_of_the_product_as_it_is(root) if criteria else None
        if result is not None:
            profiles[stage_name] = _the_tests(result, criteria)
        kept = dict(list(profiles.items())[-MOST_PROFILES:])
        path = Path(root) / PROFILES_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(kept), encoding="utf-8")
    except Exception:  # noqa: BLE001 - the fix is judged by its count, as before
        logger.debug("Could not keep the tests a fix starts from", exc_info=True)


def moved_forward(root: str | Path, stage_name: str, defect: Any) -> str | None:
    """How the fix of `stage_name` moved its defect's failing tests forward (`progress`), measured after it; "" when it
    did not, None when that cannot be read. Never raises."""
    try:
        before = _read_profiles(root).get(stage_name)
        criteria = _its_criteria(defect)
        if not before or not criteria:
            return None
        result = _the_result_of_the_product_as_it_is(root)
        if result is None:
            return None
        return progress(before, _the_tests(result, criteria))
    except Exception:  # noqa: BLE001 - judged by its count, as before
        return None


def _nearness(failure: Failure) -> int | None:
    """How near a failed test came to the answer it wanted: 0 a thrown error, 1 a server error, 2 a refusal, 3 an
    assertion on what came back; None when its failure cannot be read."""
    if not _plain(failure.test.get("message")).strip():
        return None
    if failure.answer[:3].isdigit():
        return 1 if failure.answer.startswith("5") else 2
    if failure.thrown:
        return 0 if _A_RAISED_ERROR.search(failure.thrown) else None
    return 3


def _line(where: str) -> tuple[str, int] | None:
    file, _, line = where.rpartition(":")
    return (file, int(line)) if file and line.isdigit() else None


def _compared(before: Failure, after: Failure) -> int | None:
    """1 when `after` failed further on than `before`, -1 further back, 0 at the same place; None when not readable."""
    was, now = _line(where_the_test_was(before.test.get("message"))), _line(where_the_test_was(after.test.get("message")))
    if was and now and was[0] == now[0] and was[1] != now[1]:
        return 1 if now[1] > was[1] else -1
    near_was, near_now = _nearness(before), _nearness(after)
    if near_was is None or near_now is None:
        return None
    return (near_now > near_was) - (near_now < near_was)


def _how(failure: Failure) -> str:
    """How a failed test was answered, in a few words: `answered 404`; "" when it cannot be read."""
    near = _nearness(failure)
    return (f"answered {failure.answer}" if failure.answer[:3].isdigit()
            else f"threw {failure.thrown[:80]}" if near == 0
            else "an assertion on what came back" if near == 3 else "")


def _where_it_failed(failure: Failure) -> str:
    """Where a failed test stopped and how, in a few words: `tasks.spec.ts:30, answered 404`."""
    where = where_the_test_was(failure.test.get("message"))
    return ", ".join(part for part in (where, _how(failure)) if part) or "an unread step"


def progress(before: Sequence[dict], after: Sequence[dict]) -> str | None:
    """How a fix moved one defect's tests, read from where each failed before it and after it.

    `before` and `after` are the defect's tests as {name, outcome, message}. Forward: a test that failed now passes,
    fails at a later line of the test, or with an answer nearer the one wanted. Back: a test that passed now fails,
    or one fails earlier or further from the answer. Returns what moved forward, in a line, when something did and
    nothing went back; "" when nothing moved forward or something went back; None when no failure before the fix can
    be compared with one after it (no steps known, no answers): then the count judges, as before.
    """
    now = {str(t.get("name")): t for t in after if isinstance(t, dict)}
    failing_before = [t for t in before if isinstance(t, dict) and t.get("outcome") == "failed"]
    read_before = {str(f.test.get("name")): f for f in read([("", t) for t in failing_before])}
    still_failing = [now[name] for name in read_before if (now.get(name) or {}).get("outcome") == "failed"]
    read_after = {str(f.test.get("name")): f for f in read([("", t) for t in still_failing])}
    went_back = any(t.get("outcome") == "passed" and (now.get(str(t.get("name"))) or {}).get("outcome") == "failed"
                    for t in before if isinstance(t, dict))
    forward: list[str] = []
    readable = False
    for name, was in read_before.items():
        outcome = (now.get(name) or {}).get("outcome")
        if outcome == "passed":
            readable = True
            forward.append(f"`{name}` passes now")
            continue
        if name not in read_after:
            continue
        moved = _compared(was, read_after[name])
        if moved is None:
            continue
        readable = True
        if moved > 0:
            forward.append(f"`{name}` now fails at {_where_it_failed(read_after[name])} "
                           f"(before the fix: {_where_it_failed(was)})")
        elif moved < 0:
            went_back = True
    if not readable:
        return None
    if went_back or not forward:
        return ""
    return "; ".join(forward[:3]) + (f"; and {len(forward) - 3} more" if len(forward) > 3 else "")


def with_the_new_evidence(cycle: Any, index: int, said: str) -> Any:
    """`cycle` with defect `index` noting how its tests moved forward, in place of the note an earlier kept fix left."""
    try:
        defect = cycle.defects[index]
        kept = [line for line in _plain(defect.actual_behavior).splitlines() if not line.startswith(MOVED_EVIDENCE)]
        note = f"{MOVED_EVIDENCE} {said}. What stops them there now is what is left to fix."
        changed = defect.model_copy(update={"actual_behavior": "\n".join([*kept, note]).strip()})
        return cycle.model_copy(update={"defects": [changed if i == index else d for i, d in enumerate(cycle.defects)]})
    except Exception:  # noqa: BLE001 - the defect keeps the evidence it had
        return cycle


# --- the forward repair ------------------------------------------------------------------------------------------


def _the_end_of(text: Any, most: int) -> str:
    text = _plain(text).strip()
    return text if len(text) <= most else "..." + text[-most:]


def the_new_step(tests: Sequence[dict], broken: Sequence[str]) -> str:
    """The one step every broken acceptance test stops at now, said for a repair; "" when they stop at more than one,
    or one of them cannot be read.

    `tests`: the suite's result after the fix, as {name, outcome, message}; `broken`: "acceptance: <key>" for each test
    that passed before the fix.
    """
    from app.ci import stable

    wanted = {stable(_bare(item.removeprefix("acceptance: "))) for item in broken if item.startswith("acceptance: ")}
    if not wanted or len(wanted) != len([item for item in broken if item.startswith("acceptance: ")]):
        return ""
    mine: dict[str, dict] = {}
    for test in tests:
        name = stable(_plain(test.get("name")))
        if name in wanted and test.get("outcome") == "failed":
            mine.setdefault(name, test)
    if set(mine) != wanted:
        return ""
    failures = read([("", t) for t in mine.values()])
    steps = set()
    for failure in failures:
        step = failure.frame or failure.request or where_it_threw(failure.test.get("message"))
        how = _how(failure)
        if not step or not how:
            return ""
        # A thrown error's own values (an id, a count) differ from test to test; its words do not.
        steps.add((step, re.sub(r"\d+", "#", how) if how.startswith("threw") else how))
    if len(steps) != 1:
        return ""
    step, how = next(iter(steps))
    first = failures[0].test
    return (f"{len(failures)} test(s) that passed before your change fail now, every one at the same step: {step}, "
            f"{how}. The first of them, `{first.get('name')}`, failed with:\n"
            f"{_the_end_of(first.get('message'), MOST_FAILURE)}")


def _the_unit_run_said(root: str | Path) -> str:
    try:
        from app.ci import UNIT_RUN_FILE

        saved = json.loads((Path(root) / UNIT_RUN_FILE).read_text(encoding="utf-8"))
        return _the_end_of(saved.get("output") if isinstance(saved, dict) else "", MOST_FAILURE)
    except (OSError, ValueError):
        return ""


def what_a_repair_is_given(root: str | Path, before: Any, after: Any, broken: Sequence[str]) -> str:
    """What a forward repair of a fix is handed: the start or build failure the fix caused, or the one new step the
    tests it broke stop at, with the end of the server's log; "" when the fix is reverted as before without one.

    `before` and `after` are the measurements (`ci.Snapshot`) before and after the fix; `broken` is what it broke.
    A product that did not start before the fix is not this fix's to repair, nor is anything the harness could not
    measure.
    """
    try:
        from app.ci import UNIT_TESTS_DID_NOT_RUN

        if before is None or not broken or _plain(getattr(after, "unmeasured", "")):
            return ""
        # Only a result of the product as it is now: a split of the fix measured since is of another product.
        result = _the_result_of_the_product_as_it_is(root) or {}
        log = _the_end_of(result.get("server_log"), LOG_TAIL)
        logged = f"\nThe end of the server's log:\n{log}" if log else ""
        if after.problem and not before.problem:
            return ("The product no longer starts, or no longer builds, after your change; it did before it. What the "
                    f"start said:\n{_the_end_of(after.problem, MOST_FAILURE)}{logged}")
        if after.problem:
            return ""
        unit_broke = (after.unit.get(UNIT_TESTS_DID_NOT_RUN) == "failed" and before.unit_ran
                      and before.unit.get(UNIT_TESTS_DID_NOT_RUN) != "failed")
        if unit_broke:
            said = _the_unit_run_said(root)
            return ("The project's unit tests no longer build or start after your change; they did before it."
                    + (f" What their run said:\n{said}" if said else ""))
        if all(str(item).startswith("acceptance: ") for item in broken):
            criteria = list((result.get("criteria") or {}).keys()) + list((result.get("change_requests") or {}).keys())
            step = the_new_step(_the_tests(result, criteria), [str(item) for item in broken])
            if step:
                return step + logged
        return ""
    except Exception:  # noqa: BLE001 - reverted as before
        logger.debug("Could not read what a forward repair is given", exc_info=True)
        return ""


#: What a fix's diff never counts: the harness's records, the workflow's documents, test results and caches.
_NOT_THE_PRODUCT = (":(exclude,glob).harness/**", ":(exclude,glob)docs/**", ":(exclude,glob)**/test-results/**",
                    ":(exclude,glob)**/__pycache__/**")


def the_files_it_changed(root: str | Path, base: str) -> list[str]:
    """The files a fix changed since `base`, committed or not, new ones too, that still exist."""
    from app.ci import _git

    changed = _git(root, "diff", "--name-only", base, "--", ".", *_NOT_THE_PRODUCT)
    new = _git(root, "ls-files", "--others", "--exclude-standard", "--", ".", *_NOT_THE_PRODUCT)
    names = [line.strip() for result in (changed, new) if result is not None and result.returncode == 0
             for line in result.stdout.splitlines() if line.strip()]
    return [name for name in dict.fromkeys(names) if (Path(root) / name).is_file()]


def _the_diff(root: str | Path, base: str, files: Sequence[str]) -> str:
    from app.ci import _git

    shown = _git(root, "diff", base, "--", *files)
    text = shown.stdout if shown is not None and shown.returncode == 0 else ""
    new = [name for name in files if f"b/{name}" not in text]
    if new:
        text += "".join(f"\n(new file) {name}" for name in new)
    if len(text) > MOST_DIFF:
        text = text[:MOST_DIFF] + "\n... (the diff is cut here; read the files for the rest)"
    return text.strip()


def the_repair_asked(root: str | Path, base: str, defect: Any, what: str) -> tuple[Any, list[str]]:
    """The defect as its fix's repair is asked it, and the files the repair may rewrite: those the fix changed, the
    ones `what` names first, at most the rewrite's own `MOST_FILES`."""
    from app.graph.rewritten_fixes import MOST_FILES

    files = sorted(the_files_it_changed(root, base), key=lambda name: name not in what and Path(name).name not in what)
    files = files[:MOST_FILES]
    if not files:
        return defect, []
    asked = defect.model_copy(update={
        "expected_behavior": REPAIR_EXPECTED,
        "actual_behavior": (f"{REPAIR_HEADING}\n{what}\n\nYour change, as a diff against the version before it:\n"
                            f"{_the_diff(root, base, files)}"),
        "reproduction_steps": REPAIR_STEPS,
        "affected_files": files,
    })
    return asked, files


@dataclass
class ForwardRepair:
    """One forward repair of one fix stage: tried at most once, and what came of it.

    `rewrite(asked, files)` is the fix's own model rewriting `files` for the defect as `the_repair_asked` gives it;
    it returns the rewrite's output (with `changed_files`), or None when it declined or wrote nothing.
    """

    root: str
    base: str
    defect: Any
    rewrite: Callable[[Any, list[str]], Any]
    what: str = ""
    changed: list[str] = field(default_factory=list)

    @property
    def tried(self) -> bool:
        return bool(self.what)

    def attempt(self, what: str) -> bool:
        """Hand the fix's own model what its fix broke; whether it changed a file. Once a stage. Never raises."""
        if self.tried or not what:
            return False
        self.what = what
        try:
            asked, files = the_repair_asked(self.root, self.base, self.defect, what)
            if not files:
                return False
            output = self.rewrite(asked, files)
            self.changed = [str(f) for f in (getattr(output, "changed_files", None) or [])]
        except Exception as failure:  # noqa: BLE001 - reverted as before
            from app.observability.degraded import degraded

            degraded("fix.repair_forward", failure)
            self.changed = []
        return bool(self.changed)

    def said(self, broke: Sequence[str]) -> str:
        """The ledger's detail of this repair after the fix was judged again; "" when none was tried."""
        if not self.tried:
            return ""
        why = " ".join(self.what.split())[:300]
        if not self.changed:
            return f"{REVERTED_AFTER_A_REPAIR}: the repair changed no file; it was handed: {why}"
        if broke:
            return (f"{REVERTED_AFTER_A_REPAIR}: after it rewrote {', '.join(self.changed)}, the fix still broke "
                    f"{'; '.join(map(str, broke[:3]))}; it was handed: {why}")
        return f"{REPAIR_HELD}: it rewrote {', '.join(self.changed)}; it was handed: {why}"

    def outcome(self, settled_as: str, broke: Sequence[str]) -> str:
        """The attempt's outcome for the defect's history, with this repair in it."""
        if not self.tried:
            return settled_as
        if broke:
            return f"{REVERTED_AFTER_A_REPAIR}: it broke {'; '.join(map(str, broke[:3]))}"
        return f"{settled_as} ({REPAIRED_FORWARD}: {' '.join(self.what.split())[:200]})"


__all__ = [
    "ForwardRepair", "MOVED_EVIDENCE", "MOVED_FORWARD", "PROFILES_FILE", "REPAIRED_FORWARD", "REPAIR_HELD",
    "REVERTED_AFTER_A_REPAIR", "moved_forward", "progress", "remember_before", "the_files_it_changed",
    "the_new_step", "the_repair_asked", "what_a_repair_is_given", "with_the_new_evidence",
]
