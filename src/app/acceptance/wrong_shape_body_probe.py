"""A write sent valid JSON that is not an object must not make the server fail (behind `WRONG_SHAPE_BODY_PROBE`).

Measured: products answered 500 to a JSON string sent as a write's body - the parser took it, and the handler read
fields off a string. The bad-body probe sends bytes no parser can read, so it never reached the handler. When a test
round finds the locked suite green, each `POST`, `PUT` and `PATCH` line of the contract (the bad-body probe's, with a
record made first where the route has a parameter) is sent each of `SHAPES` as raw bytes with the JSON content type;
any answer under 500 passes, the refusal being the product's to choose. A 5xx joins the contract's server-error
defect, worded with `SAID`.

A quality probe that starts the product once more per green round, so a switch until measured.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: The words its defect gives, which the audit's switch-firing check reads; `still_raised` reads them back.
SAID = "sent a JSON body that is not an object"

#: The bodies sent, each as the bytes written here: a JSON string, and an array.
SHAPES = ('"text"', "[]")

#: Which check and which shape a test of the probe is: `contract 3:` in its title.
_CHECK_NUMBER = re.compile(r"\bcontract (\d+):")


def enabled() -> bool:
    return is_on("WRONG_SHAPE_BODY_PROBE", ON_BY_DEFAULT)


def _title(number: int, check: Any, shape: str) -> str:
    return f"{f'[{check.criterion}] ' if check.criterion else ''}contract {number}: {check.line} with {shape}"


def playwright_wrong_shape_checks(asked: list[Any], bodies: list[Any] | None = None) -> str:
    """A Playwright spec with one test per write and shape, numbered check by check and shape by shape.

    Each shape goes as bytes (`Buffer.from`): Playwright JSON-encodes a string `data`, which would send `"\\"text\\""`.
    """
    from app.acceptance import interface_contract as ic

    marker = f"data: Buffer.from({ic._js(ic.A_BODY_NOTHING_CAN_PARSE)}), "  # noqa: SLF001
    tests = []
    for index, check in enumerate(asked):
        for offset, shape in enumerate(SHAPES):
            number = index * len(SHAPES) + offset + 1
            text = ic._a_bad_body_test(ic._js(_title(number, check, shape)), check)  # noqa: SLF001
            assert marker in text
            tests.append(text.replace(marker, f"data: Buffer.from({ic._js(shape)}), "))  # noqa: SLF001
    return ic._with_sign_in_js("import { test, expect } from '@playwright/test';\n\n" + "\n".join(tests),  # noqa: SLF001
                               ic.sign_in_plan(asked, bodies))


def pytest_wrong_shape_checks(asked: list[Any], bodies: list[Any] | None = None) -> str:
    """A pytest module with one case per write and shape; each shape is sent as the bytes written in `SHAPES`."""
    from app.acceptance import interface_contract as ic

    cases = []
    for index, check in enumerate(asked):
        for offset, shape in enumerate(SHAPES):
            number = index * len(SHAPES) + offset + 1
            # A string `send` is sent as its own bytes by the probe's `_call`, not encoded again.
            cases.append(ic._pytest_case(number, check, f" with {shape}", rule="under_500", send=shape))  # noqa: SLF001
    return ic._pytest_module(cases, ic.sign_in_plan(asked, bodies))  # noqa: SLF001


RUNNERS = {"playwright": playwright_wrong_shape_checks, "pytest": pytest_wrong_shape_checks}


def _the_case_of(test: Any, asked: list[Any]) -> tuple[Any, str] | None:
    """(the check, the shape) a test of the probe is, by `contract N:` in its title; None when it names none."""
    number = _CHECK_NUMBER.search(str(getattr(test, "name", "") or ""))
    if not number or not 0 < int(number.group(1)) <= len(asked) * len(SHAPES):
        return None
    index = int(number.group(1)) - 1
    return asked[index // len(SHAPES)], SHAPES[index % len(SHAPES)]


def wrong_shape_errors(repo_root: str | Path, *, runner: Any = None) -> list[tuple[Any, int, str]] | None:
    """Each write call of the locked contract that answers a 5xx to a JSON body that is not an object: (check, status, shape).

    None when off or when the checks cannot run.
    """
    if not enabled():
        return None
    try:
        from functools import partial

        from app.acceptance import interface_contract as ic
        from app.acceptance import probe_coverage, suite
        from app.stacks import contract

        root = Path(repo_root)
        bodies = ic.bodies_for_the_probes(root)
        lines = ic.the_locked_contract(root)[:ic.MOST_CHECKS]
        asked, unchecked = ic.bad_body_checks(lines, bodies)
        found = contract.the_pack(root)
        name = found[0].probe_runner if found else ""
        probe = ic.PROBE_RUNNERS.get(name)
        not_asked = [(u.rsplit(" (", 1)[0], u.rsplit(" (", 1)[-1].rstrip(")")) for u in unchecked]
        if probe is None or name not in RUNNERS or not asked:
            if lines:
                probe_coverage.write(root, "wrong_shape_body", probe_coverage.coverage(
                    considered=len(lines), asked=[],
                    not_asked=not_asked + [(c.line, "no runner on this stack probes it") for c in asked]))
            return None
        project_name = str((found[1] or {}).get("project") or "")
        run = runner or suite._sandbox_runner(root)  # noqa: SLF001 - the suite's own runner
        compiled = {**probe, "wrong_shape_checks": partial(RUNNERS[name], bodies=bodies)}
        report = ic._the_probe_s_report(root / project_name, project_name, compiled, asked, run,  # noqa: SLF001
                                        "wrong_shape_checks")
        found_report = report if report is not None and report.found else None
        # A line's coverage once, by its first shape's test: two tests a line would read "asked 6, probed 12".
        of_the_lines = None if found_report is None else SimpleNamespace(found=True, tests=[
            t for t in found_report.tests if (case := _the_case_of(t, asked)) is not None and case[1] == SHAPES[0]])
        probe_coverage.write(root, "wrong_shape_body", probe_coverage.coverage(
            considered=len(lines), asked=asked, report=of_the_lines, not_asked=not_asked,
            check_of=lambda test: (_the_case_of(test, asked) or (None, ""))[0]))
        if found_report is None:
            return None
        errors: list[tuple[Any, int, str]] = []
        for test in found_report.tests:
            case, status = _the_case_of(test, asked), ic._a_server_error(test)  # noqa: SLF001
            if case is not None and getattr(test, "outcome", "") == "failed" and status:
                errors.append((case[0], status, case[1]))
        return errors
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not probe the contract with a JSON body that is not an object", exc_info=True)
        return None


def described(wrong_shape: list[tuple[Any, int, str]]) -> list[str]:
    """Each call that failed, as the server-error defect names it: the call, `SAID`, the bodies and the status."""
    from app.acceptance import interface_contract as ic

    by_call: dict[str, list[tuple[str, int]]] = {}
    for check, status, shape in wrong_shape:
        by_call.setdefault(ic._the_call(check), []).append((shape, status))  # noqa: SLF001
    return [f"`{call}` {SAID} ({', '.join(f'`{shape}` answered {status}' for shape, status in sent)}) "
            "where a refusal under 500 was due"
            for call, sent in list(by_call.items())[:6]]


__all__ = ["ON_BY_DEFAULT", "RUNNERS", "SAID", "SHAPES", "described", "enabled", "playwright_wrong_shape_checks",
           "pytest_wrong_shape_checks", "wrong_shape_errors"]
