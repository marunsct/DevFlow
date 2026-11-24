"""Documentation for the release a project runs, read through the one outbound gate (plans HK.7, HK.9; LF.1302-1303).

`app.tools.docs` reads a library's documentation as it is published today, and `lookups.context7` asks Context7 with
no version: both answer for the newest release, whatever the project installed. Here a question about one release
of one library is answered from, in this order:

1. **Context7 with the version written into the library id** (`/owner/repo/<version>`). Only a version Context7
   lists for that library is asked: asked for one it does not hold, it silently answers for the nearest or the latest
   (`reports/research/2026-11-24-agents-that-work-like-a-team.md`, section (c)), so an unlisted release is not asked
   at all. The listed tag equal to the release here is chosen, else the nearest on the same release line.
2. **The library's own documentation** (`docs.read`: its `llms.txt` index, else its registry's README). It is
   published for the newest release, so it is read only when the release here is on the newest's line, and labelled
   with the release it describes.

Every request leaves through the gate (`app.tools.outbound`): Context7's query cleaned and recorded, its requests
counted and held by its breaker (`lookups.guarded`), each documentation address recorded. Only public names leave -
a package, a version, a generic question - so an answer is kept in `DATA_DIR/versioned-docs` per library, release
and question for every run and tenant: an answer for `KEPT_DAYS`, a true "nothing found" for `NOTHING_FOUND_DAYS`, a
refusal or a failure never.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: Days an answer is kept for one library, release and question: a release's documentation does not move.
KEPT_DAYS = 30
#: Days "nothing found" is kept.
NOTHING_FOUND_DAYS = 1
#: Characters of one answer's excerpt.
MOST_EXCERPT = 3_000

#: (status, body[, headers]) of a GET with these headers: the lookups' fetch (`lookups.Fetch`).
Fetch = Callable[..., Any]
#: (status, text, content type) of a documentation address: the docs' fetch (`docs.Fetch`).
DocsFetch = Callable[[str], tuple[int, str, str]]


def numbers(version: Any) -> tuple[int, ...]:
    found = re.search(r"(\d+(?:\.\d+)*)", str(version or ""))
    return tuple(int(part) for part in found.group(1).split(".")) if found else ()


def line(version: Any) -> tuple[int, ...]:
    """A version's release line: its major, or `0.minor` while the major is 0 (semantic versioning's own rule)."""
    found = numbers(version)
    if not found:
        return ()
    return found[:2] if found[0] == 0 and len(found) > 1 else found[:1]


def same_line(one: Any, other: Any) -> bool:
    return bool(line(one)) and line(one) == line(other)


# --- the cache --------------------------------------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    folder = Path(os.environ.get("DATA_DIR") or "data") / "versioned-docs"
    return folder / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".json")


def _cached(key: str) -> dict[str, Any] | None:
    try:
        kept = json.loads(_cache_path(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    answer = kept.get("answer") if isinstance(kept, dict) else None
    if not isinstance(answer, dict):
        return None
    days = KEPT_DAYS if answer.get("excerpt") else NOTHING_FOUND_DAYS
    return answer if time.time() - float(kept.get("at") or 0) <= days * 86_400 else None


def _keep(key: str, answer: dict[str, Any]) -> None:
    try:
        path = _cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"at": time.time(), "key": key, "answer": answer}), encoding="utf-8")
    except OSError:
        pass


# --- 1. Context7, pinned to the release -------------------------------------------------------------------------------

class _NotAnswered(Exception):
    """A source refused, was capped or could not be reached: no answer, and none to keep."""


def _pinned_tag(versions: list[Any], version: str) -> str:
    """The tag Context7 lists for `version`: the equal one, else the nearest on its line; "" when it lists none."""
    tags = [str(v) for v in versions or [] if numbers(v)]
    wanted = numbers(version)
    equal = [t for t in tags if numbers(t) == wanted]
    if equal:
        return equal[0]
    on_the_line = [t for t in tags if same_line(t, version)]
    if not on_the_line:
        return ""
    return min(on_the_line, key=lambda t: tuple(abs(a - b) for a, b in zip(numbers(t) + (0,) * 4, wanted + (0,) * 4)))


def _context7_excerpt(said: dict[str, Any]) -> str:
    """Context7's answer as text: each explanation, each example as a fenced block."""
    pieces = [" ".join(str(i.get("content") or "").split()) for i in (said.get("infoSnippets") or [])
              if isinstance(i, dict)]
    for snippet in said.get("codeSnippets") or []:
        if not isinstance(snippet, dict):
            continue
        codes = [c for c in snippet.get("codeList") or [] if isinstance(c, dict) and c.get("code")]
        if not codes:
            continue
        language = str(codes[0].get("language") or "")
        title = str(snippet.get("codeTitle") or "").strip()
        pieces.append((f"{title}:\n" if title else "") + f"```{language}\n{str(codes[0]['code']).rstrip()}\n```")
    return "\n\n".join(p for p in pieces if p.strip())


