"""The cross-file check skips a framework's build output, and one round raises at most a few of its proven problems.

Measured on one Next.js run: the check read `.next/server/`'s generated pages and route cache, proved 138 and then 151
"references a file that does not exist" problems in one round, each became a fixer of its own, and the run ended with
"Recursion limit of 100 reached" in the middle of the batch.
"""
from __future__ import annotations

from app.agents.specialists import ReportedDefect
from app.analysis import integration_checks
from app.graph.nodes import triage


def test_a_next_build_folder_is_not_read(tmp_path):
    (tmp_path / ".next" / "server" / "app").mkdir(parents=True)
    (tmp_path / ".next" / "server" / "app" / "cart.html").write_text('<script src="/_next/static/chunks/x.js"></script>')
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "page.tsx").write_text("export default function Page() { return null }")

    read = [p.relative_to(tmp_path).as_posix() for p in integration_checks._source_files(tmp_path)]

    assert "app/page.tsx" in read and not any(r.startswith(".next/") for r in read)


def _defect(n: int) -> ReportedDefect:
    return ReportedDefect(description=f"page{n}.html references `/x{n}.js`, which does not exist in the workspace.",
                          severity="major", reproduction_steps="read it", expected_behavior="it exists",
                          actual_behavior="missing", affected_files=[], owner="testing")


def test_a_flood_of_proven_problems_is_bundled_into_a_few_defects():
    bundled = triage.at_most([_defect(n) for n in range(138)], triage.MOST_PROVEN_PER_ROUND)

    assert len(bundled) == triage.MOST_PROVEN_PER_ROUND
    assert "and 128 more of the same check" in bundled[-1].description


def test_a_few_proven_problems_are_left_as_they_are():
    few = [_defect(n) for n in range(3)]

    assert triage.at_most(few, triage.MOST_PROVEN_PER_ROUND) == few
