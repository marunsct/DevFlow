"""In thorough delivery the harness's own unit run reaches the defect with its exception lines, not as a count (LF.1457).

The harness raises "The unit tests fail" with the unit run's failures grouped by cause only when it runs the round
itself: in fast delivery, or in thorough delivery behind `MEASURED_ROUND_WHEN_RED`. A thorough round run by the
tester was left to the tester's prose. Measured on one medium run in thorough delivery: the harness's unit report held
9 of 32 failing, grouped as `InvalidRequestError: One or more mappers failed to initialize` and `AmbiguousForeignKeysError
... Specify the 'foreign_keys' argument`, and earlier `'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'`,
printed in nine command results. Across the opening requests of all 19 stages of that sprint `visit_ARRAY` appeared 0
times; eleven carried "Unit tests: 23 of 32 pass". The tester's defect read "SQLAlchemy ARRAY type blocks SQLite table
creation in test fixtures".

After a tester's round, when the harness's unit run fails (`carried`):

- a defect the round raised about those tests - its text names a failing test's file or name - carries the grouped
  causes under its actual behaviour, as the harness measured them;
- when none did, the harness's own unit-test defect is raised, as fast delivery raises it.

Nothing here names a language or a runner: test names are read as the runner's report keys them. Never raises.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Sequence

#: How the grouped causes are headed under a defect's actual behaviour.
HEADING = "What the harness's own unit run printed, grouped by cause:"
#: Parts of a test's key that name no test: the runner, the folder every test sits in, a language's suffix.
_GENERIC = frozenset({"pytest", "tests", "test", "spec", "specs", "src", "unit", "index", "js", "ts", "tsx", "jsx",
                      "py", "mjs", "cjs", "go", "rs", "java", "cs", "php", "rb"})
#: A test name long enough to be told from words of prose.
SHORTEST_NAME = 12


def _what_names_them(failing: Sequence[str]) -> set[str]:
    """The files, classes and test names the failing tests' keys hold, as a defect's text would name them."""
    found: set[str] = set()
    for key in failing or ():
        parts = [part.strip() for part in str(key).split(" › ") if part.strip()]
        for part in parts[:-1]:
            found.update(piece for piece in re.split(r"[/\\.:]+", part) if len(piece) >= 5 and piece.lower() not in _GENERIC)
        if parts and len(parts[-1]) >= SHORTEST_NAME:
            found.add(parts[-1])
    return found


def _names_them(defect: Any, names: set[str]) -> bool:
    text = " ".join(str(getattr(defect, field, "") or "") for field in
                    ("description", "reproduction_steps", "actual_behavior")) + " " + " ".join(
        str(f) for f in getattr(defect, "affected_files", None) or [])
    return any(re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", text) for name in names)


def _the_harness_s_own(defect: Any) -> bool:
    """Whether `defect` is one the harness raised about the unit tests itself: the unit run's, or a unit regression."""
    from app.graph.workflow import _A_REGRESSED_TEST, UNIT_TESTS_FAIL

    description = str(getattr(defect, "description", "") or "")
    regressed = _A_REGRESSED_TEST.match(description)
    return description.startswith(UNIT_TESTS_FAIL) or bool(regressed and regressed.group(1).startswith("unit: "))


def carried(
    defects: Sequence[Any], output: str, failing: Sequence[str], raise_own: Callable[[], Any] | None = None,
    others: Sequence[Any] = (),
) -> list[Any]:
    """`defects` with the unit run's grouped causes carried to those about its failing tests; when none is, with the
    harness's own unit-test defect (`raise_own()`) added - unless one the harness raised about the unit tests is among
    them or `others` (the round's review defects). `defects` as they are when the run states no cause."""
    from app import ci

    if any(_the_harness_s_own(d) for d in [*(defects or ()), *(others or ())]):
        # The harness's own word on the unit tests is already there, with its evidence.
        return list(defects or ())
    causes = ci.the_distinct_causes(str(output or ""))
    if not causes:
        from app.graph.workflow import _what_the_failure_says

        causes = _what_the_failure_says(str(output or ""))
    names = _what_names_them(failing)
    result, any_carried = [], False
    for defect in defects or ():
        if causes and names and _names_them(defect, names) and HEADING not in str(getattr(defect, "actual_behavior", "")):
            try:
                defect = defect.model_copy(update={
                    "actual_behavior": f"{getattr(defect, 'actual_behavior', '') or ''}\n\n{HEADING}\n{causes}".strip()})
                any_carried = True
            except Exception:  # noqa: BLE001 - the defect stands as the round wrote it
                pass
        result.append(defect)
    if not any_carried and raise_own is not None:
        own = raise_own()
        if own is not None:
            result.append(own)
    return result


__all__ = ["HEADING", "carried"]
