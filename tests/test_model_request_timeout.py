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

A full-length answer is 13,000 tokens and the slowest model measured makes 33
tokens a second, so no timeout may be under 394 seconds.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.models import _request_timeout

#: 13,000 tokens at the slowest measured 33 tokens a second.
A_FULL_ANSWER_ON_THE_SLOWEST_MODEL = 394


def test_it_can_be_raised(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT_SECONDS", "900")

    assert _request_timeout() == 900.0  # above the derived floor, so honoured


@pytest.mark.parametrize("asked", ["10", "30", "not-a-number"])
def test_it_cannot_be_set_below_what_an_answer_needs(monkeypatch, asked) -> None:
    """A timeout under the longest legitimate call turns real work into
    retries, which is the more expensive mistake; garbage falls back rather than
    raising, since this is read while building a model."""
    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT_SECONDS", asked)

    assert _request_timeout() >= A_FULL_ANSWER_ON_THE_SLOWEST_MODEL


def _timeout_of(model) -> float | None:
    """The client's request timeout, whichever name its library gives it."""
    for name in ("request_timeout", "default_request_timeout", "timeout"):
        if getattr(model, name, None) is not None:
            return float(getattr(model, name))
    return None


@pytest.mark.parametrize("provider,base_url", [
    ("local", "http://gpu:9090/v1"), ("anthropic", ""), ("gemini", ""),
])
def test_every_model_built_here_carries_it(provider, base_url) -> None:
    """Reaching five of six construction sites is the mistake this codebase has
    made four times: the primary and the fallback of every provider."""
    from app.config import load_settings
    from app.models import build_default_chat_model

    settings = replace(
        load_settings({"LLM_PROVIDER": "local", "OPENAI_BASE_URL": base_url or "http://gpu:9090/v1",
                       "OPENAI_API_KEY": "k", "MODEL_NAME": "m"}),
        llm_provider=provider, openai_base_url=base_url, anthropic_api_key="a", google_api_key="g",
        model_name=f"m-{provider}",
    )

    model = build_default_chat_model(settings=settings)

    built = [model.runnable, *model.fallbacks]
    assert len(built) == 2
    assert all(A_FULL_ANSWER_ON_THE_SLOWEST_MODEL <= _timeout_of(part) < 600 for part in built), built


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
    length limit wearing the wrong name. The rate floor was once 40 tokens a
    second, measured on one model; a model at 33 then needed 394 seconds against
    the 325 that floor derived.
    """
    assert _request_timeout() >= A_FULL_ANSWER_ON_THE_SLOWEST_MODEL


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


def test_a_slower_model_can_be_declared(monkeypatch) -> None:
    """Lowering it only lengthens the timeout, so a wrong value here costs
    patience rather than correctness."""
    from app.models import _request_timeout, _tokens_per_second

    monkeypatch.setenv("MODEL_TOKENS_PER_SECOND", "10")

    assert _tokens_per_second() == 10.0
    assert _request_timeout() >= 1300  # 13,000 tokens at 10 tok/s


@pytest.mark.parametrize("bad", ["0", "-5", "not-a-number"])
def test_a_nonsense_rate_falls_back_rather_than_dividing_by_zero(monkeypatch, bad) -> None:
    """This is read while building a model; an infinite wait is worse than a
    wrong one."""
    from app.models import _tokens_per_second

    monkeypatch.setenv("MODEL_TOKENS_PER_SECOND", bad)

    assert _tokens_per_second() == 30.0
