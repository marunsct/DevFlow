"""What every node of a run's graph is built with.

`build_workflow_graph` makes one `GraphContext` from its parameters and hands it
to each node that needs it, so a node is a module-level function of
`(state, config, ctx)` rather than a closure over the builder's locals. See
`app.graph.nodes`.

It carries every field of `app.graph.acceptance_nodes.Context`, so the stages
kept in `acceptance_nodes`, `engineering`, `escalation` and `delivery` take it
as they are.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

#: The workflow's logger: the model choices log as they did inside the builder.
logger = logging.getLogger("app.graph.workflow")


@dataclass(frozen=True)
class GraphContext:
    """The models, checkpointer and repository scope a run's nodes share.

    `model`: the run's default model (or None: each stage builds the default).
    `judgement_model`: the architect's, QA's, the reviews', the test rounds' and
    the fixes' model. `planning_model`: what intake, the stack, the sprint plan and
    the work orders are written on. `building_model`: the build stages' model, with
    reasoning off in fast delivery. See `build_workflow_graph` for how each is chosen,
    and `the_build_model` for which one a stage that builds or fixes runs on.
    """

    model: Any
    judgement_model: Any
    planning_model: Any
    building_model: Any
    checkpointer: Any
    repo_root: str | None
    allow_subdirectories: bool = True

    def the_build_model(
        self,
        state: Any,
        stage_name: str,
        failed_tries: int = 0,
        *,
        reasons: bool = False,
        after_a_revert: bool = False,
    ) -> Any:
        """The model a stage that builds or fixes runs on: the default one, until it has failed.

        The judgement model takes over once this stage has had to start over on
        a fresh conversation `escalate_after()` times, once the defect it fixes
        has failed that many fixes (`failed_fix_tries`), or on a sprint being
        tried again (`the_model_for_this_attempt`). If that fails too, the run
        goes on as it always has.

        `reasons`: a fix reasons as the owner configured the model. Fast
        delivery switches reasoning off to write what the specification has
        decided; a fix has to find out why something fails first. One run's
        fixes without it broke 62 passing tests in one fix and reported edits
        they never made.
        """
        from app.models.roles import escalate_after

        quiet = self.model if reasons else self.building_model
        if self.judgement_model is self.model:
            return quiet
        if after_a_revert:
            # The revert is the proven failure signal; the next attempt does
            # not wait for the generic rung (Initiative L.4). Capped at one
            # per defect by `_a_revert_escalates_this_fix`.
            logger.info(
                "Stage %s goes to the judgement model: the fix it retries was reverted once, "
                "which is a measured failure of the build model's attempt",
                stage_name,
            )
            return self.judgement_model
        limit = escalate_after()
        restarts = int((state.get("structured_retries") or {}).get(stage_name, 0))
        if restarts >= limit or failed_tries >= limit:
            logger.info(
                "Stage %s goes to the judgement model: %d restart(s), %d failed fix(es) on the build model",
                stage_name, restarts, failed_tries,
            )
            return self.judgement_model
        chosen = self.the_model_for_this_attempt(state)
        return quiet if chosen is self.model else chosen

    def the_model_for_this_attempt(self, state: Any) -> Any:
        """A rung of the escalation ladder: a sprint being tried again after a
        re-plan, a sent-back review, a held release or an escalation is built on
        the judgement model, not the default one."""
        retried = (
            int(state.get("sprint_replan_count") or 0) >= 1
            or int(state.get("milestone_revision_count") or 0) >= 2
            or int(state.get("release_attempts") or 0) >= 1
            or int(state.get("escalation_count") or 0) >= 1
        )
        return self.judgement_model if retried else self.model
