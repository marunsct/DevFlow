"""The current Claude models are priced, so a run's cost ceiling holds on them.

Found when the owner approved a run on Claude Haiku 5.5 with a fixed budget: the price table knew no Claude model
released after 2025, so a Haiku 5.5 run counted as unpriced and `MAX_RUN_COST_USD` could not stop it; and the old
`claude-opus-4` prefix would have charged Opus 4.8 at three times its price.
"""
from __future__ import annotations

import pytest

from app.observability import cost_tracker


def test_haiku_5_5_is_priced_at_its_short_and_long_prompt_rates():
    price = cost_tracker._lookup("claude-haiku-5-5")

    assert price is not None
    assert price.usd_for(50_000, 2_000) == pytest.approx((50_000 * 0.10 + 2_000 * 0.50) / 1_000_000)
    assert price.usd_for(150_000, 2_000) == pytest.approx((150_000 * 0.50 + 2_000 * 2.50) / 1_000_000)


def test_a_newer_opus_is_not_charged_at_the_old_opus_4_rate():
    assert cost_tracker._lookup("claude-opus-4-8").input_usd_per_mtok == 5.00
