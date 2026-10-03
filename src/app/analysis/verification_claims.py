"""Check what a specialist says it ran against what actually ran.

`VerificationRun`'s own docstring has said, since it was written, that "a claim
here is checked against `read_execution_ledger`, which is what makes it
evidence rather than assertion". No such check existed. The field was collected,
stored, rendered into reports, and never once compared with the ledger sitting
beside it - so a specialist could name any command with any exit code and be
believed.

What that cost is visible in one run's final message to the human:

    - Defect (fixed): renderTasks test fails due to listEl not having children
      property in the mock environment. [owner: testing]
    - Defect (fixed): Syntax error in createElementFallback causing renderTasks
      failure and test assertions fail. [owner: security_reliability]
    - Defect (open): Test app.test.mjs fails due to renderTasks creating 0
      items despite valid tasks array. [owner: testing]

Three descriptions of one failure. `app.test.mjs` failed continuously from the
first test round to the last, and two of the three are reported as fixed,
because "fixed" meant "the specialist named a test" and nothing more. A report
that says fixed about something still failing is the same fault this codebase
has spent its time removing from every tool it owns: do not claim to have done
what was not done.

A comment describing a safeguard that is not there is worse than no comment,
because it stops the next reader looking.
"""

from __future__ import annotations

from typing import Any


def _argv_of(claim: Any) -> list[str]:
    command = getattr(claim, "command", None)
    if isinstance(command, str):
        return command.split()
    if isinstance(command, (list, tuple)):
        return [str(part) for part in command]
    return []


def proven_commands(repo_root: str, verification: Any) -> list[list[str]]:
    """The claimed commands the ledger confirms ran and exited zero.

    Matched on argv, not on the working directory: a specialist writes the
    command the way it ran it and the ledger records where, and requiring both
    to line up turns an honest claim into an unproven one over a `./` that was
    or was not typed.
    """
    from app.tools.sandbox import read_execution_ledger

    claims = [_argv_of(claim) for claim in (verification or [])]
    claims = [argv for argv in claims if argv]
    if not claims:
        return []
    try:
        entries = read_execution_ledger(repo_root, by_the_agents=True)
    except Exception:  # noqa: BLE001 - an unreadable ledger proves nothing
        return []
    passed = {
        tuple(str(part) for part in entry.get("command") or ())
        for entry in entries
        if str(entry.get("returncode", "")).strip() == "0"
    }
    return [argv for argv in claims if tuple(argv) in passed]


def why_this_fix_is_not_proven(repo_root: str, verification: Any) -> str:
    """Why this fix cannot be taken as verified, or "" when it can.

    Deliberately narrow. It asks one question - did any command this specialist
    says it ran actually run and exit zero? - because that is the question the
    ledger can answer exactly. It does not judge whether the right command was
    run, or whether the command proves the defect closed; a reviewer does that.
    """
    claims = [claim for claim in (verification or []) if _argv_of(claim)]
    if not claims:
        return (
            "no command was recorded in `verification`, so nothing was run to "
            "show the fix works"
        )
    if proven_commands(repo_root, claims):
        return ""
    listed = ", ".join(" ".join(_argv_of(claim)) for claim in claims[:3])
    return (
        f"none of the commands named in `verification` ({listed}) is recorded in "
        "this workspace's execution ledger as having run and exited 0"
    )


__all__ = ["proven_commands", "why_this_fix_is_not_proven"]
