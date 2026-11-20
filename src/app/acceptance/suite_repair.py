"""The one record of a locked suite's repair: what was sent, each version measured, and the best of them.

Suite-repair design review 2026-11-20: four fixes in one day (a rewrite read as "not changed", a put-back that lost the
harness's own better rewrite, and two more) shared one cause - each check read its own store (`repair_bodies`,
`before_repair`, `repair_best`, a folder of the best files) while another writer changed what that store described.
This module alone writes `.harness/suite-repair.json`, and the suite's repair checks (`app.acceptance.suite`) read it:

- `opened`: when, and the lock version the repair began from;
- `sent`: each test sent for repair with its code as the repair began (a sibling added later with its own);
- `versions`: version 0 is the lock as measured before the repair; each later one is a measured version of the suite
  - who left it (`writers`, or `put back` by the harness), its digest, the tests run (a skipped test did not run),
  passed and failed, whether the product started, the failing names, and the sent tests it had changed;
- `best`: the index of the version that ran the most tests and, among those, passed the most. Its files are kept under
  `.harness/suite-repair/vN/`; version 0's are the lock's snapshot. A version measured while the product did not start
  is never the best: it measured nothing about the tests.

Every lock removes the record. The suite's names under repair stay in its own state (`repairing`), read by many
writing-time guards; the once-per-lock send-backs at the review's limit stay there too, since a first writing has them
with no repair open. Neither is a measured version, so neither can disagree with this record.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from app.stacks import contract

logger = logging.getLogger(__name__)

FILE = f"{contract.HARNESS_DIR}/suite-repair.json"
VERSIONS_DIR = f"{contract.HARNESS_DIR}/suite-repair"
#: Who left a measured version.
BY_THE_WRITERS = "writers"
BY_A_PUT_BACK = "put back"
#: The stores this record replaced, read once from a workspace a repair was open in when the harness changed.
_EARLIER_KEYS = ("repair_bodies", "before_repair", "repair_best")
_EARLIER_BEST_DIR = f"{contract.HARNESS_DIR}/acceptance-repair-best"


def read(repo_root: str | Path) -> dict[str, Any]:
    """The open repair's record; {} when no repair is open. Never raises."""
    try:
        record = json.loads((Path(repo_root) / FILE).read_text(encoding="utf-8"))
        return record if isinstance(record, dict) else {}
    except (OSError, ValueError):
        return _from_the_earlier_stores(repo_root)


def _write(repo_root: str | Path, record: dict[str, Any]) -> None:
    path = Path(repo_root) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")


def _from_the_earlier_stores(repo_root: str | Path) -> dict[str, Any]:
    """A repair opened before this record existed, as a record; {} when there was none."""
    from app.acceptance import suite

    state = suite._state(repo_root)
    if "lock" in state or not any(key in state for key in _EARLIER_KEYS):
        return {}
    before = state.get("before_repair") or {}
    record: dict[str, Any] = {
        "opened": {"lock_version": state.get("lock_version")},
        "sent": {str(name): str(body) for name, body in (state.get("repair_bodies") or {}).items()},
        "versions": [{"by": "lock", **({"tests": int(before.get("tests") or 0), "passed": int(before.get("passed") or 0)}
                                       if before else {})}],
        "best": 0,
    }
    best = state.get("repair_best") or {}
    earlier = Path(repo_root) / _EARLIER_BEST_DIR
    if best and earlier.is_dir():
        target = Path(repo_root) / VERSIONS_DIR / "v1"
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(earlier, target)
        record["versions"].append({"by": BY_THE_WRITERS, "tests": int(best.get("tests") or 0),
                                   "passed": int(best.get("passed") or 0), "changed": list(best.get("changed") or []),
                                   "files": f"{VERSIONS_DIR}/v1"})
        record["best"] = 1
    return record


