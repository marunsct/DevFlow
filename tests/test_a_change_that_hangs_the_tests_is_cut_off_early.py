"""A run of the unit tests with a deliberate change in place is held to a small multiple of the unchanged run.

Measured on one C# run: a mutation finding's check made the unit tests never return, and each check waited out the
whole 10-minute test limit - three checks, about 30 minutes, after the product already passed every criterion.
Mutation tools count a timed-out mutant as noticed; here the tests that hang are cut off at three times the unchanged
run (at least a minute) and the change counts as noticed, as before, only sooner.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import mutation_guided
from app.tools import sandbox


def test_the_cap_holds_every_command_inside_it_and_none_outside():
    full = sandbox.timeout_for("test")
    with sandbox.capped(45):
        assert sandbox.timeout_for("test") == min(45, full)
    assert sandbox.timeout_for("test") == full


def test_a_finding_s_check_runs_the_change_under_the_cap(tmp_path, monkeypatch):
    (tmp_path / "calc.py").write_text("def ok(a, b):\n    return a or b\n")
    seen = []

    def run_unit():
        seen.append(sandbox._A_CAP.get())  # noqa: SLF001
        return {"test_ok"} if len(seen) != 2 else set()

    monkeypatch.setattr(mutation_guided, "site_of", lambda d: {"file": "calc.py", "line": 2, "column": 14,
                                                               "original": "or", "replacement": "and"})
    monkeypatch.setattr(mutation_guided, "_located", lambda root, site: site)

    settled = mutation_guided.settled(tmp_path, SimpleNamespace(), run_unit=run_unit)

    assert settled is True
    assert seen[0] is None and seen[1] == mutation_guided.MOST_SECONDS_FOR_A_CHANGE_FLOOR and seen[2] is None
    assert (tmp_path / "calc.py").read_text() == "def ok(a, b):\n    return a or b\n"
