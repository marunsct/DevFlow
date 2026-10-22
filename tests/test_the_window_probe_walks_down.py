"""A server that refuses without naming its limit is still measurable.

Part I item 2 derives every context budget from the model's window, and the
single-probe design could only read a limit a server volunteered in its refusal
message. Most local servers do not: measured 2026-09-21 against
`unsloth/Qwen3.6-35B-A3B-MTP-GGUF` behind llama.cpp, the refusal is a bare
HTTP 400 with no number in it, and detection answered

    "The server refused the probe but did not say what its limit is
     (HTTP 400). Set the window by hand."

Which is how `MODEL_CONTEXT_WINDOW` came to be a hand-entered 130,000 that
nothing had confirmed, with `input_ceiling_tokens`, `compaction_trigger_tokens`
and every other derived budget resting on it.

Windows are configuration values rather than arbitrary numbers - a server is
loaded with a power of two or a round figure near one - so walking a ladder of
those lands on the real value in a few requests, where a binary search would
take seventeen and land near it.
"""

from __future__ import annotations

import urllib.error

import pytest

from app.models import window_probe
from app.models.window_probe import PROBE_TOKENS, detect_context_window


def _refusal(code=400, body=b"Bad Request"):
    return urllib.error.HTTPError("u", code, "Bad Request", {}, None)


@pytest.fixture
def server(monkeypatch):
    """A fake server that accepts prompts up to `limit` tokens."""
    sent = []

    def _install(limit, unreachable_above=None):
        def _urlopen(request, timeout=None):
            body = request.data.decode("utf-8")
            words = body.count("word ")
            sent.append(words)
            if unreachable_above is not None and words > unreachable_above:
                raise TimeoutError("server went away")
            if words > limit:
                raise _refusal()
            class _Response:
                def read(self):
                    return b"{}"
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
            return _Response()

        monkeypatch.setattr(window_probe.urllib.request, "urlopen", _urlopen)
        return sent

    return _install


def test_it_finds_the_window_a_silent_server_will_accept(server):
    sent = server(limit=40_000)

    detected, why = detect_context_window("http://x/v1", "k", "m")

    assert detected == 32_768
    assert "accepted 32,768" in why
    # The oversized probe first, then down the ladder - never up.
    assert sent[0] == PROBE_TOKENS
    assert sent == sorted(sent, reverse=True)


def test_a_server_that_names_its_limit_is_not_walked(monkeypatch):
    """One request is enough when the refusal carries the number."""
    calls = []

    class _Named(urllib.error.HTTPError):
        def read(self):
            return b"This model's maximum context length is 8192 tokens"

    def _urlopen(request, timeout=None):
        calls.append(request.data.decode("utf-8").count("word "))
        raise _Named("u", 400, "Bad Request", {}, None)

    monkeypatch.setattr(window_probe.urllib.request, "urlopen", _urlopen)

    detected, why = detect_context_window("http://x/v1", "k", "m")

    assert detected == 8192
    assert "reported 8,192" in why
    assert calls == [PROBE_TOKENS], "the ladder must not run when the limit is named"


def test_a_server_that_accepts_everything_is_not_guessed_at(server):
    """Accepting the probe bounds the window from below and no further."""
    server(limit=10**9)

    detected, why = detect_context_window("http://x/v1", "k", "m")

    assert detected is None
    assert "could not be measured" in why


def test_a_server_refusing_every_rung_says_so(server):
    server(limit=0)

    detected, why = detect_context_window("http://x/v1", "k", "m")

    assert detected is None
    assert "refused every size down to" in why
    assert "set the window by hand" in why.lower()


def test_a_server_that_stops_answering_mid_ladder_is_not_reported_as_small(
    monkeypatch,
):
    """Unreachable is not the same as refused, and must not become a window.

    The oversized probe is refused, so the ladder starts; the server then goes
    away. Reporting the last rung tried would configure a window from a
    timeout.
    """
    seen = []

    def _urlopen(request, timeout=None):
        words = request.data.decode("utf-8").count("word ")
        seen.append(words)
        if words >= PROBE_TOKENS:
            raise _refusal()
        raise TimeoutError("server went away")

    monkeypatch.setattr(window_probe.urllib.request, "urlopen", _urlopen)

    detected, why = detect_context_window("http://x/v1", "k", "m")

    assert detected is None
    assert "stopped answering" in why
    assert len(seen) >= 2, "the ladder must have been entered"


def test_an_unreachable_server_is_reported_as_unreachable(monkeypatch):
    """The first probe failing outright is a different answer from a refusal."""
    def _urlopen(request, timeout=None):
        raise TimeoutError("nothing is listening")

    monkeypatch.setattr(window_probe.urllib.request, "urlopen", _urlopen)

    detected, why = detect_context_window("http://x/v1", "k", "m")

    assert detected is None
    assert "Could not reach the model server" in why


def test_the_ladder_is_ordered_and_plausible():
    rungs = window_probe._COMMON_WINDOWS
    assert list(rungs) == sorted(rungs, reverse=True)
    assert 131_072 in rungs and 32_768 in rungs and 8_192 in rungs
    assert all(rung < PROBE_TOKENS for rung in rungs), (
        "a rung at or above the probe size can never be tried"
    )


def test_every_rung_asks_for_one_token(server):
    """This measures what the server will read, not what it will write."""
    import inspect

    source = inspect.getsource(window_probe._accepts)
    assert '"max_tokens": 1' in source
