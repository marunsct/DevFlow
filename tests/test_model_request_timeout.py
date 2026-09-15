"""One model call cannot wait forever.

The alternative to setting this is not "no timeout" but the OpenAI SDK's
default - `Timeout(connect=5, read=600, write=600, pool=600)` - a value nobody
here chose.

Measured on a local llama.cpp server. Twice a request has wedged: the server
reported `llamacpp:requests_processing 1` with `prompt_tokens_total` AND
`tokens_predicted_total` both frozen across a 25-second sample, while the GPU
sat at 88%. A slow generation still moves those counters; a wedged one moves
neither. run-6412366b lost 22 minutes to it in `tools_models`; run-caae7e32
never produced a single event.

The retry is cheap: on run-6412366b the identical request succeeded in 66
seconds once the first attempt was abandoned.
"""

from __future__ import annotations

import pytest

from app.models import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    MIN_REQUEST_TIMEOUT_SECONDS,
    _request_timeout,
)


def test_the_default_is_twice_the_longest_measured_call() -> None:
    """`principal_architect` at 162 seconds is the longest legitimate call in
    the stored runs; everything else is well under."""
    assert DEFAULT_REQUEST_TIMEOUT_SECONDS == 300.0
    assert _request_timeout() == DEFAULT_REQUEST_TIMEOUT_SECONDS


def test_it_can_be_raised(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT_SECONDS", "900")

    assert _request_timeout() == 900.0


def test_it_cannot_be_lowered_below_real_work(monkeypatch) -> None:
    """A timeout under the longest legitimate call turns real work into
    retries, which is the more expensive mistake."""
    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT_SECONDS", "10")

    assert _request_timeout() == MIN_REQUEST_TIMEOUT_SECONDS


def test_garbage_falls_back_rather_than_raising(monkeypatch) -> None:
    """This is read while building a model; raising here fails the run."""
    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT_SECONDS", "not-a-number")

    assert _request_timeout() == DEFAULT_REQUEST_TIMEOUT_SECONDS


def test_every_model_built_here_carries_it() -> None:
    """Reaching five of six construction sites is the mistake this codebase has
    made four times."""
    import inspect

    from app import models

    source = inspect.getsource(models)

    assert source.count("max_retries=3,") == source.count("timeout=_request_timeout(),")


def test_the_live_model_has_a_timeout() -> None:
    """The property that matters: not None."""
    from app.models import build_default_chat_model

    model = build_default_chat_model()
    resolved = getattr(model, "request_timeout", None) or getattr(model, "timeout", None)

    assert resolved is not None
    assert float(resolved) >= MIN_REQUEST_TIMEOUT_SECONDS
