"""Candidate fixes for a stuck defect, kept only when they also hold the regression set (plan PF.2, behind
`CANDIDATE_FIXES_WHEN_STUCK`).

After a failed fix the harness already asks for several one-call rewrites of the defect's files at once and keeps the
first its own tests pass (`rewritten_fixes.fix_by_candidates`, Agentless's repair and validation). Two things made that
the expensive path for a defect that keeps failing: the fix rate at a third attempt of one cause was 11%
(`docs/improvement-plan.md`), and the candidate kept was the first whose own tests passed - measured against the whole
suite only after, and reverted when it broke a test that passed, with the other candidates already thrown away.

With the switch on, from a defect's second failed attempt:

- **as many candidates as the model server has room for now**, at most `MOST_CANDIDATES`: the slots the server serves
  at once (`workflow.concurrent_requests`) less the model calls in flight on it (`call_gate.in_flight`), each candidate
  taking one call per file; fewer than `LEAST_CANDIDATES` fit and the harness asks as before;
- **each with its own seed** where the server takes one (an OpenAI-compatible self-hosted server), so the candidates
  differ by more than the server's sampling;
- **each kept only when it passes the defect's own tests and the regression set**: written into the workspace from
  the same starting point, measured, and its files put back before the next (`holds`); the first that passes both is
  the attempt's answer, measured once more as every fix is;
- **one whose own tests pass and that broke tests that passed before is not lost**: it is kept as a candidate for the
  defect (`kept_fix_candidates.keep_from_the_tree`), replayed at its next attempt as a reverted fix is.

A transcript record (`RECORD_KIND`) says, per stuck attempt, how many candidates were asked and how each was judged;
`loop.sh effects` reads it (`effects_lines`). Nothing here names a language, a framework or a runner. Never raises.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from app.switches import is_on

logger = logging.getLogger(__name__)

NAME = "CANDIDATE_FIXES_WHEN_STUCK"
#: `CANDIDATE_FIXES_WHEN_STUCK` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Failed attempts of a defect before its candidates are sized to the server and held to the regression set.
STUCK_AFTER = 2
#: Candidates asked at once, at most and at least (one alone is the serial path it replaces).
MOST_CANDIDATES = 3
LEAST_CANDIDATES = 2
#: The transcript record of one stuck attempt's candidates.
RECORD_KIND = "candidate_fixes"
SAID = "Candidate fixes for a stuck defect, each measured against its own tests and the regression set"


def enabled() -> bool:
    return is_on(NAME, ON_BY_DEFAULT)


def idle_slots() -> int:
    """The model server's requests it can serve at once less the model calls in flight on it now; 0 when unknown."""
    try:
        from app.graph.workflow import concurrent_requests
        from app.models.call_gate import in_flight

        return max(0, concurrent_requests() - len(in_flight()))
    except Exception:  # noqa: BLE001 - no room known is no room
        return 0


def width(failed_tries: int, files: Iterable[str] | None, idle: int | None = None) -> int:
    """How many candidate fixes a stuck defect is given now: 0 when the switch is off, the defect has failed fewer
    than `STUCK_AFTER` times, or fewer than `LEAST_CANDIDATES` fit in the idle slots (`idle`, else `idle_slots`)."""
    if not enabled() or failed_tries < STUCK_AFTER:
        return 0
    calls_each = max(1, len(list(files or ())))
    room = idle_slots() if idle is None else idle
    count = min(MOST_CANDIDATES, room // calls_each)
    return count if count >= LEAST_CANDIDATES else 0


def seed_for(model: Any, seed: int) -> dict[str, Any]:
    """`{"seed": seed}` for a model served by a self-hosted OpenAI-compatible server, which takes one; else {}: a
    hosted API refuses a field it does not know."""
    try:
        from app.models import CompatibleChatOpenAI

        return {"seed": int(seed)} if isinstance(model, CompatibleChatOpenAI) else {}
    except Exception:  # noqa: BLE001 - no seed
        return {}


def lost_now(root: str | Path, label: str) -> list[str] | None:
    """The tests that passed at the last measurement and do not pass now, measuring the whole suite as a fix is
    measured (`ci.take`); a product that started before and does not now counts; None when it could not be measured."""
    from app import ci

    before = ci.load(root, "latest")
    after = ci.take(root, label)
    if getattr(after, "unmeasured", ""):
        return None
    lost = ci.regressions(before, after)
    if after.problem and before is not None and not before.problem:
        lost = [f"the product no longer builds or starts ({str(after.problem)[:300]})", *lost]
    return lost


class Stuck:
    """One stuck attempt's candidates: `holds` judges each against the regression set, `note` records them all."""

    def __init__(self, root: str | Path, defect: Any, stage: str, count: int, measure: Any = None) -> None:
        self.root, self.defect, self.stage, self.count = Path(root), defect, stage, count
        self.measure = measure or (lambda: lost_now(self.root, f"a candidate fix of {stage}"))
        self.judged: list[str] = []

    def holds(self, changed: list[str]) -> bool:
        """Whether the candidate now in the workspace, whose own tests pass, broke nothing that passed before; one
        that broke tests is kept for the defect's next attempt. A suite that cannot be measured holds."""
        try:
            lost = self.measure()
        except Exception as error:  # noqa: BLE001 - measured again as every fix is
            from app.observability.degraded import degraded

            degraded("candidate_fixes_when_stuck.holds", error)
            lost = None
        if not lost:
            self.judged.append("kept: its own tests and the regression set pass" if lost is not None
                               else "kept: its own tests pass; the regression set could not be measured")
            return True
        from app.graph import kept_fix_candidates

        kept = kept_fix_candidates.keep_from_the_tree(self.root, self.defect, self.stage, changed, lost)
        self.judged.append(f"broke {len(lost)} test(s) that passed before ({'; '.join(lost[:3])[:300]})"
                           + ("; kept for the next attempt" if kept else ""))
        return False

    def note(self, answered: bool) -> None:
        """One transcript record of this attempt's candidates. Never raises."""
        try:
            from app.observability.transcript import _run_id_from_config, record

            record(_run_id_from_config(), self.stage, RECORD_KIND, message=SAID, candidates=self.count,
                   judged=self.judged, kept=bool(answered))
        except Exception:  # noqa: BLE001 - the attempt goes on unrecorded
            logger.debug("Could not record a stuck defect's candidate fixes", exc_info=True)


def effects_lines(records: Iterable[Any]) -> list[str]:
    """`loop.sh effects` (PF.2): stuck attempts given candidates, candidates asked, those kept, those that broke the
    regression set and so were not kept."""
    seen = [r for r in records if isinstance(r, dict) and r.get("kind") == RECORD_KIND]
    head = "PF.2 stuck defects given candidate fixes held to the regression set"
    if not seen:
        return [f"     -  {head}: not reached"]
    asked = sum(int(r.get("candidates") or 0) for r in seen)
    answered = sum(1 for r in seen if r.get("kept"))
    judged = [str(j) for r in seen for j in (r.get("judged") or [])]
    broke = sum(1 for j in judged if j.startswith("broke "))
    return [f"  {len(seen):>4}  {head} ({asked} candidates asked; {answered} attempts answered by one; "
            f"{broke} passed their own tests and broke the regression set)"]


__all__ = ["LEAST_CANDIDATES", "MOST_CANDIDATES", "NAME", "ON_BY_DEFAULT", "RECORD_KIND", "SAID", "STUCK_AFTER",
           "Stuck", "effects_lines", "enabled", "idle_slots", "lost_now", "seed_for", "width"]
