"""One outbound gate: every query that leaves the machine passes here first (plan HK.5, LF.1291).

What leaves: the harness's lookups of a stuck error (`app.tools.lookups`, called by `app.graph.stuck_lookup`), a
package name asked of its registry (`app.tools.package_registry`), and a model's own `search_the_web` query and
`read_web_page` address (`app.tools.web_search`). Before this, only the harness's lookups were cleaned, and of the
product's words only its folder, project and title were taken out; a model's search went out as it wrote it, with the
product's name and its nouns in it.

- `cleaned`: no paths (a file's own name stays), no host and port, no long tokens, no addresses, no long quoted
  values, and none of the product's private words (`private_words`): its folder, project, package and title, its name
  from the intake, and the nouns its routes are named by (from the specification and the locked interface contract) -
  each also in its plural and inside a joined identifier (`LinkShelf`, `reading_lists`). Public identifiers stay:
  error codes and versions (never a private word's shape), and the packages the project declares (`public_names`),
  even one spelled like a route's noun.
- `query` and `address`: what a caller sends, cleaned, and recorded.
- `refused_name`: a package name goes to its registry unless it is the product's own name.

Each query sent is one `outbound` record on the run's transcript (`KIND`): where it went, what was sent, and how many
private words were taken out - never which. `loop.sh effects` counts them. A caller that knows the run's workspace
passes it; otherwise the workspace of the run in progress is found from the graph's config, and outside a run only the
generic cleaning applies.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

logger = logging.getLogger(__name__)

#: The transcript record of one query that left the machine.
KIND = "outbound"

#: Where each kind of query goes, as the record names it.
LOOKUP = "lookup"
WEB_SEARCH = "web search"
WEB_PAGE = "web page"
REGISTRY = "registry"

#: Shortest private word taken out: two letters are in every error.
SHORTEST = 3

#: Route words every web product has: naming them says nothing about which product it is.
_EVERY_PRODUCT_S_WORDS = frozenset({
    "api", "apis", "app", "apps", "auth", "login", "logout", "register", "signup", "signin", "sign", "token",
    "tokens", "refresh", "health", "healthz", "ready", "status", "me", "user", "users", "account", "accounts",
    "session", "sessions", "admin", "static", "assets", "public", "docs", "openapi", "swagger", "search",
    "settings", "profile", "page", "pages", "home", "index", "new", "edit", "create", "update", "delete", "list",
    "items", "item", "web", "www", "server", "client", "backend", "frontend", "src", "test", "tests", "dashboard",
})

#: A route as a specification or a contract line names it: `GET /api/notes/{id}`, `page /dashboard`.
_A_ROUTE = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE|page)\s+(/[^\s`'\")]*)")
#: The product's name as the intake's heading gives it.
_THE_INTAKE_S_NAME = re.compile(r"^#\s*Product Intake\s*[—-]+\s*(.+?)\s*$", re.M)

# --- what is never sent, whoever sends it ----------------------------------------------------------------------------

_A_PATH = re.compile(r"(?:[A-Za-z]:)?(?:/[\w.@~+-]+){2,}/?|(?:[\w.@~+-]+/){2,}[\w.@~+-]+")
#: An address and port - an IP, localhost, or a host of three or more labels - never `store.rs:41`, a file and its line.
_A_HOST_AND_PORT = re.compile(r"\b(?:\d{1,3}(?:\.\d{1,3}){3}|localhost|[\w-]+(?:\.[\w-]+){2,}):\d{2,5}\b")
_A_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9_\-]{24,}\b|\b[0-9a-f]{8,}\b|\b[0-9a-f]{8}-[0-9a-f-]{27}\b", re.I)
_AN_ADDRESS = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_A_QUOTED_VALUE = re.compile(r"(['\"])(?:(?!\1).){41,}\1")
#: A pair of quotes with nothing left between them.
_AN_EMPTIED_QUOTE = re.compile(r"(['\"`])\s*\1")
#: A comma, colon or semicolon standing alone between spaces, or two of them in a row.
_A_LONE_MARK = re.compile(r"(?<=\s)[,:;](?=\s|$)|(?<=[,:;])\s*[,:;]")


def _parts(name: str) -> list[str]:
    """A name's words: `LinkShelf`, `link-shelf`, `link_shelf` and `Link Shelf` are all ["link", "shelf"]."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(name or ""))
    return [part.lower() for part in re.split(r"[\s_\-./]+", spaced) if part]


