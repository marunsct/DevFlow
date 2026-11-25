"""A language service's finding that the product's own run contradicts is the service's word, not a failure (LF.1455).

A finding that an import names nothing - `"settings" is unknown import symbol` - was raised as "this fails when the
code runs", and the fix guard reverted fixes on the same certainty. An import that fails, fails when its module loads.
Measured on one medium run: the language service raised three such defects while the harness's own measurement read
15 of 15 acceptance tests passing and the service's 18 unit tests passed - the code had run. Six fixers spent 43
minutes on them, said "a false positive from the language service", and the two that wrote the regression test asked
for had it reverted because the test imports the same names.

`contradicted` answers, for one finding about an import, what in the latest measurement contradicts it: tests of that
very file passed, or - for the product's own code - the product started and acceptance tests passed against it. The
gate words such a finding as the service's, a suspected false finding to check before changing anything, and the fix
guard never reverts on it; each is recorded in the check findings, so an audit can count them. A finding about a name
inside a function, which fails only when that function is called, is left as it was. Nothing here names a language:
the import findings are read as each service words them. Never raises.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

#: How a language service says an import names nothing: Pyright, TypeScript and the compilers' wording.
_AN_IMPORT_FINDING = re.compile(
    r"is unknown import symbol|could not be resolved|has no exported member|Cannot find module"
    r"|is not a known attribute of module|does not provide an export named|has no default export", re.I)
#: How a gate's defect ends for such a finding.
SUSPECTED_FALSE = (" - the language service reports this, and the product's own run contradicts it: a suspected false "
                   "finding. Check it against the code before changing anything.")
#: The check the findings are recorded under (`acceptance.check_findings`).
CHECK = "language service, contradicted by the measurement"


def is_about_an_import(message: str) -> bool:
    """Whether a finding says an import names nothing, which fails as the module loads."""
    return bool(_AN_IMPORT_FINDING.search(str(message or "")))


def _its_tests(relative: str, names: Any) -> list[str]:
    """The keys among `names` of tests in the file `relative`: its folder and stem, as a runner's report keys them."""
    path = PurePosixPath(str(relative))
    stem = path.name.split(".", 1)[0]
    if len(stem) < 3:
        return []
    wanted = f".{path.parent.name}.{stem}." if path.parent.name else f".{stem}."
    found = []
    for key in names or ():
        for part in str(key).split(" › ")[:-1]:
            dotted = "." + part.strip().replace("/", ".").replace("\\", ".") + "."
            if wanted in dotted or dotted == f".{stem}.":
                found.append(str(key))
                break
    return found


def contradicted(relative: str, message: str, measured: Any) -> str:
    """What in the measurement `measured` (a `ci.Snapshot`) contradicts a finding about an import in `relative`; ""
    when nothing does, the finding is about something else, or there is no measurement."""
    try:
        if measured is None or not is_about_an_import(message):
            return ""
        passing = [name.split(": ", 1)[1] for name in measured.passing() if ": " in name]
        own = _its_tests(relative, passing)
        if own:
            return f"{len(own)} test(s) of `{relative}` passed in the latest measurement, which loads its imports"
        from app.analysis.file_kinds import classify_file

        if classify_file(relative) != "application" or getattr(measured, "problem", "") \
                or not getattr(measured, "acceptance_ran", False):
            return ""
        acceptance = getattr(measured, "acceptance", None) or {}
        passed = sum(outcome == "passed" for outcome in acceptance.values())
        if not passed:
            return ""
        return (f"the product started and {passed} of {len(acceptance)} acceptance test(s) passed against it in the "
                "latest measurement")
    except Exception:  # noqa: BLE001 - no contradiction read is none
        return ""


def recorded(root: Any, relative: str, message: str, why: str) -> None:
    """Record a contradicted finding in the check findings. Never raises."""
    try:
        from app.acceptance import check_findings

        check_findings.noted(root, 0, CHECK, [f"{relative}: {message} - underlined, contradicted: {why}"])
    except Exception:  # noqa: BLE001 - the finding is worded so whether or not it is recorded
        pass


__all__ = ["CHECK", "SUSPECTED_FALSE", "contradicted", "is_about_an_import", "recorded"]
