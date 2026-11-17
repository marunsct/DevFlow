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

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GraphContext:
    """The models, checkpointer and repository scope a run's nodes share.

    `model`: the run's default model (or None: each stage builds the default).
    `judgement_model`: the architect's, QA's, the reviews', the test rounds' and
    the fixes' model. `planning_model`: what intake, the stack, the sprint plan and
    the work orders are written on. `building_model`: the build stages' model, with
    reasoning off in fast delivery. See `build_workflow_graph` for how each is chosen.
    """

    model: Any
    judgement_model: Any
    planning_model: Any
    building_model: Any
    checkpointer: Any
    repo_root: str | None
    allow_subdirectories: bool = True
