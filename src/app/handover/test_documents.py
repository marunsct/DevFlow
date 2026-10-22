"""The unit-test and acceptance-test documents, written by the harness from the run's facts (plan DT.6).

No model writes a word of them: every row is a test or a criterion the harness
measured (`facts.document_facts`), so a document can never claim a test that
did not run. Markdown, so any later template stage (DT.3, DT.4) renders from
the same text.
"""

from __future__ import annotations

from typing import Any


def _cell(text: Any, most: int = 200) -> str:
    return " ".join(str(text or "").split()).replace("|", "/")[:most]


def _heading(facts: dict[str, Any], title: str) -> list[str]:
    return [
        f"# {title}: {facts.get('product') or facts.get('project') or 'the product'}",
        "",
        f"Run `{facts.get('run_id') or 'unknown'}`, commit `{(facts.get('commit') or 'unknown')[:12]}`, "
        f"stack pack `{facts.get('pack') or 'none'}`. Written by the harness from what it measured.",
        "",
    ]


def unit_test_document(facts: dict[str, Any]) -> str:
    """Each unit test with its file, outcome, duration and failure message, and the command it ran under."""
    tests = facts.get("unit_tests") or []
    passed = sum(1 for t in tests if t.get("outcome") == "passed")
    failed = sum(1 for t in tests if t.get("outcome") == "failed")
    skipped = len(tests) - passed - failed
    lines = _heading(facts, "Unit test report")
    lines += [f"Command: `{facts.get('unit_command') or 'not recorded'}`.", "",
              f"{len(tests)} tests: {passed} passed, {failed} failed, {skipped} skipped.", ""]
    if not tests:
        lines.append("The run recorded no unit test report.")
        return "\n".join(lines) + "\n"
    lines += ["| Test | File | Outcome | Seconds | Failure |", "| --- | --- | --- | --- | --- |"]
    for t in sorted(tests, key=lambda t: (t.get("outcome") == "passed", str(t.get("file")), str(t.get("name")))):
        lines.append(f"| {_cell(t.get('name'), 120)} | {_cell(t.get('file'), 80)} | {t.get('outcome')} | "
                     f"{t.get('seconds')} | {_cell(t.get('message'))} |")
    return "\n".join(lines) + "\n"


def acceptance_test_document(facts: dict[str, Any]) -> str:
    """Each criterion with its interface line, its tests and their outcomes, the suite's totals and what shipped unproven."""
    criteria = facts.get("criteria") or []
    totals = facts.get("acceptance") or {}
    lines = _heading(facts, "Acceptance test report")
    lines += [
        f"Command: `{facts.get('acceptance_command') or 'not recorded'}`.", "",
        f"{len(criteria)} criteria: {sum(1 for c in criteria if c.get('status') == 'passed')} passed, "
        f"{sum(1 for c in criteria if c.get('status') == 'failed')} failed, "
        f"{sum(1 for c in criteria if c.get('deferred'))} deferred. Tests: {totals.get('passed', 0)} passed, "
        f"{totals.get('failed', 0)} failed, {totals.get('skipped', 0)} skipped.", "",
        "| Criterion | Status | Interface | Tests |", "| --- | --- | --- | --- |",
    ]
    for c in criteria:
        tests = "; ".join(f"{_cell(t.get('name'), 80)} ({t.get('outcome')})" for t in c.get("tests") or []) or "no test carries it"
        status = c.get("status") + (f" - deferred: {_cell(c.get('deferred'), 120)}" if c.get("deferred") else "")
        lines.append(f"| {c.get('id')}: {_cell(c.get('text'), 140)} | {status} | {_cell('; '.join(c.get('contract') or []), 140) or '-'} | {tests} |")
    failing = [(c, t) for c in criteria for t in c.get("tests") or [] if t.get("outcome") != "passed" and t.get("message")]
    if failing:
        lines += ["", "## What failed", ""]
        lines += [f"- {c.get('id')} `{_cell(t.get('name'), 80)}`: {_cell(t.get('message'), 400)}" for c, t in failing[:30]]
    gaps = facts.get("completion_gaps") or []
    if gaps:
        lines += ["", "## Shipped with these gaps", ""] + [f"- {_cell(g, 400)}" for g in gaps]
    return "\n".join(lines) + "\n"


__all__ = ["acceptance_test_document", "unit_test_document"]
