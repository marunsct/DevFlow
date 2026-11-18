"""A unit test that keeps failing beside a green locked suite is set aside, not handed to fixers (behind `UNIT_TEST_QUARANTINE`).

Deep review 2026-11-18, item B6: the model that writes the product writes its unit tests after the code, so they
mirror it; when one disagrees with the locked acceptance suite, fixers chase it, are reverted for breaking it, and
the product ships with it failing ("own unit tests still fail and ship failing" in 28 of the last 150 runs). The locked
suite is the definition of done; and a failing unit test of the product's own lost a hidden or quality test no more
often than any run (`completion_verdict`, B4).

A unit test that fails in `TIMES` measurements of different product states, each beside a locked suite that passed
in full, is set aside: it is no longer raised as a defect, nor holds the release, and the record (`STORE`) names it,
why, and where its file went. Its file is moved to `FOLDER` when every test of that file failed; a file holding a
test that passes stays where it is, so no passing test leaves the run. Nothing is deleted. The release names each
set aside as a note.

Not done: a unit run that did not compile names no test and no file in its report, so it is raised as before; and
keeping only tests that kill a deliberate change the suite misses needs mutation data per unit test, which no run
records.

A switch: it changes what blocks a run.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from app.observability.degraded import degraded
from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: The record of each failing unit test's measurements and of each set aside.
STORE = ".harness/quarantined_unit_tests.json"
#: Where a file whose every test failed is moved: the harness's own folder, so no runner collects it.
FOLDER = ".harness/quarantined-unit-tests"
#: Measurements of different product states a test must fail in, each beside a green locked suite.
TIMES = 2
#: How the release's note begins; the audit's switch-firing check reads it.
SET_ASIDE = "unit test(s) were set aside, not raised as defects:"
WHY = f"it failed in {TIMES} measurements of the product while the locked acceptance suite passed in full"


def enabled() -> bool:
    return is_on("UNIT_TEST_QUARANTINE", ON_BY_DEFAULT)


def _read(root: Path) -> dict[str, Any]:
    try:
        found = json.loads((root / STORE).read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(root: Path, record: dict[str, Any]) -> None:
    (root / STORE).parent.mkdir(parents=True, exist_ok=True)
    (root / STORE).write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def set_aside(repo_root: str | Path) -> dict[str, dict[str, str]]:
    """Each unit test set aside so far: name -> {why, file, moved_to}; {} when none or off."""
    if not enabled():
        return {}
    return dict(_read(Path(repo_root)).get("set_aside") or {})


def _the_file(root: Path, project: str, key: str) -> Path | None:
    """The test file a unit outcome's key names, inside the repository; None when the key names none on disk."""
    from app import ci

    if ci.WHERE not in key:
        return None
    where = key.rsplit(ci.WHERE, 1)[0].strip()
    for base in (root / project, root):
        candidate = (base / where).resolve()
        if candidate.is_file() and candidate.is_relative_to(root.resolve()):
            return candidate
    return None


def after_a_green_measurement(repo_root: str | Path, outcomes: dict[str, str], fingerprint: str,
                              project: str = "") -> list[str] | None:
    """Count this measurement's failing unit tests, set aside each failing for the `TIMES`-th time, and return the
    failing tests still to be raised; None when off or nothing could be read. Never raises.

    `outcomes` is each unit test's outcome in this measurement, which the locked suite passed in full beside;
    `fingerprint` names the product state measured, so one state measured twice counts once.
    """
    if not enabled() or not outcomes or not fingerprint:
        return None
    try:
        from app import ci

        root = Path(repo_root)
        record = _read(root)
        seen: dict[str, list[str]] = {k: list(v) for k, v in (record.get("seen") or {}).items()}
        aside: dict[str, dict[str, str]] = dict(record.get("set_aside") or {})
        failing = sorted(key for key, outcome in outcomes.items() if outcome == "failed")
        still: list[str] = []
        for key in failing:
            if key in aside:
                continue
            states = seen.setdefault(key, [])
            if fingerprint not in states:
                states.append(fingerprint)
            if len(states) < TIMES:
                still.append(key)
                continue
            entry = {"why": WHY, "file": "", "moved_to": ""}
            path = _the_file(root, project, key)
            if path is not None:
                entry["file"] = str(path.relative_to(root.resolve()))
                where = key.rsplit(ci.WHERE, 1)[0]
                same_file = {k: o for k, o in outcomes.items() if ci.WHERE in k and k.rsplit(ci.WHERE, 1)[0] == where}
                if same_file and all(o == "failed" for o in same_file.values()):
                    target = root / FOLDER / entry["file"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(target))
                    entry["moved_to"] = str(target.relative_to(root))
                    # The file's other tests go with it: each failed too.
                    for other in same_file:
                        aside.setdefault(other, {**entry})
            aside[key] = entry
            logger.warning("Set aside the unit test %s: %s", key, WHY)
        still = [key for key in still if key not in aside]
        _write(root, {"seen": seen, "set_aside": aside})
        return still
    except Exception as error:  # noqa: BLE001 - raised as before
        degraded("unit_quarantine.count", error)
        return None


def raised_beside_a_green_suite(repo_root: str | Path) -> bool:
    """Whether a round's failing unit run, beside a locked suite that passed in full, is still raised as a defect.

    True unless every failing test in the runner's report is now set aside; True when off or nothing could be read.
    """
    if not enabled():
        return True
    try:
        from app import ci
        from app.acceptance.unstable import fingerprint
        from app.stacks import contract

        read = ci.unit_outcomes_in_the_pack_s_report(repo_root)
        if read is None or not read[1] or not any(outcome == "failed" for outcome in read[0].values()):
            return True  # no test named failing: the run itself failed, and is raised as before
        project = str((contract.read(repo_root) or {}).get("project") or "")
        still = after_a_green_measurement(repo_root, read[0], fingerprint(repo_root), project)
        return still is None or bool(still)
    except Exception:  # noqa: BLE001 - raised as before
        logger.debug("Could not read the unit run beside a green suite", exc_info=True)
        return True


def without_those_set_aside(repo_root: str | Path, failing: list[str]) -> list[str]:
    """`failing` less the unit tests set aside, compared by name as the release names them."""
    aside = set_aside(repo_root)
    if not aside:
        return list(failing)
    from app import ci

    names = {*aside, *(ci.stable(k) for k in aside)}
    return [name for name in failing if name not in names and ci.stable(name) not in names]


def release_note(repo_root: str | Path) -> list[str]:
    """The release's note naming each unit test set aside and where its file is; [] when none or off."""
    aside = set_aside(repo_root)
    if not aside:
        return []
    each = "; ".join(f"{name}" + (f" (moved to {e['moved_to']})" if e.get("moved_to", "").startswith(FOLDER) else "")
                     for name, e in list(aside.items())[:6])
    more = f"; and {len(aside) - 6} more" if len(aside) > 6 else ""
    return [f"{len(aside)} {SET_ASIDE} {WHY}: {each}{more}."[:800]]


__all__ = ["FOLDER", "ON_BY_DEFAULT", "SET_ASIDE", "STORE", "TIMES", "WHY", "after_a_green_measurement", "enabled",
           "raised_beside_a_green_suite", "release_note", "set_aside", "without_those_set_aside"]
