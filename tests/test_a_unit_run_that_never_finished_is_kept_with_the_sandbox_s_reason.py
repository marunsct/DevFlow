"""A unit run held to its time limit is kept with the sandbox's reason, so the test round does not say "(no output)".

Measured on one browser-and-service run: a unit test blocked its own thread, `npm test` ran to the time limit, a
snapshot kept that run with no output, and the test round read the kept run: three rounds of defects said the runner's
output ended "(no output)" and no fixer learned that the command never finished.
"""
from __future__ import annotations

from app import ci
from app.stacks import contract, pack_named


def test_the_kept_run_says_the_command_timed_out(tmp_path, monkeypatch):
    monkeypatch.setenv("MEASURE_ONCE", "on")
    pack = pack_named("node-http-api")
    contract.write(tmp_path, pack, "svc", "Svc")
    reason = "Command timed out after 300 seconds. A command that does not finish is usually one that was not meant to."

    def runner(command, kind, project):
        return {"error": reason}

    try:
        ci._run_unit(tmp_path, runner)
    except ci.NotMeasured:
        pass
    command = list((contract.read(tmp_path) or {}).get("unit_test") or pack.unit_test)

    kept = ci.the_unit_run_kept(tmp_path, command)

    assert kept is not None and "timed out after 300 seconds" in str(kept.get("output"))
