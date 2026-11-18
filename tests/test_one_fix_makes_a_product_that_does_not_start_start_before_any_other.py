"""While the product does not build or start, one fix with every reason why is sent, not one per failing criterion.

Deep review 2026-11-18, item 1.5. Measured on two runs: fix rounds sent many per-defect fixers - up to 13 in one round
- at a product that did not start, each failing the same way, and reverts piled up ("the product no longer builds or
starts" three and five times). Beside the one start defect went each compiler finding, a failed install and every
open defect of earlier rounds, each to a fixer of its own.
"""

from __future__ import annotations

import re

import the_fix_stage

from app.agents.specialists import ReportedDefect
from app.graph import start_first
from app.graph.acceptance_nodes import THE_PRODUCT_DOES_NOT_START

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _reported(description, kind="", source="", files=(), actual="it fails", evidence=()):
    return ReportedDefect(description=description, severity="major", reproduction_steps="r", expected_behavior="e",
                          actual_behavior=actual, affected_files=list(files), owner="backend", kind=kind,
                          source=source, evidence=list(evidence))


def _the_start(actual="error[E0425]: cannot find value `pool`"):
    return _reported(THE_PRODUCT_DOES_NOT_START, kind="start_failure", actual=actual,
                     evidence=[{"error": "error[E0425]: cannot find value `pool`"}])


def test_what_says_why_it_does_not_start_goes_to_the_one_start_defect():
    reported = [
        _the_start(),
        _reported("src/db.rs line 4: cannot find value `pool`", kind="compile_error", source="language service",
                  files=["src/db.rs"], actual="cannot find value `pool` in this scope",
                  evidence=[{"file": "src/db.rs", "code": "E0425"}]),
        _reported("src/routes.rs line 9: unresolved import `crate::db::Pool`", kind="compile_error",
                  source="language service", files=["src/routes.rs"]),
        _reported(f"{start_first.DEPENDENCIES_DO_NOT_INSTALL}, so nothing its manifests declare is there: x",
                  files=["Cargo.toml"]),
        _reported("[AC-3] A note can be read - the acceptance suite says this does not work yet.", kind="failing_test"),
    ]

    after = start_first.folded(reported)

    assert [d.description for d in after] == [
        THE_PRODUCT_DOES_NOT_START,
        "[AC-3] A note can be read - the acceptance suite says this does not work yet.",
    ]
    start = after[0]
    assert "src/db.rs line 4" in start.actual_behavior and "unresolved import" in start.actual_behavior
    assert start_first.DEPENDENCIES_DO_NOT_INSTALL in start.actual_behavior
    assert set(start.affected_files) == {"src/db.rs", "src/routes.rs", "Cargo.toml"}
    assert {"file": "src/db.rs", "code": "E0425"} in start.evidence and start.severity == "blocking"


def test_a_product_that_starts_keeps_its_findings_apart():
    reported = [_reported("src/db.rs line 4: x", kind="compile_error", source="language service", files=["src/db.rs"]),
                _reported("[AC-3] y", kind="failing_test")]

    assert start_first.folded(reported) == reported
    assert start_first.held_back(reported) == set()


def test_a_merge_led_by_the_compiler_s_finding_is_still_the_start_failure():
    from app.sprint import cause

    lead = _reported("src/db.rs line 4: x", kind="compile_error", evidence=[{"file": "src/db.rs", "code": "E0425"}])

    assert cause.as_merged(lead, [_the_start()])["kind"] == "start_failure"


def _a_cycle(root, *, start_at):
    criteria = [the_fix_stage.a_defect(f"[AC-{n}] criterion {n} fails", affected_files=[f"app/part{n}.js"],
                                       kind="failing_test") for n in range(1, 6)]
    start = the_fix_stage.a_defect(THE_PRODUCT_DOES_NOT_START, affected_files=[], kind="start_failure")
    defects = [*criteria[:start_at], start, *criteria[start_at:]]
    return the_fix_stage.a_state(root, *defects)


def test_side_by_side_fixing_sends_only_the_start_fix_while_the_product_does_not_start(tmp_path):
    update, seen = the_fix_stage.run(tmp_path, _a_cycle(tmp_path, start_at=2), side_by_side=True)

    assert not update.get("fix_batch"), "no batch of fixers at a product that does not start"
    assert [stage for stage, _ in seen.shown] == ["defect_fix_2_2"]


def test_one_at_a_time_the_start_fix_goes_first_and_the_criteria_wait(tmp_path):
    update, seen = the_fix_stage.run(tmp_path, _a_cycle(tmp_path, start_at=3))

    assert [stage for stage, _ in seen.shown] == ["defect_fix_2_3"]


def test_the_folded_text_holds_no_product_words():
    assert not BANNED.search(start_first.ALSO_WHILE_IT_DOES_NOT_START)
