"""What a reverted fix broke, kept for the fixer of its defect that comes next (LF.1547). Always on: a quality fix.

Measured on two runs. On one, a schema-conformance finding was rewritten alone three times; each rewrite of the same
file broke the same unit test, was reverted, and the next rewrite made the same change again until the defect went to
a person. Each later request carried only the broken test's name, twice over, and an instruction to change the test -
to a rewrite that could write the product's file only. Neither the test's failure nor the change that caused it was
in front of it. On the other, a fix of two files broke one criterion's tests, and its replay broke them again.

- `record`: called by the fix guard while the reverted fix is still in the workspace (`engineering.after_a_fix`'s
  `on_revert`). Each test it broke, with what its runner said of it (bounded), and its change as a diff (bounded, the
  files its failures name first). Kept in `FILE` by the defect's cause key, else its wording, so a re-planned sprint's
  defect reads it too.
- `told`: what a fixer's request carries after a revert - the one-shot rewrite's and the tool-using fixer's alike: the
  tests that broke, what each said, the change that broke them, and the instruction to keep them passing.
- `repeated`: a defect whose one-shot rewrites were reverted twice for breaking the same test is not rewritten a third
  time. It goes to the tool-using fixer, both failures in front of it: that fixer can run the test, read it and change
  a test that is out of date, which the rewrite of the product's files cannot. The forward repair (LF.1271) is not a
  route to choose here: it runs at the measurement, when a fix stops the product or its broken tests stop at one new
  step, and had already run where it applied. Holding the defect for the next round changes nothing it is shown.
- `set_aside_if_doubtful`: a schema-conformance finding whose fix was reverted for breaking a test that passed is
  doubtful - a check's reading of the specification against a test that ran. It is recorded in the check findings,
  noted in the ledger as a suspected false finding, accepted as a risk with that reason, and not raised again
  (`doubtful`, read by the gate before its cap), as the language service's contradicted findings are (`analysis.checker_contradicted`).

Nothing here names a language or a framework. Every function never raises.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

logger = logging.getLogger(__name__)

FILE = ".harness/reverted-fixes.json"
#: Reverts kept per defect, newest last; shown to one fixer, newest last.
MOST_KEPT = 4
MOST_SHOWN = 2
#: Broken tests recorded per revert, and characters of the reverted change's diff.
MOST_TESTS = 3
MOST_DIFF = 2_400
#: Characters of a broken item that is not a test (the build, the start), as recorded.
MOST_OTHER = 600

HEADING = "--- What earlier changes for this defect broke, measured by the harness and put back ---"
SAID = ("Each change below was put back because tests that passed before it failed after it. Keep each of those "
        "tests passing: make the change this defect needs without the part that made them fail.")
#: The ledger detail of a rewrite not asked a third time; the effects report counts it.
STOPPED = "not rewritten a third time"
#: The reason a doubtful schema finding is accepted as a risk; the effects report counts it.
DOUBTFUL = ("A doubtful finding: the specification's record was read as needing a field the code does not declare, and "
            "the fix that added it broke a test that passed before it. Set aside, not fixed again: ")
#: The check the doubtful findings are recorded under (`acceptance.check_findings`).
CHECK = "schema conformance, contradicted by a passing test"
#: How the gate's schema-conformance findings begin and the source they are raised under (`analysis.schema_conformance`).
_SCHEMA_SOURCE = "schema conformance"
_SCHEMA_WORDS = "Schema conformance:"

_A_TEST = ("unit: ", "acceptance: ")
_WHERE = " › "
_VARYING = re.compile(r"\"[^\"]*\"|'[^']*'|\d+")
_WRITING = threading.Lock()


def _wording(defect: Any) -> str:
    text = str(getattr(defect, "description", "") or "")
    return "wording:" + " ".join(_VARYING.sub("_", text).split()).lower()[:300]


def _keys(defect: Any) -> set[str]:
    """The keys one defect is found under: its cause key where it has one, and its wording."""
    keys = {_wording(defect)}
    try:
        from app.sprint.cause import key_of

        cause = key_of(defect)
        if cause:
            keys.add("cause:" + cause)
    except Exception:  # noqa: BLE001 - its wording alone
        pass
    return keys


def _read(root: str | Path) -> dict[str, Any]:
    try:
        data = json.loads((Path(root) / FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(root: str | Path, data: dict[str, Any]) -> None:
    path = Path(root) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def _reverts(root: str | Path, defect: Any) -> list[dict[str, Any]]:
    """This defect's recorded reverts, oldest first."""
    keys = _keys(defect)
    found = [entry for entry in _read(root).get("reverts") or []
             if isinstance(entry, dict) and keys & set(entry.get("keys") or [])]
    return found[-MOST_KEPT:]


def _bare(key: str) -> str:
    return key.rsplit(_WHERE, 1)[-1].strip()


