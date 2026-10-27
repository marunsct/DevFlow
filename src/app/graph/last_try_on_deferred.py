"""One last try at each deferred criterion before release (deep review F3, behind `LAST_TRY_ON_DEFERRED`).

Measured over 19 runs: of 5 false acceptances, 4 shipped the failing behaviour as a deferred criterion - DELETE twice,
persistence, DELETE again. A criterion is deferred when the sprint's fixes and re-plans ran out on it, and nothing
looks at it again. Before release, each deferred criterion that has a locked test gets one single-call rewrite aimed
at it alone (`rewritten_fixes.fix_by_rewriting`, with the test's failure). The suite is measured again: the change is
kept, and the criterion no longer deferred, only when its tests pass and every test that passed before still passes;
otherwise its files are put back as they were.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False
#: Deferred criteria given a last try, at most.
MOST_CRITERIA = 3


def enabled() -> bool:
    return is_on("LAST_TRY_ON_DEFERRED", ON_BY_DEFAULT)


def _the_defect(criterion: str, text: str, reason: str, failures: list[str]) -> Any:
    from app.agents.specialists import ReportedDefect

    said = "\n".join(failures)[:1_500] or "its locked tests fail"
    return ReportedDefect(
        description=f"[{criterion}] {text} - the acceptance suite says this does not work yet. It was deferred "
                    f"({reason[:200]}); this is one last try before release.",
        severity="major",
        reproduction_steps=f"Run the acceptance suite and read the {criterion} tests.",
        expected_behavior=text,
        actual_behavior=said,
        affected_files=[],
        owner="backend",
    )


def try_them(
    root: str | Path, state: Any, *,
    run_suite: Callable[[], Any] | None = None,
    rewrite: Callable[[Any], Any] | None = None,
) -> list[str]:
    """The criteria a last try made pass and took out of the deferred list; [] when off or none. Never raises."""
    if not enabled():
        return []
    try:
        from app import ci
        from app.acceptance import junit, suite
        from app.acceptance.mutation import passing

        root = Path(root)
        deferred = suite.deferred(root)
        tested = {tag for _shown, name in suite.declared_tests(root) for tag in junit.tags_in(name)}
        texts = {criterion.id: criterion.text for criterion in suite.criteria(root)}
        chosen = [c for c in deferred if c in tested and c in texts][:MOST_CRITERIA]
        if not chosen:
            return []
        run_suite = run_suite or (lambda: suite.run(root, save=False))
        if rewrite is None:
            from app.graph.rewritten_fixes import fix_by_rewriting

            def rewrite(defect: Any) -> Any:
                return fix_by_rewriting(
                    defect, root, None, specification=state.get("technical_specification"),
                    stack=getattr(state.get("stack_selection"), "technology_stack", None),
                )
        before = run_suite()
        held = passing(before)
        made: list[str] = []
        for criterion in chosen:
            tests = [t for t in getattr(getattr(before, "report", None), "tests", None) or []
                     if criterion in junit.tags_in(t.name)]
            failures = [f"{t.name}: {((t.message or '').strip().splitlines() or ['failed'])[0][:300]}"
                        for t in tests if t.outcome != "passed"]
            if tests and not failures:
                continue  # passing already: the release reads it as it is
            start = ci.commit(root, f"Before the last try at {criterion}")
            output = rewrite(_the_defect(criterion, texts[criterion], deferred[criterion], failures))
            changed = list(getattr(output, "changed_files", None) or [])
            if not changed:
                continue
            after = run_suite()
            now = passing(after)
            own = [t for t in getattr(getattr(after, "report", None), "tests", None) or []
                   if criterion in junit.tags_in(t.name)]
            if own and all(t.outcome == "passed" for t in own) and held <= now:
                suite.undefer(root, [criterion])
                ci.commit(root, f"Last try at {criterion}: its tests pass")
                made.append(criterion)
                held = now
                logger.warning("Last try at deferred %s: its tests pass now; no longer deferred", criterion)
            else:
                ci.restore_paths(root, start, changed)
                ci.commit(root, f"Last try at {criterion}: put back")
                logger.info("Last try at deferred %s did not pass it without breaking another; put back", criterion)
        return made
    except Exception:  # noqa: BLE001 - the release goes on as it was
        logger.warning("Could not make the last try at the deferred criteria", exc_info=True)
        return []


__all__ = ["MOST_CRITERIA", "ON_BY_DEFAULT", "enabled", "try_them"]
