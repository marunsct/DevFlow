"""The fix cycle, bounded per defect: localise, rewrite and verify (plan AY).

Measured over the runs before it: 8 of 62 defects fixed, 100 to 200 model
calls per defect, and on one gate run the fix stages wrote about 1.1 million
of its 1.34 million output tokens. The harness already had the parts of the
pattern the strongest open harnesses use - several short candidates, each kept
only when the defect's own tests pass (Agentless) - but asked for candidates
only from a judgement model distinct from the build model, so a run on one
local model never reached them and went from one rewrite to a forty-call
agent loop.
"""

from __future__ import annotations

from typing import Any

#: Group 2 of the plan is measured before and after (ADR-0010): built while a
#: gate run measures the code without it, so it stays off until that run ends.
#: `FIX_CYCLE` set to on or off overrides this.
ON_BY_DEFAULT = False


def enabled() -> bool:
    """Whether the bounded fix cycle runs (plan AY)."""
    from app.switches import is_on

    return is_on("FIX_CYCLE", ON_BY_DEFAULT)


def the_candidate_model(judgement_model: Any, model: Any, fix_model: Any = None) -> Any | None:
    """Which model writes the candidate fixes after a failed one; None when no candidates are asked.

    A judgement model of its own first, as before. Without one, the model the
    fix runs on (AY step 2): candidates sampled at the server's own setting
    differ from each other, and each is kept only if the defect's tests pass,
    so the same weights are as safe a source as another tier.
    """
    if judgement_model is not None and judgement_model is not model:
        return judgement_model
    if enabled():
        return fix_model or model
    return None
