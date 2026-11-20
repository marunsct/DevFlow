"""Open mutation findings in the file being fixed go to that one fixer, each settled by the harness after it (behind `MUTATION_GAPS_BUNDLED`).

A mutation finding (`app.acceptance.mutation_guided`) asks the testing role for
a unit test that notices one deliberate change. Bundling (`_bundle_co_defects`)
joins only kinds a measurement can close and only defects that share a named
file; a finding names none, so each went to its own fix stage. Measured: three
findings in one file, a comparison flipped on three lines, went to three fixers
one after another - 38 model calls, about 15 minutes, after the product had
passed every criterion; another run spent about 30 minutes the same way.

With the switch on, a finding's fixer is also handed the other open findings
of the same owner in the same file, at most `MOST_BUNDLED_DEFECTS`, each with
its line, the change and what settles it. After the fix the harness checks each
bundled finding itself (`mutation_guided.settled`: the change made, the unit
tests run, the line put back): one the tests now notice is closed with no fixer
of its own; one they do not stays open for its own fixer. None is closed on the
strength of the first finding's answer. Off, every finding is fixed alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.acceptance import mutation_guided
from app.switches import is_on

#: `MUTATION_GAPS_BUNDLED` set to on or off overrides this.
ON_BY_DEFAULT = False
#: The heading a fix request carries when it bundles findings (`switch_firing.SIGNALS`).
SAYS = "to settle in this same fix"


def enabled() -> bool:
    return is_on("MUTATION_GAPS_BUNDLED", ON_BY_DEFAULT)


def bundled_with(cycle: Any, defect_index: int, most: int) -> list[tuple[int, Any]]:
    """The open findings after this one, of its owner and in its file, at most `most`; [] when off or not a finding."""
    if not enabled():
        return []
    defect = cycle.defects[defect_index]
    site = mutation_guided.site_of(defect) if mutation_guided.is_a_finding(defect) else None
    if site is None:
        return []
    found: list[tuple[int, Any]] = []
    for pos, other in enumerate(cycle.defects[defect_index + 1:], start=defect_index + 1):
        if other.status != "open" or other.owner != defect.owner or not mutation_guided.is_a_finding(other):
            continue
        where = mutation_guided.site_of(other)
        if where is not None and where["file"] == site["file"]:
            found.append((pos, other))
    return found[:max(0, most)]


def not_bundled(defects: Any, co_defects: list[tuple[int, Any]]) -> list[Any]:
    """`defects` without the bundled ones, which the bundled section lists in full."""
    bundled = [d for _, d in co_defects]
    return [d for d in defects or () if all(d is not b for b in bundled)]


def section(co_defects: list[tuple[int, Any]]) -> str:
    """The bundled findings as the fixer is shown them; "" when none of `co_defects` is a finding."""
    lines = []
    for pos, other in co_defects:
        site = mutation_guided.site_of(other) if mutation_guided.is_a_finding(other) else None
        if site is None:
            continue
        lines.append(
            f"- Finding {pos + 1}: `{site['file']}` line {site['line']}, column {site['column']}: "
            f"`{site['original']}` made `{site['replacement']}`."
            + (f" The line reads: {site['text'].strip()}" if site.get("text", "").strip() else "")
        )
        lines.append(
            f"  Settled when a unit test fails with `{site['replacement']}` there and passes with `{site['original']}`."
        )
    if not lines:
        return ""
    return (
        f"\n--- The other changes no test notices in the same file, {SAYS} ---\n" + "\n".join(lines) + "\n"
        "Write a test for each change listed here as well as for your own finding, before you answer. After your fix "
        "the harness makes each change itself and runs the unit tests: each one they notice is settled with no fix "
        "of its own, and one they do not notice goes to its own fix.\n"
    )


class Bundled:
    """The findings bundled with one fix, each checked by the harness at most once (`mutation_guided.settled`)."""

    def __init__(self, root: str | Path, co_defects: list[tuple[int, Any]]) -> None:
        self.root = root
        self.open = [
            (pos, d) for pos, d in co_defects
            if getattr(d, "status", "open") == "open" and mutation_guided.is_a_finding(d)
        ]
        self._answers: dict[int, bool | None] = {}

    def answer(self, pos: int, defect: Any) -> bool | None:
        if pos not in self._answers:
            self._answers[pos] = mutation_guided.settled(self.root, defect)
        return self._answers[pos]

    def any_settled(self) -> bool:
        """Whether the unit tests now notice any bundled change: the fix's tests are then not tests that notice nothing."""
        return any(self.answer(pos, d) is True for pos, d in self.open)

    def closed(self, cycle: Any, *, stage_name: str, round_: int, sprint: int, put_back: str = "") -> Any:
        """`cycle` with each bundled finding the unit tests now notice marked fixed; the others left open. Never raises.

        None is checked when the fix's test files were put back (`put_back`): what would have settled them is gone.
        """
        from app.observability import defect_ledger
        from app.sprint import mark_defect_fixed

        for pos, other in self.open:
            where = {"round_": round_, "index": pos, "sprint": sprint}
            try:
                if not put_back and self.answer(pos, other) is True:
                    detail = ("the unit tests fail with the change and pass without it, measured by the harness after "
                              "the fix it was bundled with")
                    defect_ledger.note("closed without a fixer", stage_name, defect=other, detail=detail, **where)
                    cycle = mark_defect_fixed(
                        cycle, pos,
                        regression_test="the unit tests, which fail with the change and pass without it",
                        verified_by="the harness's mutation check",
                        resolution=f"Settled by {stage_name}, which it was bundled with: " + detail + ".",
                    )
                    continue
                defect_ledger.note(
                    "left open", stage_name, defect=other, **where,
                    detail=("bundled, but " + (f"the fix's tests were put back ({put_back})" if put_back else
                            "the unit tests do not notice its change after the fix") + "; it goes to its own fix"),
                )
            except Exception:  # noqa: BLE001 - left open, it goes to its own fixer
                continue
        return cycle


__all__ = ["Bundled", "ON_BY_DEFAULT", "SAYS", "bundled_with", "enabled", "not_bundled", "section"]
