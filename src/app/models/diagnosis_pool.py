"""The diagnosis's requests asked side by side, as many at once as the model's server really serves (owner, 2026-11-27).

Owner, in their words: "if the model supports more parallel request run the diagnosis parallely". The tool and
reasoning diagnosis (`diagnostics`) asked its forty-odd requests one after another, and the deep diagnosis
(`deep_diagnosis`) asked each guide's few tries as a batch of its own, the next only when the last had ended, so on a
pool of two servers with two slots each most slots sat idle; and none of its requests named a session, so a balancer
in front of several servers (olla) placed them all by the same opening bytes.

- **How many at once** (`width`): the slots the server reports (`server_profile`: behind a balancer, the sum over the
  endpoints serving the model), less the model calls live runs have in flight on that server now
  (`call_gate.in_flight_on`), never above `HARNESS_MAX_PARALLEL`, and never fewer than one; one where the server says
  nothing of its slots. Asked again each time a request ends, so a run that starts calling takes its slots back. A
  hosted model: at most `HOSTED_AT_ONCE`.
- **Each request its own session** (`handle`): a fresh value of the session header (`session_header`) on every
  request to a self-hosted server, so a balancer spreads them.
- **Results as a serial run's** (`side_by_side`): in the order the jobs were given, whatever order they end in; a job
  that raises leaves its exception in its place and never loses the others'.
- **What company spoils** (the speed and cache probes of `speed_profile`) is not asked here: those run alone.
- **A hosted model's spend** (`handle`): every reply's tokens are priced (`cost_tracker.price_for`; an unpriced model
  at the dearest rate in the table, the safe side for a ceiling), and once `DIAGNOSIS_MAX_COST_USD` (default 1 USD)
  is spent, the requests not yet sent are not sent: they end "not measured" (`server_fault`), never as the model's
  failures.
- **Progress** (`reporting`): a callback told how many of a batch have been answered, for the settings page.
"""
from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import threading
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any, Callable, Iterator, Sequence, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: At most this many diagnosis requests at once to a hosted model: its rate limits, not its slots, bound it.
HOSTED_AT_ONCE = 2
#: What a hosted model's diagnosis may spend, unless `DIAGNOSIS_MAX_COST_USD` says otherwise (design 4.10 proposal).
DEFAULT_COST_CEILING_USD = 1.0
#: An unpriced hosted model's tokens are counted at the dearest rate in the price table (USD per million tokens).
_DEAREST = (10.0, 50.0)


class CeilingReached(RuntimeError):
    """A hosted model's diagnosis spent its ceiling: the request was not sent, so it is not measured."""

    not_measured = "the diagnosis's cost ceiling was reached"


def _is_hosted(model: Any) -> bool:
    base = str(getattr(model, "openai_api_base", "") or "")
    if not base:
        return False
    try:
        from app.models.endpoints import is_self_hosted

        return not is_self_hosted(base)
    except Exception:  # noqa: BLE001
        return False


def _most_parallel() -> int:
    raw = os.environ.get("HARNESS_MAX_PARALLEL", "").strip()
    try:
        return max(1, int(raw)) if raw else 6
    except ValueError:
        return 6


def width(model: Any = None) -> int:
    """How many diagnosis requests may be in flight at once now. Never raises."""
    try:
        if _is_hosted(model):
            return max(1, min(HOSTED_AT_ONCE, _most_parallel()))
        from app.models import server_profile

        profile = server_profile.current()
        slots = getattr(profile, "slots", None)
        if not isinstance(slots, int) or slots < 1:
            return 1
        from app.models.call_gate import in_flight_on

        busy = in_flight_on(str(getattr(model, "openai_api_base", "") or ""))
        return max(1, min(slots - busy, _most_parallel()))
    except Exception:  # noqa: BLE001 - one at a time is always safe
        return 1


#: The callback told of each batch's progress (`reporting`); None when no one asks.
_PROGRESS: contextvars.ContextVar[Callable[[int, int], None] | None] = contextvars.ContextVar(
    "diagnosis_progress", default=None)


@contextlib.contextmanager
def reporting(callback: Callable[[int, int], None]) -> Iterator[None]:
    """Within this block, each batch tells `callback(answered, of)` as its requests end."""
    token = _PROGRESS.set(callback)
    try:
        yield
    finally:
        _PROGRESS.reset(token)


