"""A rusqlite pragma run through `execute` is kept out of the design and explained when it fails.

Measured on a Rust axum run on rusqlite 0.40.2: the specification decided `conn.execute("PRAGMA journal_mode=WAL", [])`;
`PRAGMA journal_mode=WAL` answers a row, which rusqlite's `execute` refuses, so every request was answered 503
"database initialization failed: sqlite error: Execute returned results - did you mean to call query?" and all nine
hidden tests failed. A builder that read the error reached for a `batch_execute` rusqlite does not have.
"""
from __future__ import annotations

import re

from app.agents.shared_facts import what_the_setup_decides
from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: What the harness's smoke and the server's log said on that run, as the fixer was shown it.
THE_SMOKE_SAID = (
    "`POST /notes` answered 503 - it said: database initialization failed: io error: File exists (os error 17).\n"
    "What the server printed while the smoke ran:\n"
    "[WebServer]     Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.03s\n"
    "[WebServer] Failed to initialize database: sqlite error: Execute returned results - did you mean to call query?"
)


def _defect(actual: str) -> ReportedDefect:
    return ReportedDefect(description="The product's foundation does not hold: `POST /notes` answered 503",
                          severity="major", reproduction_steps="npm run test:acceptance",
                          expected_behavior="a note is made", actual_behavior=actual,
                          affected_files=["notes-api/src/db.rs"], owner="backend")


def _told(tmp_path, actual: str) -> str:
    contract.write(tmp_path, pack_named("rust-axum-api"), "notes-api", "Notes")
    (defect,) = with_known_causes(tmp_path, [_defect(actual)])
    return defect.actual_behavior


def test_the_run_time_error_of_a_pragma_run_through_execute_is_given_its_cause(tmp_path):
    told = _told(tmp_path, THE_SMOKE_SAID)

    assert KNOWN_CAUSE in told
    assert "`conn.pragma_update(None, \"journal_mode\", \"WAL\")?`" in told
    assert "`conn.busy_timeout(std::time::Duration::from_secs(5))?`" in told
    assert not BANNED.search(told)


def test_a_batch_execute_that_does_not_exist_is_given_rusqlite_s_name(tmp_path):
    told = _told(tmp_path, "error[E0599]: no method named `batch_execute` found for struct `Connection` in the current "
                           "scope")

    assert KNOWN_CAUSE in told and "`execute_batch`" in told
    assert not BANNED.search(told)


def test_the_specification_is_told_how_a_rusqlite_pragma_is_set():
    """The design stages decided the `execute` form; they read the setup's facts, not the builders' guide."""
    lines = "\n".join(what_the_setup_decides(pack_named("rust-axum-api"), "notes-api", "notes_api"))

    fact = next(line for line in lines.splitlines() if "rusqlite" in line)
    assert "`conn.pragma_update(None, \"journal_mode\", \"WAL\")?`" in fact
    assert "never `conn.execute(\"PRAGMA ...\")`" in fact
    assert not BANNED.search(fact)


def test_a_rust_builder_is_told_how_a_rusqlite_pragma_is_set():
    guide = " ".join(pack_named("rust-axum-api").guide.split())

    assert "`conn.pragma_update(None, \"journal_mode\", \"WAL\")?`" in guide
    assert "never `conn.execute(\"PRAGMA ...\")`" in guide
    assert not BANNED.search(guide)
