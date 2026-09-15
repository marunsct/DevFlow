"""Reading a server's real context window out of its own refusal.

The patterns are the whole feature. If one stops matching, detection silently
reverts to guessing - and guessing this number wrong is the failure that has
cost this repository the most: it is invisible at configuration time and
surfaces hours later as a dead stage in an unrelated part of the run.

Every string below is a real refusal, kept verbatim, including the one measured
from this project's own model server.
"""

from __future__ import annotations

import pytest

from app.models.window_probe import PROBE_TOKENS, detect_context_window, limit_from_error

# Measured from the LM Studio server this project runs against.
LM_STUDIO = (
    '{"error":"Engine protocol predict request returned 400: {\\"error\\":{\\"code\\":400,'
    '\\"message\\":\\"request (400068 tokens) exceeds the available context size (131072 tokens), '
    'try increasing it\\",\\"type\\":\\"exceed_context_size_error\\",\\"n_prompt_tokens\\":400068,'
    '\\"n_ctx\\":131072}}"}'
)

OPENAI = (
    "This model's maximum context length is 8192 tokens. However, your messages resulted "
    "in 400068 tokens. Please reduce the length of the messages."
)

VLLM = "This model's maximum context length is 4096 tokens. However, you requested 400100 tokens."

ANTHROPIC = "prompt is too long: 400068 tokens > 200000 maximum"

GATEWAY = "Request exceeds the context window of 32768 for this deployment."


@pytest.mark.parametrize(
    "message,expected",
    [
        (LM_STUDIO, 131_072),
        (OPENAI, 8_192),
        (VLLM, 4_096),
        (ANTHROPIC, 200_000),
        (GATEWAY, 32_768),
    ],
)
def test_the_servers_own_limit_is_read_out_of_its_refusal(message, expected):
    assert limit_from_error(message) == expected


def test_the_probe_size_is_never_mistaken_for_the_limit():
    """Both numbers appear in the same sentence, and only one is the answer.

    A pattern loose enough to match "(400068 tokens)" would configure a window
    four times larger than the model has - the exact failure this prevents.
    """
    assert limit_from_error(LM_STUDIO) != 400_068
    assert limit_from_error(OPENAI) != 400_068
    assert limit_from_error(ANTHROPIC) != 400_068


def test_a_number_at_or_above_the_probe_size_is_refused():
    assert limit_from_error(f"maximum context length is {PROBE_TOKENS} tokens") is None
    assert limit_from_error(f"maximum context length is {PROBE_TOKENS + 1} tokens") is None


def test_an_unrecognised_refusal_yields_nothing_rather_than_a_guess():
    assert limit_from_error("Bad request") is None
    assert limit_from_error("") is None
    assert limit_from_error("rate limit exceeded, try again in 20s") is None


def test_detection_never_raises_on_an_unreachable_server():
    """A settings page must not be taken down by a probe."""
    found, why = detect_context_window(
        "http://127.0.0.1:9/v1", "key", "some-model", timeout=2
    )

    assert found is None
    assert "could not reach" in why.lower()


def test_detection_declines_without_a_configured_server():
    found, why = detect_context_window("", "", "")

    assert found is None
    assert "no model server" in why.lower()


def test_a_server_that_accepts_the_probe_is_not_guessed_at():
    """Accepting bounds the window from below and no further.

    Some servers truncate an oversized prompt instead of refusing it, so
    acceptance is not evidence of a large window - and configuring the probe
    size would be worse than leaving the field alone.
    """

    class _Accepts:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    import app.models.window_probe as probe

    original = probe.urllib.request.urlopen
    probe.urllib.request.urlopen = lambda *a, **k: _Accepts()
    try:
        found, why = detect_context_window("http://x/v1", "k", "m")
    finally:
        probe.urllib.request.urlopen = original

    assert found is None
    assert "by hand" in why