def opened(repo_root: str | Path, tests: list[str], bodies: dict[str, str]) -> None:
    """Open the record, when no repair is open, with version 0 as the lock last measured; and add each of `tests` to
    what was sent with its code in `bodies`, a test already sent keeping the code it had when first sent."""
    from app.acceptance import suite

    record = read(repo_root)
    if not record:
        last = suite.last_result(repo_root)
        lock = {"by": "lock"}
        if last.get("ran"):
            tests_run, passed = suite._run_and_passed(int(last.get("passed") or 0), int(last.get("failed") or 0))
            lock.update(tests=tests_run, passed=passed)
        record = {"opened": {"at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                             "lock_version": suite._state(repo_root).get("lock_version")},
                  "sent": {}, "versions": [lock], "best": 0}
    sent = record.setdefault("sent", {})
    for name in tests:
        if str(name) in bodies and str(name) not in sent:
            sent[str(name)] = bodies[str(name)]
    _write(repo_root, record)


def sent(repo_root: str | Path) -> dict[str, str]:
    """Each test sent for repair, with its code as the repair began; {} when no repair is open."""
    return dict(read(repo_root).get("sent") or {})


def before(repo_root: str | Path) -> dict[str, Any]:
    """What the suite measured before the repair ({"tests", "passed"}); {} when that was never measured."""
    versions = read(repo_root).get("versions") or [{}]
    return {key: versions[0][key] for key in ("tests", "passed") if key in versions[0]} if "tests" in versions[0] else {}


def best(repo_root: str | Path) -> dict[str, Any]:
    """The repair's best measured version other than the lock ({"tests", "passed", "changed", "files"}); {} when the
    lock is still the best, or its files are gone."""
    record = read(repo_root)
    index = int(record.get("best") or 0)
    versions = record.get("versions") or []
    if not index or index >= len(versions):
        return {}
    version = versions[index]
    if not version.get("files") or not (Path(repo_root) / version["files"]).is_dir():
        return {}
    return version


def _did_not_start(result: Any) -> bool:
    """Whether a measurement says the product never came up: its problem, or every failure, says so."""
    from app.acceptance import suite

    if str(getattr(result, "problem", "") or "").startswith(suite.PRODUCT_DID_NOT_START):
        return True
    failed = [test for test in result.report.tests if test.outcome == "failed"]
    return bool(failed) and len(failed) >= result.report.passed and all(
        suite.failed_because_the_product_did_not_start(test.message) for test in failed)


def measured(repo_root: str | Path, result: Any, *, by: str = BY_THE_WRITERS) -> bool:
    """Record the suite as it stands, as `result` measured it, as the repair's next version; keep it as the best when
    it ran no fewer tests and passed no fewer than the best so far (version 0, the lock, to begin with), the product
    started, and it is not the lock itself. Whether it became the best. No model call. Never raises.

    A version that passes more by running fewer tests is never the best: a loss of tests is not a gain.
    """
    from app.acceptance import suite

    try:
        record = read(repo_root)
        if not record or not result.ran:
            return False
        root = Path(repo_root)
        now = {path.relative_to(root).as_posix(): path.read_text(encoding="utf-8", errors="replace")
               for path in suite.suite_files(repo_root)}
        bodies = suite._test_bodies(repo_root)
        tests, passed = suite._counted(result)
        started = not _did_not_start(result)
        version: dict[str, Any] = {
            "by": by,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "digest": hashlib.sha1(json.dumps(now, sort_keys=True).encode("utf-8")).hexdigest()[:16],
            "tests": tests, "passed": passed, "failed": result.report.failed, "started": started,
            "failing": [str(test.name) for test in result.report.tests if test.outcome == "failed"][:200],
            # The tests sent for repair this version changed: a test a kept version has rewritten is a changed one.
            "changed": sorted(name for name, body in (record.get("sent") or {}).items()
                              if name in bodies and bodies[name].strip() != str(body).strip()),
        }
        versions = record.setdefault("versions", [{"by": "lock"}])
        versions.append(version)
        bar = versions[int(record.get("best") or 0)]
        better = bool("tests" in versions[0] and started and now
                      and now != suite._the_files_of(root / suite.SNAPSHOT_DIR) and suite._no_worse_than(tests, passed, bar))
        if better:
            number = len(versions) - 1
            kept = root / VERSIONS_DIR / f"v{number}"
            shutil.rmtree(kept, ignore_errors=True)
            for path in suite.suite_files(repo_root):
                target = kept / path.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            version["files"] = f"{VERSIONS_DIR}/v{number}"
            earlier = versions[int(record.get("best") or 0)].get("files")
            if earlier:
                shutil.rmtree(root / earlier, ignore_errors=True)
            record["best"] = number
        _write(repo_root, record)
        return better
    except Exception as error:  # noqa: BLE001 - without it, the best kept so far is what comes back
        logger.debug("The repair's version could not be recorded: %s", error)
        return False


def closed(repo_root: str | Path) -> None:
    """At every lock: the repair's record and its kept versions are gone, and so are the stores it replaced."""
    root = Path(repo_root)
    (root / FILE).unlink(missing_ok=True)
    shutil.rmtree(root / VERSIONS_DIR, ignore_errors=True)
    shutil.rmtree(root / _EARLIER_BEST_DIR, ignore_errors=True)


__all__ = ["BY_A_PUT_BACK", "BY_THE_WRITERS", "FILE", "VERSIONS_DIR", "before", "best", "closed", "measured", "opened",
           "read", "sent"]