def context7_pinned(package: str, version: str, question: str, *, fetch: Fetch | None = None) -> dict[str, Any] | None:
    """Context7's documentation of `package` at the release `version` about `question`; None when it lists no such
    release or found nothing. Raises `_NotAnswered` when it refused or could not be reached."""
    from urllib.parse import urlencode

    from app.tools import lookups, outbound, source_breaker

    if not package or not numbers(version):
        return None
    sent = outbound.query(question, outbound.LOOKUP, to="context7", keep=[package])
    send = lookups.guarded("context7", fetch)
    key = lookups.credential("CONTEXT7_API_KEY")
    headers = {"Accept": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})}
    try:
        status, body, _ = send("https://context7.com/api/v2/libs/search?"
                               + urlencode({"libraryName": package, "query": sent}), headers)
        found = (json.loads(body or "{}").get("results") or []) if status == 200 else []
        chosen = next((r for r in found if isinstance(r, dict) and str(r.get("id") or "").startswith("/")), None)
        if chosen is None:
            return None
        tag = _pinned_tag(list(chosen.get("versions") or []), version)
        if not tag:
            return None
        library = f"{chosen['id'].rstrip('/')}/{tag}"
        status, body, _ = send("https://context7.com/api/v2/context?"
                               + urlencode({"libraryId": library, "query": sent, "type": "json"}), headers)
        excerpt = _context7_excerpt(json.loads(body or "{}")) if status == 200 else ""
    except (source_breaker.Refused, lookups.Capped, OSError, RuntimeError) as error:
        raise _NotAnswered(str(error)) from error
    except ValueError:
        return None
    if not excerpt.strip():
        return None
    return {"source": f"Context7 {library}", "url": f"https://context7.com{library}", "release": tag,
            "excerpt": excerpt}


# --- 2. the library's own documentation, for the newest release --------------------------------------------------------

def _gated(fetch: DocsFetch | None) -> DocsFetch:
    """The docs' fetch with each address passed through the gate first (recorded as a page read)."""
    from app.tools import docs, outbound

    def call(url: str) -> tuple[int, str, str]:
        return (fetch or docs._fetch)(outbound.address(url, outbound.WEB_PAGE))  # noqa: SLF001 - the one docs fetch

    return call


def official(package: str, version: str, newest: str, topic: str, ecosystem: str = "", *,
             fetch: DocsFetch | None = None) -> dict[str, Any] | None:
    """The library's own documentation about `topic`, when the release here is on the newest's line (what that
    documentation describes); None otherwise, or when it says nothing about the topic."""
    from app.tools import docs

    if not docs.enabled() or not same_line(version, newest):
        return None
    try:
        answer = docs.read(package, topic, ecosystem, fetch=_gated(fetch))
    except Exception as error:  # noqa: BLE001 - unread documentation is no answer
        raise _NotAnswered(str(error)) from error
    if not isinstance(answer, dict) or answer.get("error") or not str(answer.get("excerpt") or "").strip():
        return None
    sources = answer.get("source") or []
    return {"source": f"{package}'s own documentation", "url": ", ".join(map(str, sources))[:300],
            "release": str(newest), "excerpt": str(answer["excerpt"])}


# --- the answer ---------------------------------------------------------------------------------------------------------

def read(package: str, version: str, question: str, *, ecosystem: str = "", newest: str = "", topic: str = "",
         fetch: Fetch | None = None, docs_fetch: DocsFetch | None = None) -> dict[str, Any]:
    """The documentation of `package` at release `version` about `question`, from the first source that holds that
    release: {"source", "url", "release", "excerpt"}, or {} for none. Kept per library, release and question.
    Never raises."""
    from app.tools.untrusted_text import defanged

    key = json.dumps([ecosystem, package, version, question, topic or question])
    kept = _cached(key)
    if kept is not None:
        return kept if kept.get("excerpt") else {}
    answered_by_all = True
    for source in (lambda: context7_pinned(package, version, question, fetch=fetch),
                   lambda: official(package, version, newest, topic or question, ecosystem, fetch=docs_fetch)):
        try:
            found = source()
        except _NotAnswered as error:
            logger.info("Documentation of %s %s not read: %s", package, version, error)
            answered_by_all = False
            continue
        except Exception:  # noqa: BLE001 - the next source
            logger.debug("Documentation of %s %s could not be read", package, version, exc_info=True)
            answered_by_all = False
            continue
        if found:
            from app.tools.page_reader import cut_at_a_block

            found = {**found, "excerpt": cut_at_a_block(defanged(found["excerpt"]), MOST_EXCERPT)}
            _keep(key, found)
            return found
    if answered_by_all:
        _keep(key, {"excerpt": ""})
    return {}


__all__ = ["KEPT_DAYS", "MOST_EXCERPT", "NOTHING_FOUND_DAYS", "context7_pinned", "line", "numbers", "official", "read",
           "same_line"]