def _what_the_unit_report_says(root: Path) -> dict[str, str]:
    """{a unit test's key, as the fix guard names it: its message} from the stack pack's unit report on disk."""
    from app import ci
    from app.acceptance import junit
    from app.stacks import contract

    found = contract.the_pack(root)
    if found is None:
        return {}
    pack, record = found
    report = junit.read(root / str(record.get("project") or "") / pack.unit_report)
    said: dict[str, str] = {}
    for test in report.tests:
        if test.outcome == "passed":
            continue
        for key in ci.outcomes_of([test]):
            said[key] = str(test.message or "")
    return said


def _what_the_suite_says(root: Path) -> dict[str, str]:
    """{an acceptance test's own name: its message} from the suite's last saved result."""
    from app.acceptance import suite

    result = suite.last_result(root) or {}
    said: dict[str, str] = {}
    for kind in ("criteria", "change_requests"):
        held = result.get(kind) if isinstance(result.get(kind), dict) else {}
        for criterion in held.values():
            for test in (criterion or {}).get("tests") or []:
                if isinstance(test, dict) and test.get("name") and test.get("outcome") != "passed":
                    said[str(test["name"]).strip()] = str(test.get("message") or "")
    return said


def _what_each_said(root: Path, broken: Sequence[str]) -> list[dict[str, str]]:
    from app import ci

    tests = [str(item) for item in broken if str(item).startswith(_A_TEST)][:MOST_TESTS]
    if not tests:
        return []
    unit = _what_the_unit_report_says(root) if any(t.startswith("unit: ") for t in tests) else {}
    acceptance = _what_the_suite_says(root) if any(t.startswith("acceptance: ") for t in tests) else {}
    found = []
    for item in tests:
        kind, key = item.split(": ", 1)
        # By the whole key, else by the test's own name: a measurement taken before keys carried where a test lives.
        message = (unit.get(key) or next((said for other, said in unit.items() if _bare(other) == _bare(key)), "")
                   if kind == "unit" else acceptance.get(_bare(key), ""))
        found.append({"name": item, "said": ci._what_it_says(message) if message.strip() else ""})
    return found


def _named_in(path: str, text: str) -> bool:
    stem = PurePosixPath(path).stem
    return path in text or PurePosixPath(path).name in text or (len(stem) >= 4 and stem in text)


def _the_change(root: Path, base: str, failures: str) -> tuple[str, list[str]]:
    """The reverted change as a diff against `base`, the files its failures name first, at most `MOST_DIFF`
    characters; and the files it changed."""
    from app.ci import _git
    from app.graph.judged_fixes import the_files_it_changed

    files = sorted(the_files_it_changed(root, base), key=lambda path: not _named_in(path, failures))
    pieces: list[str] = []
    room = MOST_DIFF
    left: list[str] = []
    for path in files:
        if room <= 0:
            left.append(path)
            continue
        shown = _git(root, "diff", "--no-color", "-U2", base, "--", path)
        text = shown.stdout if shown is not None and shown.returncode == 0 else ""
        text = "\n".join(line for line in text.splitlines() if not line.startswith(("index ", "diff --git ")))
        if not text.strip():
            text = f"(a new file) {path}"
        if len(text) > room:
            text = text[:room].rstrip() + "\n... (cut here)"
        pieces.append(text)
        room -= len(text)
    if left:
        pieces.append("Also changed, not shown: " + ", ".join(left))
    return "\n".join(pieces).strip(), files


def record(root: str | Path, base: str, defect: Any, stage: str, broken: Sequence[str], made_by: str = "") -> None:
    """Keep what the fix of `stage` broke while it is still in the workspace, about to be reverted.

    `made_by`: "rewrite" for the harness's one-shot rewrite (`repeated` counts only these), else how the change was
    made. Never raises.
    """
    try:
        if not root or not base or not broken:
            return
        root = Path(root)
        tests = _what_each_said(root, broken)
        other = [" ".join(str(item).split())[:MOST_OTHER] for item in broken if not str(item).startswith(_A_TEST)][:2]
        failures = "\n".join([*(f"{t['name']}\n{t['said']}" for t in tests), *other])
        diff, files = _the_change(root, base, failures)
        entry = {"keys": sorted(_keys(defect)), "stage": str(stage), "made_by": str(made_by or ""),
                 "tests": tests, "other": other, "files": files[:12], "diff": diff}
        with _WRITING:
            data = _read(root)
            data["reverts"] = [*(data.get("reverts") or []), entry][-200:]
            _write(root, data)
    except Exception:  # noqa: BLE001 - the fix is reverted as before
        logger.debug("Could not record what a reverted fix broke", exc_info=True)


def _shown(entry: dict[str, Any]) -> str:
    files = ", ".join(f"`{name}`" for name in entry.get("files") or []) or "no file of the product"
    lines = [f"- `{entry.get('stage') or '?'}` changed {files}. It broke:"]
    for test in entry.get("tests") or []:
        said = str(test.get("said") or "").strip()
        lines.append(f"  - `{test.get('name')}`" + (":\n    " + said.replace("\n", "\n    ") if said else
                                                     " (its runner's words were not kept)"))
    lines.extend(f"  - {item}" for item in entry.get("other") or [])
    if entry.get("diff"):
        lines.append(f"  The change that was put back:\n```diff\n{entry['diff']}\n```")
    return "\n".join(lines)


