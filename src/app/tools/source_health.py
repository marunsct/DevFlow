"""What the lookup sources have left, and whether the page reader reads the pages answers live on (plan KS.6, LF.1297).

`loop.sh ready` asked each lookup source one question and the page reader one page, example.com - which never fails
the way an answer page does: Stack Overflow answers the reader 403 and its robots.txt refuses everything, and a GitHub
file page gives its menus first. Nor did anything say that a search engine behind the private search had stopped
answering, or how much of a day's Stack Exchange or GitHub allowance was left. Each line here is a warning, never a
block:

- one line per engine the private search names in `unresponsive_engines`;
- Stack Exchange's `quota_remaining` of `quota_max`, and its `backoff` when it asks for one;
- GitHub's search and core allowances (`/rate_limit`, which does not count against them);
- the page reader on one page of each kind a lookup reads: a file on a code host, a documentation page and a question
  with its answers.

Every query and address passes the one outbound gate (`app.tools.outbound`). No key is ever printed.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable
from urllib.parse import urlencode

#: (status, headers, body) for a GET of a URL with these headers.
Get = Callable[[str, dict[str, str]], tuple[int, dict[str, str], str]]

#: A question every engine has answers for: generic, no product's words in it.
QUESTION = "TypeError: Cannot read properties of undefined reading map"
#: One page of each kind a lookup reads, all public and long-lived.
PAGES: tuple[tuple[str, str], ...] = (
    ("a file on a code host", "https://github.com/python/cpython/blob/main/README.rst"),
    ("a documentation page", "https://docs.python.org/3/library/json.html"),
    ("a question and its answers", "https://stackoverflow.com/questions/11227809"),
)
#: Below this share of a day's allowance left, the line says it is low.
LOW_SHARE = 0.1
TIMEOUT_SECONDS = float(os.environ.get("LOOKUP_TIMEOUT", "12"))


def _get(url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], str]:
    import httpx

    with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False,
                      headers={"User-Agent": "software-harness-lookup", **headers}) as client:
        response = client.get(url)
        return response.status_code, {k.lower(): v for k, v in response.headers.items()}, response.text[:2_000_000]


def _json(body: str) -> dict[str, Any]:
    try:
        found = json.loads(body or "{}")
    except ValueError:
        return {}
    return found if isinstance(found, dict) else {}


def _no_answer(name: str, why: str) -> str:
    from app.tools.lookups import without_keys

    return without_keys(f"LOOKUPS {name}: NO ANSWER ({why}) - lookups find less; not a block")


def search_engine_lines(get: Get | None = None) -> list[str]:
    """One line per engine of the private search that did not answer a generic question; one line when all did; none
    when the private search is not configured."""
    from app.tools import outbound

    base = os.environ.get("SEARXNG_URL", "").strip().rstrip("/")
    switched = os.environ.get("WEB_SEARCH_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
    if not base or not switched:
        return []
    query = outbound.query(QUESTION, outbound.WEB_SEARCH, to="private search")
    try:
        status, _, body = (get or _get)(f"{base}/search?" + urlencode(
            {"q": query, "format": "json", "categories": "it,general"}), {"Accept": "application/json"})
    except Exception as exc:  # noqa: BLE001 - a search that cannot be asked is the answer
        return [_no_answer("private search engines", type(exc).__name__)]
    if status != 200:
        return [_no_answer("private search engines", f"it answered {status}")]
    silent = []
    for entry in _json(body).get("unresponsive_engines") or []:
        engine, why = (list(entry) + ["", ""])[:2] if isinstance(entry, (list, tuple)) else (str(entry), "")
        silent.append(_no_answer(f"private search engine {engine}", str(why or "no reason given")))
    return silent or ["LOOKUPS private search engines: every engine asked answered"]


def _low(left: int, most: int) -> str:
    return " - low; lookups find less; not a block" if most and left < most * LOW_SHARE else ""


def stack_exchange_line(get: Get | None = None) -> str:
    """Stack Exchange's requests left today for this address (or key), and its backoff when it asks for one."""
    from app.tools import lookups, outbound

    key = lookups.credential("STACKEXCHANGE_KEY")
    # The key is added after the gate, so no record ever holds it.
    url = outbound.address("https://api.stackexchange.com/2.3/info?site=stackoverflow", outbound.LOOKUP)
    url += f"&{urlencode({'key': key})}" if key else ""
    try:
        status, _, body = (get or _get)(url, {})
    except Exception as exc:  # noqa: BLE001
        return _no_answer("stack exchange allowance", type(exc).__name__)
    said = _json(body)
    if status != 200 or "quota_remaining" not in said:
        return _no_answer("stack exchange allowance", f"it answered {status}"
                          + (f": {str(said.get('error_message'))[:80]}" if said.get("error_message") else ""))
    left, most = int(said.get("quota_remaining") or 0), int(said.get("quota_max") or 0)
    return (f"LOOKUPS stack exchange allowance: {left} of {most} requests left today"
            + (f"; asks to wait {said['backoff']}s between requests" if said.get("backoff") else "")
            + _low(left, most))


def github_line(get: Get | None = None, now: Callable[[], float] = time.time) -> str:
    """GitHub's search and core allowances left (`/rate_limit` does not count against them)."""
    from app.tools import lookups, outbound

    token = lookups.credential("GITHUB_TOKEN")
    url = outbound.address("https://api.github.com/rate_limit", outbound.LOOKUP)
    try:
        status, _, body = (get or _get)(url, {"Accept": "application/vnd.github+json",
                                              **({"Authorization": f"Bearer {token}"} if token else {})})
    except Exception as exc:  # noqa: BLE001
        return _no_answer("github allowance", type(exc).__name__)
    resources = _json(body).get("resources") or {}
    if status != 200 or not isinstance(resources, dict) or "search" not in resources:
        return _no_answer("github allowance", f"it answered {status}")
    search, core = resources.get("search") or {}, resources.get("core") or {}
    left, most = int(search.get("remaining") or 0), int(search.get("limit") or 0)
    back = max(0, int(search.get("reset") or 0) - int(now())) if not left else 0
    return (f"LOOKUPS github allowance: search {left} of {most} a minute"
            + f", core {int(core.get('remaining') or 0)} of {int(core.get('limit') or 0)} an hour left"
            + (f"; search again in {back}s" if back else "") + _low(left, most))


def reader_lines(read: Callable[[str], dict[str, Any]] | None = None) -> list[str]:
    """The page reader on one page of each kind (`PAGES`): whether it gave text, and why not."""
    from app.tools import outbound, page_reader

    lines = []
    for kind, address in PAGES:
        name = f"page reader, {kind}"
        started = time.monotonic()
        try:
            page = (read or page_reader.read)(outbound.address(address, outbound.WEB_PAGE))
        except Exception as exc:  # noqa: BLE001
            lines.append(_no_answer(name, type(exc).__name__))
            continue
        took = time.monotonic() - started
        if page.get("error") or not str(page.get("text") or "").strip():
            lines.append(_no_answer(name, str(page.get("error") or "no text")[:120]))
        else:
            lines.append(f"LOOKUPS {name}: answers ({page.get('pages') or 1} page(s) of text in {took:.1f}s)")
    return lines


def lines(get: Get | None = None, read: Callable[[str], dict[str, Any]] | None = None) -> list[str]:
    """Every line of the probe, in order."""
    return [*search_engine_lines(get), stack_exchange_line(get), github_line(get), *reader_lines(read)]


__all__ = ["PAGES", "QUESTION", "github_line", "lines", "reader_lines", "search_engine_lines", "stack_exchange_line"]
