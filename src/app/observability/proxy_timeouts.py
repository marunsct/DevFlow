"""Name a proxy origin-timeout for what it is, instead of leaving it opaque.

**What this is for.** A model server reached through a reverse proxy or tunnel
has two timeouts, and only one of them is ours. `app.models._request_timeout`
derives a patient ceiling from the measured generation rate - 433 seconds on
this deployment. A Cloudflare quick tunnel (`*.trycloudflare.com`) caps an
origin response at roughly 100 seconds and that cap is not configurable. The
smaller one wins, so the derived timeout never applies: any generation that
needs more than about a hundred seconds is killed by the proxy first.

Observed on 2026-09-21 during a live run, on `specialist_ui_ux_2`::

    HTTP Request: POST https://...trycloudflare.com/v1/chat/completions
        "HTTP/1.1 524 <none>"
    Retrying request in 120.000000 seconds (retry 1 of 3)
    ... "HTTP/1.1 524 <none>"
    Retrying request in 120.000000 seconds (retry 2 of 3)

Four minutes of dead time, and the only thing the log said about the cause was
the bare number 524. The retry is not wrong - the third attempt succeeded, and a
shorter answer does get under the cap - but an operator reading this has no way
to learn that the ceiling they configured is not the ceiling in force.

**Why a log observer and not a client change.** The alternative is an httpx
`event_hooks` client passed to `ChatOpenAI`, which puts new code on the request
path of every model call - and a custom client also takes over timeout and
streaming behaviour. This only watches; it cannot change what a request does,
which is the right trade for a diagnostic.

The codes are Cloudflare's origin-error family. They are about the hop between
the proxy and the model server, never about the request's content, so a larger
context or a smaller reply will not fix a 522 or a 523 - only 524 responds to
asking for less.
"""

from __future__ import annotations

from typing import Any

import logging
import re
import threading
import time

logger = logging.getLogger(__name__)


PROXY_ORIGIN_ERRORS = {
    502: "the proxy got an invalid response from the model server",
    504: "the proxy's own gateway timed out waiting for the model server",
    520: "the model server returned something the proxy could not read",
    521: "the model server refused the proxy's connection - is it running?",
    522: "the proxy could not connect to the model server at all",
    523: "the proxy could not reach the model server's host",
    524: (
        "the model server accepted the request but did not answer within the "
        "proxy's origin timeout - about 100 seconds on a Cloudflare quick "
        "tunnel, and not configurable there"
    ),
}


#: Don't repeat the explanation on every retry of the same stall.
_QUIET_SECONDS = 60.0
_last_reported: dict[int, float] = {}
_lock = threading.Lock()

_STATUS = re.compile(r'"HTTP/[\d.]+ (\d{3})')


def _should_report(code: int) -> bool:
    now = time.monotonic()
    with _lock:
        if now - _last_reported.get(code, 0.0) < _QUIET_SECONDS:
            return False
        _last_reported[code] = now
        return True