def _singular(word: str) -> str:
    """A plural's singular - `lists` is `list`, `entries` is `entry`, `boxes` is `box` - or the word as it is."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _spellings(name: str) -> set[str]:
    """Each way a name of several words is written in code and prose: joined, hyphenated, underscored, spaced; with
    its last word in the singular too (the pattern adds the plural back)."""
    parts = _parts(name)
    if not parts:
        return set()
    singular = [*parts[:-1], _singular(parts[-1])]
    return {joiner.join(words) for words in (parts, singular) for joiner in ("", "-", "_", " ")}


def _pattern(word: str) -> re.Pattern[str]:
    """`word` in any case, with its plural, standing alone or as one part of a joined identifier (`LinkShelfApp`,
    `reading_lists`) - never inside another word (`note` is not taken out of `notebook`)."""
    letters = "".join(f"[{c.lower()}{c.upper()}]" if c.isalpha() else (r"[\s_-]" if c in " -_" else re.escape(c))
                      for c in word)
    return re.compile(r"(?:(?<![A-Za-z0-9])|(?<=[a-z0-9])(?=[A-Z]))" + letters + r"(?:[eE]?[sS]|[iI][eE][sS])?(?![a-z0-9])")


def _protected(text: str, keep: Iterable[str]) -> tuple[str, list[str]]:
    """`text` with each public name in it swapped for a marker no private word matches, and the names in order."""
    kept: list[str] = []
    for name in sorted({k for k in keep if k and len(k) >= 2}, key=len, reverse=True):
        found = re.compile(r"(?<![\w@/.-])" + re.escape(name) + r"(?![\w-])", re.I)

        def marker(match: re.Match[str]) -> str:
            kept.append(match.group(0))
            return f"\x00{len(kept) - 1}\x00"

        text = found.sub(marker, text)
    return text, kept


def _restored(text: str, kept: list[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], text)


def without_private_words(text: str, private: Iterable[str] = (), keep: Iterable[str] = ()) -> tuple[str, int]:
    """`text` without any of `private` (longest first, in every spelling), the names in `keep` untouched; and how
    many private words were taken out."""
    text, kept = _protected(str(text or ""), keep)
    removed = 0
    spellings = {s for word in private for s in (_spellings(word) | {str(word).strip()}) if len(s) >= SHORTEST}
    for spelling in sorted(spellings, key=len, reverse=True):
        text, n = _pattern(spelling).subn(" ", text)
        removed += n
    return _restored(text, kept), removed


def cleaned(text: str, private: Iterable[str] = (), keep: Iterable[str] = (), most: int | None = None) -> str:
    """`text` as it may leave the machine (see the module's note); cut to `most` characters when given."""
    return _cleaned(text, private, keep, most)[0]


def _cleaned(text: str, private: Iterable[str], keep: Iterable[str], most: int | None) -> tuple[str, int]:
    text = " ".join(str(text or "").split())
    text = _A_PATH.sub(lambda m: m.group(0).rstrip("/").rsplit("/", 1)[-1], text)
    for pattern in (_A_HOST_AND_PORT, _AN_ADDRESS, _A_LONG_TOKEN, _A_QUOTED_VALUE):
        text = pattern.sub(" ", text)
    text, removed = without_private_words(text, private, keep)
    # What the removals left: an emptied quote (`' '`) and the punctuation that stood beside it. Measured: queries went
    # out as "path to : ' ' does not exist" and "at id ` ` answered 500", which match nothing anyone wrote.
    text = _AN_EMPTIED_QUOTE.sub(" ", text)
    text = _A_LONE_MARK.sub(" ", text)
    text = " ".join(text.split())
    return (text[:most] if most else text).strip(), removed


# --- the product's words, from its workspace -------------------------------------------------------------------------

_SOURCES = ("contract", "intake", "specification", "acceptance", "dependencies")
_PATHS = {"contract": ".harness/stack-pack.json", "intake": "docs/product_intake.md",
          "specification": "docs/technical_specification.md", "acceptance": ".harness/acceptance.json",
          "dependencies": ".harness/dependency-gate.json"}
_KNOWN: dict[tuple[str, tuple[int, ...]], tuple[list[str], list[str], set[str]]] = {}
_WORKSPACE_OF: dict[str, str] = {}


def _read(root: Path, source: str) -> str:
    try:
        return (root / _PATHS[source]).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _stamp(root: Path) -> tuple[int, ...]:
    stamps = []
    for source in _SOURCES:
        try:
            stamps.append((root / _PATHS[source]).stat().st_mtime_ns)
        except OSError:
            stamps.append(0)
    return tuple(stamps)


def _generic(word: str) -> bool:
    parts = _parts(word)
    return not parts or all(part in _EVERY_PRODUCT_S_WORDS or part.isdigit() for part in parts)


def _the_route_nouns(*texts: str) -> list[str]:
    """The words the product's routes are named by: `/api/reading-lists/{id}` gives `reading-lists`."""
    nouns: list[str] = []
    for text in texts:
        for route in _A_ROUTE.findall(text or ""):
            for segment in route.split("/"):
                if (re.fullmatch(r"[A-Za-z][A-Za-z_-]*[A-Za-z]", segment) and len(segment) >= SHORTEST
                        and not _generic(segment) and segment not in nouns):
                    nouns.append(segment)
    return nouns


def _the_declared_packages(text: str) -> set[str]:
    """The packages the dependency gate found in their registries, as the project declares them."""
    try:
        verdicts = json.loads(text) if text else {}
    except ValueError:
        return set()
    names: set[str] = set()
    for key, verdict in (verdicts.items() if isinstance(verdicts, dict) else ()):
        if isinstance(verdict, dict) and verdict.get("verdict") == "missing":
            continue
        name = str(key).partition(":")[2] or str(key)
        names.add(name)
        if "/" in name:
            names.add(name.rsplit("/", 1)[-1])
    return {n for n in names if n}


def _words_of(repo_root: str | Path) -> tuple[list[str], list[str], set[str]]:
    """(the product's own names, every private word, the public names) for one workspace; cached until a source
    changes."""
    root = Path(repo_root)
    key = (str(root), _stamp(root))
    if key in _KNOWN:
        return _KNOWN[key]
    if len(_KNOWN) > 256:
        _KNOWN.clear()
    names = [root.name]
    try:
        record = json.loads(_read(root, "contract") or "{}")
        if isinstance(record, dict):
            names += [str(record.get(field) or "") for field in ("project", "title", "package")]
    except ValueError:
        pass
    found = _THE_INTAKE_S_NAME.search(_read(root, "intake"))
    if found:
        names.append(found.group(1))
    names = [n.strip() for n in dict.fromkeys(names) if n and n.strip() and not _generic(n)]
    private = names + [n for n in _the_route_nouns(_read(root, "specification"), _read(root, "acceptance"))
                       if n not in names]
    public = _the_declared_packages(_read(root, "dependencies"))
    _KNOWN[key] = (names, private, public)
    return _KNOWN[key]


def _the_run_s_workspace() -> Path | None:
    """The workspace of the run in progress, from the graph's config; None outside a run."""
    try:
        from app.observability.transcript import _run_id_from_config

        run_id = _run_id_from_config()
        if not run_id:
            return None
        if run_id not in _WORKSPACE_OF:
            from app.server.workspaces import workspace_root

            root = workspace_root()
            found = sorted(p for pattern in (f"*/*-{run_id}", f"*-{run_id}") for p in root.glob(pattern) if p.is_dir())
            if not found:
                return None
            _WORKSPACE_OF[run_id] = str(found[0])
        return Path(_WORKSPACE_OF[run_id])
    except Exception:  # noqa: BLE001 - outside a run, or no workspace: the generic cleaning alone
        return None


def _workspace(repo_root: str | Path | None) -> Path | None:
    return Path(repo_root) if repo_root else _the_run_s_workspace()


def private_words(repo_root: str | Path | None = None) -> list[str]:
    """The product's words that never leave: its folder, project, package and title, its name from the intake, and
    its routes' nouns. Of the run in progress when `repo_root` is not given. Never raises."""
    try:
        root = _workspace(repo_root)
        return list(_words_of(root)[1]) if root is not None else []
    except Exception:  # noqa: BLE001 - nothing more than the caller's own words
        return []


def public_names(repo_root: str | Path | None = None) -> set[str]:
    """The packages the project declares, found in their registries: public, so never taken out of a query."""
    try:
        root = _workspace(repo_root)
        return set(_words_of(root)[2]) if root is not None else set()
    except Exception:  # noqa: BLE001
        return set()


# --- the gate -------------------------------------------------------------------------------------------------------

def record(channel: str, sent: str, *, to: str | Iterable[str] = "", removed: int = 0, refused: str = "") -> None:
    """One `outbound` record on the run's transcript: where a query went, what was sent, how many private words were
    taken out first. Outside a run, nothing. Never raises."""
    try:
        from app.observability.transcript import _run_id_from_config, _stage_from_config
        from app.observability.transcript import record as write

        write(_run_id_from_config(), _stage_from_config(""), KIND, channel=channel, sent=str(sent)[:600],
              to=to if isinstance(to, str) else ", ".join(to), removed=int(removed),
              **({"refused": refused} if refused else {}))
    except Exception:  # noqa: BLE001 - a record never stops a query
        logger.debug("Could not record an outbound query", exc_info=True)


def prepared(text: str, *, repo_root: str | Path | None = None, private: Iterable[str] = (),
             keep: Iterable[str] = (), most: int | None = None) -> tuple[str, int]:
    """`text` as it may leave, and how many private words were taken out: the caller's `private` words and the
    product's, `keep` and the project's packages untouched. For a caller that records once it knows what it sent."""
    return _cleaned(text, [*private, *private_words(repo_root)], {*keep, *public_names(repo_root)}, most)


def query(text: str, channel: str, *, to: str = "", repo_root: str | Path | None = None,
          private: Iterable[str] = (), keep: Iterable[str] = (), most: int | None = None) -> str:
    """`text` cleaned as it may leave the machine, recorded as sent to `to` by way of `channel`."""
    sent, removed = prepared(text, repo_root=repo_root, private=private, keep=keep, most=most)
    record(channel, sent, to=to, removed=removed)
    return sent


def address(url: str, channel: str = WEB_PAGE, *, repo_root: str | Path | None = None) -> str:
    """A web address as it may be asked for: the values of its query string without the product's words (the host
    and the path name the page, and stay), recorded."""
    try:
        parts = urlsplit(str(url or ""))
    except ValueError:
        return str(url or "")
    words, keep = private_words(repo_root), public_names(repo_root)
    removed = 0
    pairs = []
    for name, value in parse_qsl(parts.query, keep_blank_values=True):
        value, n = without_private_words(value, words, keep)
        removed += n
        pairs.append((name, " ".join(value.split())))
    sent = urlunsplit(parts._replace(query=urlencode(pairs))) if removed else str(url or "")
    record(channel, sent, to=parts.hostname or "", removed=removed)
    return sent


def refused_name(ecosystem: str, name: str, *, repo_root: str | Path | None = None) -> str:
    """Why `name` is not sent to the `ecosystem` registry - it is the product's own name - or "" when it may be;
    recorded either way. Never raises."""
    try:
        root = _workspace(repo_root)
        own = {s for n in (_words_of(root)[0] if root is not None else []) for s in _spellings(n)}
        asked = str(name or "").strip().lower()
        pieces = {asked, *(p for p in re.split(r"[/:]", asked.lstrip("@")) if p)}
        if own & {s for piece in pieces for s in _spellings(piece) | {piece}}:
            why = (f"{name!r} is this product's own name, not a published package: it is not sent to the {ecosystem} "
                   "registry. Use the project's own files for it.")
            record(REGISTRY, "", to=ecosystem, refused="the product's own name")
            return why
        record(REGISTRY, name, to=ecosystem)
        return ""
    except Exception:  # noqa: BLE001 - the lookup goes on as before
        return ""


__all__ = ["KIND", "LOOKUP", "REGISTRY", "WEB_PAGE", "WEB_SEARCH", "address", "cleaned", "prepared", "private_words",
           "public_names", "query", "record", "refused_name", "without_private_words"]
