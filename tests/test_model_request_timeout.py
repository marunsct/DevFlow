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
    the stored runs; everything else is well under.

    That still sets the *baseline*, but it is no longer what `_request_timeout`
    returns: httpx applies the value as a total, so it must also be long enough
    to generate a full-length answer, which on this deployment is the larger
    number. See `test_the_timeout_allows_a_full_length_answer`.
    """
    assert DEFAULT_REQUEST_TIMEOUT_SECONDS == 300.0
    assert _request_timeout() >= DEFAULT_REQUEST_TIMEOUT_SECONDS


def test_it_can_be_raised(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT_SECONDS", "900")

    assert _request_timeout() == 900.0  # above the derived floor, so honoured


def test_it_cannot_be_lowered_below_real_work(monkeypatch) -> None:
    """A timeout under the longest legitimate call turns real work into
    retries, which is the more expensive mistake."""
    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT_SECONDS", "10")

    assert _request_timeout() >= MIN_REQUEST_TIMEOUT_SECONDS


def test_garbage_falls_back_rather_than_raising(monkeypatch) -> None:
    """This is read while building a model; raising here fails the run."""
    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT_SECONDS", "not-a-number")

    assert _request_timeout() >= DEFAULT_REQUEST_TIMEOUT_SECONDS


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


def test_the_timeout_allows_a_full_length_answer() -> None:
    """The two constants were chosen independently and contradicted each other.

    DEFAULT_REQUEST_TIMEOUT_SECONDS came from the longest call observed (162s
    x 2); DEFAULT_MAX_OUTPUT_TOKENS from the largest legitimate artifact
    (~13,000 tokens). httpx applies the timeout as a total, so at this
    deployment's measured ~41 tokens/second a 300-second timeout cut off every
    reply beyond about 12,000 tokens - including that 13,000-token
    specification. run-f0630b10 hit it twice in one hour, each costing 300
    seconds and a retry that could only time out the same way.

    A timeout shorter than a full-length answer is not a timeout, it is a
    length limit wearing the wrong name.
    """
    from app.models import _request_timeout, _time_to_generate_a_full_answer

    assert _request_timeout() >= _time_to_generate_a_full_answer()


def test_an_explicit_timeout_cannot_be_set_below_what_an_answer_needs(monkeypatch) -> None:
    """An operator may raise it; below the floor is a guarantee of failure."""
    from app.models import _request_timeout, _time_to_generate_a_full_answer

    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT_SECONDS", "30")

    assert _request_timeout() >= _time_to_generate_a_full_answer()

    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT_SECONDS", "99999")
    assert _request_timeout() == 99999


def test_the_floor_moves_with_the_output_ceiling() -> None:
    """Derived, so the two cannot drift apart again."""
    from app.models import (
        MIN_EXPECTED_TOKENS_PER_SECOND,
        _max_output_tokens,
        _time_to_generate_a_full_answer,
    )

    expected = _max_output_tokens() / MIN_EXPECTED_TOKENS_PER_SECOND

    assert _time_to_generate_a_full_answer() == expected


def test_streaming_is_not_enabled_on_the_model() -> None:
    """It is the better fix and it does not work through the agent.

    Setting `streaming` puts `stream: true` in the payload while langchain
    still routes through the non-streaming `_generate`, which is handed an
    `openai.Stream` it cannot read:

        ValueError: Unexpected response type from OpenAI-compatible endpoint.
        Expected a dict or openai.BaseModel, got Stream

    That killed run-027f369c on its first model call. It passes when a model
    is built and invoked directly, which is how it reached a deploy; the agent
    invokes a *bound* model and takes a different path. This test exists so
    the next attempt starts from a reproduction through `langchain.agents`.
    """
    from app.models import CompatibleChatOpenAI

    assert CompatibleChatOpenAI.model_fields["streaming"].default is False