class _ProxyErrorFilter(logging.Filter):
    """Watches httpx's request log and explains an origin error when one appears.

    A `Filter` rather than a `Handler` because a filter sees every record on the
    logger regardless of which handlers are configured, which matters in the
    worker where Celery owns the logging setup. It always returns True: this
    observes, it never suppresses anyone's log line.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            if "HTTP Request" not in message:
                return True
            found = _STATUS.search(message)
            if not found:
                return True
            code = int(found.group(1))
            meaning = PROXY_ORIGIN_ERRORS.get(code)
            if meaning and _should_report(code):
                from app.models import _request_timeout

                logger.warning(
                    "Model call returned HTTP %d: %s. The request timeout this "
                    "deployment derived is %.0fs, but a proxy in front of the "
                    "model server is enforcing a shorter one, so that derivation "
                    "does not apply. The client will retry, and a retry of the "
                    "same request usually hits the same wall. To fix rather than "
                    "wait: put the model server somewhere without a fixed origin "
                    "timeout, or lower MODEL_MAX_OUTPUT_TOKENS so a reply "
                    "finishes inside the proxy's limit.",
                    code,
                    meaning,
                    _request_timeout(),
                )
        except Exception:  # noqa: BLE001 - a diagnostic must never break logging
            pass
        return True


#: Objects already carrying the filter, by id. Per target rather than one
#: global flag, because Celery installs its handlers *after* `worker_process_init`
#: fires: a single "already done" flag meant the first call attached to the
#: handlers that existed then - none - and every later call returned early. The
#: set lets `install()` be called again once the real handlers are in place, and
#: attach to exactly the ones it has not seen.
def _already_watching(target: Any) -> bool:
    """Whether `target` already carries this observer.

    Asked of the target itself rather than of a remembered `id()`. CPython
    reuses an object's address as soon as the object is freed, so a set of ids
    answers "have I seen this address before" and not "is this handler being
    watched". A handler created after an earlier one was collected can land on
    that address, be taken for already-attached, and never get the filter - so
    the 524 it carries goes past unnamed, which is the precise failure this
    module exists to prevent.

    Found by the full suite rather than by this file's own tests: alone and
    beside its neighbours the id set behaved, and only with several hundred
    other tests allocating and freeing handlers first did a reused address make
    `install()` skip a live handler.
    """
    return any(
        isinstance(existing, _ProxyErrorFilter)
        for existing in getattr(target, "filters", ())
    )


def install() -> None:
    """Attach the observer wherever the request log can reach. Idempotent.

    Safe and useful to call repeatedly: each call attaches to any target it has
    not already seen, so calling it again after Celery has configured its
    handlers picks those up.

    Both the `httpx` logger *and* every root handler, because a filter only runs
    where it is attached and those are two different places.

    A `Logger`-level filter runs for records created by that logger. A
    `Handler`-level filter runs for every record that reaches the handler,
    including ones that propagated up from another logger. Under Celery the
    first was not enough: verified on 2026-09-21, the filter was attached to the
    `httpx` logger in the pool child - `logging.getLogger("httpx").filters`
    confirmed it, and the filter produced the right warning when driven by
    hand - and two live `HTTP/1.1 524` responses went past it without a word.
    Celery configures logging in the parent and routes worker output through its
    own handlers, so the record an operator sees is not one the `httpx` logger
    filtered on the way out.

    Attaching to the handlers as well costs one predicate per log record, which
    is what a filter is for, and catches the record wherever it is emitted.
    """
    targets: list[Any] = [logging.getLogger("httpx")]
    try:
        targets.extend(logging.getLogger().handlers)
    except Exception:  # noqa: BLE001
        pass
    for target in targets:
        try:
            if _already_watching(target):
                continue
            target.addFilter(_ProxyErrorFilter())
        except Exception:  # noqa: BLE001
            logger.debug("Could not attach the proxy-timeout observer", exc_info=True)


#: Hosts whose origin timeout is fixed and not configurable by the operator,
#: with the ceiling each enforces in seconds. A Cloudflare quick tunnel is the
#: one this deployment uses; the number is Cloudflare's documented 524 ceiling
#: and matches what was measured here.
FIXED_ORIGIN_TIMEOUTS = {
    "trycloudflare.com": 100,
}


def _proxy_ceiling(base_url: str) -> tuple[str, int] | None:
    """The host and its fixed origin timeout, or None if there is not one."""
    for host, ceiling in FIXED_ORIGIN_TIMEOUTS.items():
        if host in (base_url or "").lower():
            return host, ceiling
    return None


def reply_budget_that_cannot_arrive(base_url: str) -> str:
    """Why this deployment must produce 524s, or "" when it need not.

    The two numbers were never compared. The harness sizes a reply budget from
    the measured generation rate, and a proxy in front of the model server caps
    how long an origin may take to answer; when the first exceeds the second,
    every full-length reply is cut off, retried on a fixed backoff, and cut off
    again. Nothing said so until it had happened.

    Measured on one run, 2026-09-21: 37 retries at a fixed 120 seconds
    each - 74 minutes of a 129.6-minute run spent waiting, 57% of the wall
    clock - against a reply ceiling of 8,000 tokens on a transport that allows
    about 7,800. The margin was negative by a couple of hundred tokens and the
    run paid an hour and a quarter for it.

    Said once, before the work starts, rather than diagnosed forty times after.
    `install()` explains an individual 524 to whoever reads the log; this
    explains why they are inevitable to whoever starts the run.
    """
    found = _proxy_ceiling(base_url)
    if not found:
        return ""
    host, ceiling = found
    try:
        from app.models import (
            LARGEST_LEGITIMATE_OUTPUT_TOKENS,
            _tokens_per_second,
        )

        rate = _tokens_per_second()
        needed = LARGEST_LEGITIMATE_OUTPUT_TOKENS / rate if rate else 0.0
    except Exception:  # noqa: BLE001 - a warning must never fail a run
        logger.debug("Could not size the reply budget", exc_info=True)
        return ""
    if not needed or needed <= ceiling:
        return ""
    affordable = int(ceiling * rate)
    return (
        f"The model server is reached through {host}, which cuts off any reply "
        f"taking longer than about {ceiling}s and does not let that be changed. "
        f"This deployment's largest legitimate reply is "
        f"{LARGEST_LEGITIMATE_OUTPUT_TOKENS:,} tokens, which at the configured "
        f"{rate:.0f} tokens/second needs {needed:.0f}s - so a full-length answer "
        "cannot arrive, and the client will retry it on a fixed backoff and "
        "lose the same way. About "
        f"{affordable:,} tokens is all that fits. Either put the model server "
        "somewhere without a fixed origin timeout, or accept that long answers "
        "will be truncated and size the reply budget for it."
    )


__all__ = [
    "FIXED_ORIGIN_TIMEOUTS",
    "PROXY_ORIGIN_ERRORS",
    "install",
    "reply_budget_that_cannot_arrive",
]
