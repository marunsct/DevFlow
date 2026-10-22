"""Say a transport cannot carry the reply budget before the run pays for it.

The two numbers were never compared. The harness sizes a reply budget from the
measured generation rate; a proxy in front of the model server caps how long an
origin may take to answer. When the first exceeds the second, every full-length
reply is cut off, retried on a fixed backoff, and cut off again - and nothing
said so until it had happened forty times.

Measured on one run, 2026-09-21: 37 retries at a fixed 120 seconds each,
74 minutes of a 129.6-minute run spent waiting - 57% of the wall clock.

`install()` explains an individual 524 to whoever reads the log. This explains
why they are inevitable, once, to whoever starts the run.
"""

from __future__ import annotations

import pytest

from app.observability.proxy_timeouts import (
    FIXED_ORIGIN_TIMEOUTS,
    reply_budget_that_cannot_arrive,
)

TUNNEL = "https://factors-friendship-panels-medicare.trycloudflare.com/v1"


class TestWhenItSpeaks:
    def test_a_fixed_origin_timeout_that_cannot_carry_the_budget(self, monkeypatch):
        monkeypatch.setattr("app.models._tokens_per_second", lambda: 30.0)

        complaint = reply_budget_that_cannot_arrive(TUNNEL)

        assert "trycloudflare.com" in complaint
        assert "100s" in complaint
        # It must quantify what does fit, not merely object.
        assert "3,000 tokens is all that fits" in complaint

    def test_a_direct_server_is_not_complained_about(self):
        assert reply_budget_that_cannot_arrive("http://localhost:1234/v1") == ""

    def test_a_fast_enough_server_behind_the_same_proxy_is_fine(self, monkeypatch):
        """The complaint is about arithmetic, not about the hostname."""
        monkeypatch.setattr("app.models._tokens_per_second", lambda: 500.0)
        assert reply_budget_that_cannot_arrive(TUNNEL) == ""

    def test_an_empty_url_says_nothing(self):
        assert reply_budget_that_cannot_arrive("") == ""


class TestItNeverBlocksAnything:
    def test_a_rate_that_cannot_be_read_is_silent(self, monkeypatch):
        def explode():
            raise RuntimeError("settings are away")

        monkeypatch.setattr("app.models._tokens_per_second", explode)
        assert reply_budget_that_cannot_arrive(TUNNEL) == ""

    def test_a_zero_rate_does_not_divide_by_zero(self, monkeypatch):
        monkeypatch.setattr("app.models._tokens_per_second", lambda: 0.0)
        assert reply_budget_that_cannot_arrive(TUNNEL) == ""


def test_the_ceiling_is_cloudflares_documented_one():
    assert FIXED_ORIGIN_TIMEOUTS["trycloudflare.com"] == 100


@pytest.mark.real_endpoint_probe
def test_the_runner_warns_rather_than_refuses():
    """A truncating transport is the operator's trade, made knowingly."""
    import inspect

    from app.server.runner import WorkflowRunner

    source = inspect.getsource(WorkflowRunner._require_a_reachable_model)
    assert "reply_budget_that_cannot_arrive" in source
    assert "logger.warning" in source
    assert "raise RunConflict(complaint)" not in source