def side_by_side(jobs: Sequence[Callable[[], T]], at_once: int | Callable[[], int] | None = None,
                 model: Any = None) -> list[T | BaseException]:
    """Each of `jobs` run, up to `at_once` together (a number, or asked again as each ends; `width(model)` when
    None): their results in the jobs' order; a job that raised leaves its exception in its place."""
    limit = at_once if callable(at_once) else (lambda: int(at_once)) if at_once is not None else (lambda: width(model))
    results: list[Any] = [None] * len(jobs)
    if not jobs:
        return results
    report = _PROGRESS.get()
    queue = list(enumerate(jobs))
    running: dict[Future, int] = {}
    answered = 0
    most = max(1, _most_parallel(), HOSTED_AT_ONCE)
    with ThreadPoolExecutor(max_workers=most, thread_name_prefix="diagnosis") as pool:
        while queue or running:
            room = max(1, min(int(limit() or 1), most))
            while queue and len(running) < room:
                index, job = queue.pop(0)
                running[pool.submit(contextvars.copy_context().run, job)] = index
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                index = running.pop(future)
                error = future.exception()
                results[index] = error if error is not None else future.result()
                answered += 1
            if report is not None:
                try:
                    report(answered, len(jobs))
                except Exception:  # noqa: BLE001 - narration never stops a diagnosis
                    pass
    return results


class _Ledger:
    """What a hosted model's diagnosis has spent, and whether it may send another request."""

    def __init__(self, model: Any) -> None:
        self.hosted = _is_hosted(model)
        self.spent = 0.0
        self.lock = threading.Lock()
        try:
            self.ceiling = float(os.environ.get("DIAGNOSIS_MAX_COST_USD", "") or DEFAULT_COST_CEILING_USD)
        except ValueError:
            self.ceiling = DEFAULT_COST_CEILING_USD
        self.price = self._price(model) if self.hosted else None

    @staticmethod
    def _price(model: Any) -> Any:
        from app.observability.cost_tracker import Price, price_for

        try:
            from app.models import _runtime_settings

            provider = str(_runtime_settings().llm_provider or "")
        except Exception:  # noqa: BLE001
            provider = ""
        return price_for(provider, str(getattr(model, "model_name", "") or "")) or Price(*_DEAREST)

    def may_send(self) -> None:
        if self.hosted and self.spent >= self.ceiling:
            raise CeilingReached(f"spent {self.spent:.2f} USD of {self.ceiling:.2f}")

    def count(self, response: Any) -> None:
        if not self.hosted:
            return
        data = response if isinstance(response, dict) else getattr(response, "model_dump", lambda **_: {})(warnings=False)
        usage = (data or {}).get("usage") or {}
        cost = self.price.usd_for(int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0))
        with self.lock:
            self.spent += cost


class _Completions:
    def __init__(self, model: Any, ledger: _Ledger) -> None:
        self._model, self._ledger = model, ledger

    def create(self, **payload: Any) -> Any:
        self._ledger.may_send()
        if not self._ledger.hosted:
            from app.models.session_header import session_header_name

            header = session_header_name()
            if header:
                payload["extra_headers"] = {**(payload.get("extra_headers") or {}),
                                            header: f"diagnosis:{uuid.uuid4().hex[:12]}"}
        response = self._model.root_client.chat.completions.create(**payload)
        self._ledger.count(response)
        return response


class _Handle:
    """The model as the diagnosis asks it: its own requests named a session each, a hosted model's spend counted."""

    def __init__(self, model: Any) -> None:
        self._model = model
        self._ledger = _Ledger(model)
        from types import SimpleNamespace

        self.root_client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions(model, self._ledger)))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._model, name)

    @property
    def spent(self) -> float:
        return self._ledger.spent


def handle(model: Any) -> Any:
    """`model` wrapped for the diagnosis (`_Handle`); itself when it is one already or has no OpenAI-style client."""
    if isinstance(model, _Handle):
        return model
    try:
        from app.models.diagnostics import speaks_chat_completions

        if not speaks_chat_completions(model):
            return model
    except Exception:  # noqa: BLE001
        return model
    return _Handle(model)


__all__ = ["CeilingReached", "DEFAULT_COST_CEILING_USD", "HOSTED_AT_ONCE", "handle", "reporting", "side_by_side",
           "width"]