def told(root: str | Path, defect: Any) -> str:
    """The section a fixer of `defect` reads after a revert: what the last changes broke and how; "" when none was
    reverted. Never raises."""
    try:
        reverts = _reverts(root, defect)[-MOST_SHOWN:]
        if not reverts:
            return ""
        return "\n".join([HEADING, SAID, *(_shown(entry) for entry in reverts)]) + "\n"
    except Exception:  # noqa: BLE001 - the request goes as before
        return ""


def _names(entry: dict[str, Any]) -> list[str]:
    return [str(test.get("name") or "") for test in entry.get("tests") or [] if test.get("name")]


def repeated(root: str | Path, defect: Any) -> str:
    """Why `defect` is not given a one-shot rewrite again: its last two rewrites were reverted for breaking the same
    test; "" when it may be. Never raises."""
    try:
        rewrites = [entry for entry in _reverts(root, defect) if entry.get("made_by") == "rewrite"]
        if len(rewrites) < 2:
            return ""
        before, last = rewrites[-2], rewrites[-1]
        same = [name for name in _names(last) if name in _names(before)]
        if not same:
            return ""
        return (f"{STOPPED}: its rewrites `{before.get('stage')}` and `{last.get('stage')}` were each reverted for "
                f"breaking `{same[0]}`; the tool-using fixer takes it, shown both failures")
    except Exception:  # noqa: BLE001 - rewritten as before
        return ""


def _a_schema_finding(defect: Any) -> bool:
    return (str(getattr(defect, "source", "") or "") == _SCHEMA_SOURCE
            or str(getattr(defect, "description", "") or "").startswith(_SCHEMA_WORDS))


def set_aside_if_doubtful(root: str | Path, cycle: Any, index: int, broken: Sequence[str], *, stage: str = "",
                          round_: int | None = None, sprint: int | None = None) -> Any:
    """`cycle` with defect `index` accepted as a doubtful finding when it is a schema-conformance finding whose fix was
    just reverted for breaking a test that passed; else `cycle` as it is. Never raises."""
    try:
        defect = cycle.defects[index]
        tests = [str(item) for item in broken if str(item).startswith(_A_TEST)]
        if not tests or not _a_schema_finding(defect) or getattr(defect, "status", "open") != "open":
            return cycle
        from app.acceptance import check_findings
        from app.observability import defect_ledger
        from app.sprint import accept_risk

        reason = DOUBTFUL + f"it broke {tests[0]}."
        with _WRITING:
            data = _read(root)
            data["doubtful"] = sorted({*(data.get("doubtful") or []), _wording(defect)})
            _write(root, data)
        description = " ".join(str(defect.description or "").split())
        check_findings.noted(root, int(round_ or 0), CHECK, [f"{description} - its fix broke {tests[0]}"])
        defect_ledger.note(check_findings.SUSPECTED_FALSE, stage or "defect_fix", defect=defect, round_=round_,
                           index=index, sprint=sprint, detail=reason)
        logger.warning("Set aside a doubtful schema finding: its fix broke %s", tests[0])
        return accept_risk(cycle, index, reason=reason)
    except Exception:  # noqa: BLE001 - left open as before
        logger.debug("Could not set aside a doubtful finding", exc_info=True)
        return cycle


def doubtful(root: str | Path, finding: Any) -> bool:
    """Whether `finding` is a schema finding set aside as doubtful in this workspace. Never raises."""
    try:
        return _wording(finding) in set(_read(root).get("doubtful") or [])
    except Exception:  # noqa: BLE001
        return False


def effects_lines(records: Sequence[dict]) -> list[str]:
    """The effects report's lines: rewrites after a revert told what broke, repeats stopped, doubtful findings set
    aside."""
    from app.graph.anchored_edits import SYSTEM as EDITS_SYSTEM
    from app.graph.rewritten_fixes import WHOLE_FILE_SYSTEM

    told_rewrites = told_others = stopped = set_aside = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("kind") == "model_request":
            text = json.dumps(record.get("messages"), default=str)
            if HEADING in text:
                if WHOLE_FILE_SYSTEM in text or EDITS_SYSTEM in text:
                    told_rewrites += 1
                else:
                    told_others += 1
        elif record.get("kind") == "defect":
            detail = str(record.get("detail") or "")
            if STOPPED in detail:
                stopped += 1
            elif DOUBTFUL[:40] in detail:
                set_aside += 1
    return [
        f"  {told_rewrites:>4}  LF.1547 rewrites after a revert, told what broke (and {told_others} other fixer "
        "requests)",
        f"  {stopped:>4}  LF.1547 repeats stopped: a rewrite reverted twice for one test not asked a third time",
        f"  {set_aside:>4}  LF.1547 schema findings set aside as doubtful after a fix that broke a passing test",
    ]


__all__ = ["CHECK", "DOUBTFUL", "FILE", "HEADING", "STOPPED", "doubtful", "effects_lines", "record", "repeated",
           "set_aside_if_doubtful", "told"]
