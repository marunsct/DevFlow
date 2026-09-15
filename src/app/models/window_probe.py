"""Ask the model server how much context it actually has.

The context window is the one number in this system that has to be right. Every
other budget is derived from it, and getting it wrong is silent: a window set
larger than the truth schedules compaction to fire at a point the model never
reaches, so the run dies hours later in an unrelated stage with an error that
names neither the setting nor the mistake.

It is also a number almost nobody knows. A model's advertised window is not what
it was loaded with - a local server will happily serve `gpt-oss-20b`, whose
architecture supports 131,072 tokens, in a 8,192-token slot because that is what
the slider was on. Nothing in the OpenAI-compatible API reports it: `/v1/models`
returns an id and little else, and the richer endpoints are not standard.

What every server does report is the limit it *refused*. Sending one deliberately
oversized request produces an error that names the real number:

    request (400068 tokens) exceeds the available context size (131072 tokens)

That is the measurement this module makes. It costs one rejected request, which
is refused before any generation, and it replaces a guess that the entire
history of this repository has shown people get wrong.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Mapping

logger = logging.getLogger(__name__)

PROBE_TOKENS = 400_000
"""Size of the deliberately oversized request, in approximate tokens.

Above every window this is likely to meet - the largest local model seen here is
262,144 - so the server is certain to refuse and name its limit. A probe that is
accepted tells us only "at least this much", which is the one answer that is not
useful.
"""

PROBE_TIMEOUT_SECONDS = 180
"""Generous, because the server still has to tokenise the prompt to refuse it."""


#: Each pattern captures the server's *own* limit, never the size we sent.
#:
#: Ordered most specific first. The llama.cpp family reports both numbers in one
#: sentence, and a pattern loose enough to match "(400068 tokens)" would read
#: back the probe size and configure a window four times too large - which is
#: precisely the failure this exists to prevent.
_LIMIT_PATTERNS: tuple[re.Pattern[str], ...] = (
    # llama.cpp / LM Studio: "...exceeds the available context size (131072 tokens)"
    re.compile(r"available context size \((\d+) tokens?\)", re.I),
    # The same servers repeat it as JSON: "n_ctx":131072
    re.compile(r'"n_ctx"\s*:\s*(\d+)'),
    # OpenAI and vLLM: "This model's maximum context length is 8192 tokens"
    re.compile(r"maximum context length is (\d+) tokens?", re.I),
    # Anthropic: "prompt is too long: 250000 tokens > 200000 maximum"
    re.compile(r">\s*(\d+)\s*maximum", re.I),
    # Some gateways: "context window of 32768"
    re.compile(r"context window (?:of|is) (\d+)", re.I),
)


def limit_from_error(message: str) -> int | None:
    """The server's own context limit, read out of its refusal. None if absent.

    Public because it is the part worth testing directly: the patterns have to
    survive providers rewording their messages, and a regression here silently
    reverts the whole feature to guessing.
    """
    for pattern in _LIMIT_PATTERNS:
        found = pattern.search(message or "")
        if not found:
            continue
        try:
            value = int(found.group(1))
        except (TypeError, ValueError):
            continue
        # A "limit" at or above what we sent is the probe size read back, not a
        # limit. Refuse it rather than configure a window from our own input.
        if 0 < value < PROBE_TOKENS:
            return value
    return None


def detect_context_window(
    base_url: str, api_key: str, model: str, *, timeout: int = PROBE_TIMEOUT_SECONDS
) -> tuple[int | None, str]:
    """Measure the server's context window. Returns `(tokens, explanation)`.

    Never raises. A detection that cannot complete is a setting the operator
    fills in by hand, which is where they were already; an exception here would
    take the settings page down with it.
    """
    if not base_url or not model:
        return None, "No model server is configured."

    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    body = json.dumps(
        {
            "model": model,
            # Cheap to build and cheap to tokenise, unlike random text.
            "messages": [{"role": "user", "content": "word " * PROBE_TOKENS}],
            "max_tokens": 1,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Authorization": f"Bearer {api_key or 'none'}", "Content-Type": "application/json"},
    )

    try:
        urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as refusal:
        try:
            detail = refusal.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - the status alone is still informative
            detail = ""
        found = limit_from_error(detail)
        if found is not None:
            return found, f"The server refused a {PROBE_TOKENS:,}-token request and reported {found:,}."
        return None, (
            f"The server refused the probe but did not say what its limit is "
            f"(HTTP {refusal.code}). Set the window by hand."
        )
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.warning("Context-window probe failed", exc_info=True)
        return None, f"Could not reach the model server: {type(exc).__name__}."

    # Accepted. That bounds the window from below and no further, which is not
    # something to configure from - a window set to the probe size would be
    # wrong for every server that merely truncated the prompt instead of
    # refusing it.
    return None, (
        f"The server accepted a {PROBE_TOKENS:,}-token request without complaint, so its "
        "limit could not be measured this way. Set the window by hand."
    )


def detect_from_settings(environment: Mapping[str, str], secrets: Mapping[str, str]) -> tuple[int | None, str]:
    """`detect_context_window`, wired to the stored provider settings."""
    return detect_context_window(
        environment.get("OPENAI_BASE_URL", ""),
        secrets.get("openai_api_key", "") or environment.get("OPENAI_API_KEY", ""),
        environment.get("OPENAI_MODEL", ""),
    )


__all__ = ["PROBE_TOKENS", "detect_context_window", "detect_from_settings", "limit_from_error"]
