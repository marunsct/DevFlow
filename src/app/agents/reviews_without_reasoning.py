"""The acceptance review answers without reasoning first (behind `REVIEWS_WITHOUT_REASONING`, off until measured).

Measured over the last fourteen runs: the model was busy for 76-92% of each run's wall time and 68-74% of its
output tokens were reasoning; the acceptance review's output was all reasoning (6 model-minutes in one run). The
review reads a suite against its criteria and answers in a fixed schema, the shape of work fast delivery already runs
without reasoning (`app.agents.thinking.without_reasoning`). Whether its verdicts hold without it is what the switch's
on/off pairs measure: kept only with no loss in hidden score, false acceptances or the suite's strength.
"""
from __future__ import annotations

from typing import Any

from app.switches import is_on

#: `REVIEWS_WITHOUT_REASONING` set to on or off overrides this.
ON_BY_DEFAULT = False


def enabled() -> bool:
    return is_on("REVIEWS_WITHOUT_REASONING", ON_BY_DEFAULT)


def the_review_model(model: Any) -> Any:
    """`model` as the acceptance review should use it: without reasoning when the switch is on."""
    if not enabled():
        return model
    from app.agents.thinking import without_reasoning

    if model is None:
        # No judgement model configured: the stage would build the default one itself, reasoning as configured.
        # Measured on the switch's first run: three review replies of 54-74k reasoning characters each with it on.
        # Built here as fast delivery builds its own (`workflow`'s `building_model`).
        from app.models import build_default_chat_model

        model = build_default_chat_model()
    return without_reasoning(model)


__all__ = ["ON_BY_DEFAULT", "enabled", "the_review_model"]
