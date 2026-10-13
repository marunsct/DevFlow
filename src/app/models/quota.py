"""Whether a model call failed because the account behind it has run out.

A provider that refuses a call for want of quota or credit refuses every call
after it the same way until a person adds funds or changes a plan. Trying the
stage again spends minutes on refusals, and recording the run as failed says
something went wrong with the work when nothing did. A refusal of this kind is
told apart from a rate limit, which passes on its own: a 429 counts only when
it says the quota or the balance is gone.
"""

from __future__ import annotations

#: Phrases providers use for an exhausted quota, balance or plan.
OUT_OF_QUOTA_PHRASES = (
    "insufficient_quota",
    "quota exhausted",
    "quota exceeded",
    "exceeded your current quota",
    "free quota",
    "insufficient balance",
    "insufficient_balance",
    "credit balance is too low",
    "insufficient credits",
    "out of credits",
    "billing_hard_limit",
    "payment required",
)


def _causes(error: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in seen and len(seen) < 10:
        seen.append(current)
        current = current.__cause__ or current.__context__
    return seen


def out_of_quota(error: BaseException) -> bool:
    """Whether `error`, or what caused it, is a provider refusing for want of quota or credit."""
    for item in _causes(error):
        status = getattr(item, "status_code", None)
        if status is None:
            status = getattr(getattr(item, "response", None), "status_code", None)
        if status == 402:
            return True
        if status in (403, 429) or status is None:
            text = f"{type(item).__name__}: {item}".lower()
            if any(phrase in text for phrase in OUT_OF_QUOTA_PHRASES):
                return True
    return False
