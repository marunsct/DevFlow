"""One model call cannot wait forever.

The alternative to setting this is not "no timeout" but the OpenAI SDK's
default - `Timeout(connect=5, read=600, write=600, pool=600)` - a value nobody
here chose.

Measured on a local llama.cpp server. Twice a request has wedged: the server
reported `llamacpp:requests_processing 1` with `prompt_tokens_total` AND
`tokens_predicted_total` both frozen across a 25-second sample, while the GPU
sat at 88%. A slow generation still moves those counters; a wedged one moves
neither. One run lost 22 minutes to it in `tools_models`; one run
never produced a single event.

The retry is cheap: on one run the identical request succeeded in 66
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

    assert source.count("max_retries=") == source.count("timeout=_request_timeout(),")


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
    specification. One run hit it twice in one hour, each costing 300
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


def test_the_floor_is_derived_not_guessed() -> None:
    """Derived from the largest real answer and the measured generation rate,
    so the timeout and the output it must accommodate cannot drift apart."""
    from app.models import (
        LARGEST_LEGITIMATE_OUTPUT_TOKENS,
        _tokens_per_second,
        _time_to_generate_a_full_answer,
    )

    expected = LARGEST_LEGITIMATE_OUTPUT_TOKENS / _tokens_per_second()

    assert _time_to_generate_a_full_answer() == expected


def test_streaming_is_not_enabled_on_the_model() -> None:
    """It is the better fix and it does not work through the agent.

    Setting `streaming` puts `stream: true` in the payload while langchain
    still routes through the non-streaming `_generate`, which is handed an
    `openai.Stream` it cannot read:

        ValueError: Unexpected response type from OpenAI-compatible endpoint.
        Expected a dict or openai.BaseModel, got Stream

    That killed one run on its first model call. It passes when a model
    is built and invoked directly, which is how it reached a deploy; the agent
    invokes a *bound* model and takes a different path. This test exists so
    the next attempt starts from a reproduction through `langchain.agents`.
    """
    from app.models import CompatibleChatOpenAI

    assert CompatibleChatOpenAI.model_fields["streaming"].default is False


def test_the_floor_comes_from_real_output_not_the_pathology_ceiling() -> None:
    """The correction to an earlier version of this module.

    `_max_output_tokens()` is 32,000, but that is a ceiling on pathology - it
    exists so one confused turn cannot emit 108,000 tokens over 38 minutes, as
    `specialist_ui_ux_0` did on one run. Deriving the timeout from it gave
    800 seconds, which made the only failure mode that actually occurs take 2.7
    times longer to detect in order to permit answers that never happen.

    Measured on one run, 206 model calls: the longest legitimate call was
    141.7 seconds and *nothing* landed between 170 and 800 seconds. The single
    call past 800s was a wedge whose retry succeeded in 2.5 seconds.
    """
    from app.models import (
        LARGEST_LEGITIMATE_OUTPUT_TOKENS,
        _max_output_tokens,
        _request_timeout,
        _time_to_generate_a_full_answer,
    )

    assert LARGEST_LEGITIMATE_OUTPUT_TOKENS < _max_output_tokens()
    # Comfortably under the 800s the pathology ceiling produced, while still
    # covering the slowest model measured (33 tok/s needs 394s).
    assert 394 <= _time_to_generate_a_full_answer() < 600
    # Still comfortably above the longest legitimate call ever measured.
    assert _request_timeout() > 141.7 * 2


def test_a_wedge_is_still_caught_in_minutes_not_quarter_hours() -> None:
    """Why the ceiling is not the right basis.

    A wedged request produces nothing and its retry succeeds immediately, so
    the whole cost of a wedge is the timeout. Every second added to accommodate
    a hypothetical long answer is paid in full on every real wedge.
    """
    from app.models import _request_timeout

    # 800s was the pathology-ceiling answer; this stays far below it.
    assert _request_timeout() <= 600


def test_the_rate_floor_is_below_every_model_measured() -> None:
    """A constant measured on one model is that model's rate, not a floor.

    Measured on this endpoint over 800-1,200 token completions: Qwen3.5-9B at
    40.9 tok/s, Qwen2.5-Coder-7B-128K at 51.7, North-Mini-Code-1.0 at 33.0.
    The constant was 40.0, taken from the first, and the third broke it - at 33
    tok/s a full-length answer needs 394 seconds against the 325 that floor
    derived, which is exactly the mismatch this mechanism exists to prevent.
    """
    from app.models import DEFAULT_MIN_TOKENS_PER_SECOND

    slowest_measured = 33.0

    assert DEFAULT_MIN_TOKENS_PER_SECOND <= slowest_measured


def test_a_slower_model_can_be_declared(monkeypatch) -> None:
    """Lowering it only lengthens the timeout, so a wrong value here costs
    patience rather than correctness."""
    from app.models import _request_timeout, _tokens_per_second

    monkeypatch.setenv("MODEL_TOKENS_PER_SECOND", "10")

    assert _tokens_per_second() == 10.0
    assert _request_timeout() >= 1300  # 13,000 tokens at 10 tok/s


def test_a_nonsense_rate_falls_back_rather_than_dividing_by_zero(monkeypatch) -> None:
    """This is read while building a model; an infinite wait is worse than a
    wrong one."""
    from app.models import DEFAULT_MIN_TOKENS_PER_SECOND, _tokens_per_second

    for bad in ("0", "-5", "not-a-number"):
        monkeypatch.setenv("MODEL_TOKENS_PER_SECOND", bad)
        assert _tokens_per_second() == DEFAULT_MIN_TOKENS_PER_SECOND


def test_the_timeout_now_covers_the_slowest_model_measured() -> None:
    from app.models import LARGEST_LEGITIMATE_OUTPUT_TOKENS, _request_timeout

    slowest_measured = 33.0
    needed = LARGEST_LEGITIMATE_OUTPUT_TOKENS / slowest_measured

    assert _request_timeout() >= needed
