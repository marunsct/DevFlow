"""A model call with no reply cap and no ceiling is still paced against how fast the server has been.

Measured on a local server running a model with no reply ceiling: one request was never answered (the same server
answered a new request in 0.3 s) and the run waited on it for the configured thirty minutes, because the deadline was
shortened only for a call whose reply length was known.
"""
from __future__ import annotations

from app import models

SERVER = ("http://x/v1", "some-model")


def _paced(rate_tokens_per_second: float) -> None:
    models._PACE.clear()
    for _ in range(3):
        models.record_pace(SERVER, 2000, 2000 / rate_tokens_per_second)


def test_a_call_with_no_cap_and_no_ceiling_is_paced_against_the_longest_real_reply():
    _paced(60.0)

    deadline = models.paced_timeout(SERVER, models.expected_reply_tokens(None, None), 1800.0)

    assert deadline is not None and deadline < 600.0
    assert deadline >= models.MIN_REQUEST_TIMEOUT_SECONDS


def test_a_cap_or_a_ceiling_still_decides_when_there_is_one():
    assert models.expected_reply_tokens(4000, 24000) == 4000
    assert models.expected_reply_tokens(None, 24000) == 24000
    assert models.expected_reply_tokens(None, None) == models.LARGEST_LEGITIMATE_OUTPUT_TOKENS


def test_before_the_server_is_measured_the_configured_limit_stands():
    models._PACE.clear()
    assert models.paced_timeout(SERVER, models.expected_reply_tokens(None, None), 1800.0) is None
