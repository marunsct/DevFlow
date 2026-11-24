"""Each site read through its own official channel, not its HTML page (plan KS.1, LF.1294).

Measured on this machine (2026-11-24): the page reader got HTTP 403 for every Stack Overflow question - its robots.txt
disallows every path, and the site offers its API for this - while search results rank Stack Overflow first; a
GitHub issue read as HTML began "New issue, Copy link" over and over, a changelog file began with the file viewer's
controls ("Files, Expand file tree, Copy path, Blame"), and the resolution of an issue, in its closing comment, was
never reached. An address is matched to its site's channel before any HTML is fetched:

- a Stack Exchange question (`stackoverflow.com`, `superuser.com`, `askubuntu.com`, `serverfault.com`,
  `*.stackexchange.com`): the Stack Exchange API by question id - the question and its answers with their bodies,
  the accepted answer first, then by votes, each with its date, score and author (the content licence asks for the
  link and the author, so both are kept);
- a GitHub issue or pull request: the REST issue and its comments - the comment that closed it and the
  maintainers' replies first (`author_association`), with its state and the changes it links;
- a GitHub file (`/blob/<ref>/<path>`): the raw file host; `/releases`: the releases API; a repository's root: its
  README through the API;
- a package's page on npm, PyPI or crates.io: the registry's own document (`package_registry`, `docs`), never the
  HTML page.

Any other address returns None and the page reader reads it as before. Every request is one the outbound gate records
(`app.tools.outbound`, LF.1291) and carries only a public id taken from a public address; each is counted against its
source's daily cap and held when the source refuses (`lookups.guarded`, `source_breaker`). The text is the site's own
(Markdown, or HTML turned into text with code kept as fenced blocks, `page_reader.main_text`), defanged by the caller.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote, urlencode, urlsplit

#: Characters of a question's or an issue's own text: the asker's words, which are not the answer.
MOST_ASKED = 1_200
#: Characters of one answer or comment.
MOST_REPLY = 2_500
#: Answers or comments kept after the resolution.
MOST_REPLIES = 3
#: GitHub's word for a commenter who maintains the repository.
MAINTAINERS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})

#: The Stack Exchange sites known by their own host; any `<name>.stackexchange.com` is its own site too.
_STACK_EXCHANGE_HOSTS = {"stackoverflow.com": "stackoverflow", "superuser.com": "superuser",
                         "askubuntu.com": "askubuntu", "serverfault.com": "serverfault",
                         "mathoverflow.net": "mathoverflow", "stackapps.com": "stackapps"}
_A_QUESTION = re.compile(r"^/(?:questions|q)/(\d+)")
_AN_ANSWER = re.compile(r"^/a/(\d+)")
_A_GITHUB_NAME = r"[A-Za-z0-9_.-]+"
_AN_ISSUE = re.compile(rf"^/({_A_GITHUB_NAME})/({_A_GITHUB_NAME})/(?:issues|pull)/(\d+)")
_A_FILE = re.compile(rf"^/({_A_GITHUB_NAME})/({_A_GITHUB_NAME})/blob/(.+)$")
_RELEASES = re.compile(rf"^/({_A_GITHUB_NAME})/({_A_GITHUB_NAME})/releases(?:/tag/([^/]+))?/?$")
_A_REPOSITORY = re.compile(rf"^/({_A_GITHUB_NAME})/({_A_GITHUB_NAME})/?$")
#: What a reply says of the change that settled the issue: a pull request, a commit, a release.
_A_LINKED_CHANGE = re.compile(
    r"https://github\.com/[\w.-]+/[\w.-]+/(?:pull|commit)/[\w]+|(?<![\w/])#\d{1,7}\b"
    r"|\b(?:fixed|resolved|released|landed|shipped)\s+in\s+v?\d+(?:\.\d+)+\S*", re.I)

#: One request: (status, body, headers) for a GET of a URL with these headers.
Fetch = Callable[[str, dict[str, str]], tuple[int, str, dict[str, str]]]


@dataclass(frozen=True)
class Read:
    """What a site's channel gave for one address."""

    url: str
    text: str
    #: The channel it came through, as a person would name it.
    via: str
    #: The reply that settles the question - the accepted answer, the closing comment - or "".
    resolution: str = ""
    #: Who gave it: "accepted answer", "maintainer", "top-voted answer", "last reply" or "".
    resolution_by: str = ""
    #: When it was given (YYYY-MM-DD), or "".
    date: str = ""
    #: "open", "closed", "answered", "unanswered" or "".
    state: str = ""
    #: The changes the replies link to: pull requests, commits, "fixed in x.y".
    linked: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"url": self.url, "text": self.text, "via": self.via, "resolution": self.resolution,
                "resolution_by": self.resolution_by, "date": self.date, "state": self.state,
                "linked": list(self.linked)}


def _day(stamp: Any) -> str:
    if isinstance(stamp, (int, float)) and stamp > 0:
        return time.strftime("%Y-%m-%d", time.gmtime(int(stamp)))
    return str(stamp or "")[:10]


def _html_text(body: str) -> str:
    from app.tools.page_reader import main_text

    return main_text(f"<div>{body or ''}</div>")[0]


def _cut(text: str, most: int) -> str:
    from app.tools.page_reader import cut_at_a_block

    return cut_at_a_block(str(text or "").strip(), most)


def _json(body: str) -> Any:
    try:
        return json.loads(body or "null")
    except ValueError:
        return None


def _get(source: str, fetch: Fetch | None) -> Fetch:
    """A request to `source`, recorded by the outbound gate, counted and held on a refusal (`lookups.guarded`)."""
    from app.tools import lookups, outbound

    guarded = lookups.guarded(source, fetch)
    key = lookups.credential("STACKEXCHANGE_KEY") if source == "stack exchange" else ""

    def call(url: str, headers: dict[str, str]) -> tuple[int, str, dict[str, str]]:
        # Recorded as it leaves, the key added after: a key never reaches the transcript.
        sent = outbound.address(url, outbound.WEB_PAGE)
        return guarded(sent + (("&" if "?" in sent else "?") + urlencode({"key": key}) if key else ""), headers)

    return call


def _github_headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    from app.tools.lookups import credential

    token = credential("GITHUB_TOKEN")
    return {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {})}


# --- Stack Exchange ---------------------------------------------------------------------------------------------------

def _site_of(host: str) -> str:
    host = host.lower().removeprefix("www.")
    if host in _STACK_EXCHANGE_HOSTS:
        return _STACK_EXCHANGE_HOSTS[host]
    if host.endswith(".stackexchange.com") and host.count(".") == 2 and not host.startswith(("api.", "meta.")):
        return host.split(".")[0]
    return ""


def _stack_exchange_params(site: str, **more: str) -> str:
    return urlencode({"site": site, "filter": "withbody", **more})


def answers_in_order(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A question's answers as a person reads them: the accepted one first, then by votes, newer before older at a
    tie."""
    return sorted((a for a in answers if isinstance(a, dict)),
                  key=lambda a: (not a.get("is_accepted"), -int(a.get("score") or 0), -int(a.get("creation_date") or 0)))


def _who(item: dict[str, Any]) -> str:
    owner = item.get("owner") or item.get("user") or {}
    return str(owner.get("display_name") or owner.get("login") or "someone") if isinstance(owner, dict) else "someone"


def stack_exchange_question(site: str, question_id: str, fetch: Fetch | None = None) -> Read | dict[str, str]:
    """A question and its answers through the Stack Exchange API; {"error": ...} when the site has no such question."""
    get = _get("stack exchange", fetch)
    status, body, _ = get(f"https://api.stackexchange.com/2.3/questions/{question_id}?"
                          + _stack_exchange_params(site), {})
    questions = ((_json(body) or {}).get("items") or []) if status == 200 else []
    if not questions:
        return {"error": f"Stack Exchange has no question {question_id} on {site} (it answered {status})."}
    question = questions[0]
    status, body, _ = get(f"https://api.stackexchange.com/2.3/questions/{question_id}/answers?"
                          + _stack_exchange_params(site, sort="votes", order="desc", pagesize="10"), {})
    answers = answers_in_order(((_json(body) or {}).get("items") or []) if status == 200 else [])
    import html

    link = str(question.get("link") or f"https://{site}.com/questions/{question_id}")
    lines = [f"# {html.unescape(str(question.get('title') or ''))}",
             f"Question on {site}, asked {_day(question.get('creation_date'))}, score {question.get('score') or 0}, "
             f"by {_who(question)}: {link}",
             _cut(_html_text(str(question.get("body") or "")), MOST_ASKED)]
    for answer in answers[:1 + MOST_REPLIES]:
        said = "Accepted answer" if answer.get("is_accepted") else "Answer"
        lines += ["", f"## {said}, {_day(answer.get('creation_date'))}, score {answer.get('score') or 0}, "
                      f"by {_who(answer)}", _cut(_html_text(str(answer.get("body") or "")), MOST_REPLY)]
    first = answers[0] if answers else {}
    return Read(url=link, text="\n".join(lines).strip(), via="Stack Exchange API",
                resolution=_cut(_html_text(str(first.get("body") or "")), MOST_REPLY) if first else "",
                resolution_by=("accepted answer" if first.get("is_accepted") else "top-voted answer") if first else "",
                date=_day(first.get("creation_date")) if first else _day(question.get("creation_date")),
                state="answered" if answers else "unanswered")


def _stack_exchange(url: str, fetch: Fetch | None) -> Read | dict[str, str] | None:
    parts = urlsplit(url)
    site = _site_of(parts.hostname or "")
    if not site:
        return None
    found = _A_QUESTION.match(parts.path)
    if found:
        return stack_exchange_question(site, found.group(1), fetch)
    found = _AN_ANSWER.match(parts.path)
    if not found:
        return None
    status, body, _ = _get("stack exchange", fetch)(
        f"https://api.stackexchange.com/2.3/answers/{found.group(1)}?" + _stack_exchange_params(site), {})
    items = ((_json(body) or {}).get("items") or []) if status == 200 else []
    if not items or not items[0].get("question_id"):
        return {"error": f"Stack Exchange has no answer {found.group(1)} on {site} (it answered {status})."}
    return stack_exchange_question(site, str(items[0]["question_id"]), fetch)


# --- GitHub ----------------------------------------------------------------------------------------------------------

def _reactions(comment: dict[str, Any]) -> int:
    reactions = comment.get("reactions") or {}
    return int(reactions.get("total_count") or 0) if isinstance(reactions, dict) else 0


def the_resolution(issue: dict[str, Any], comments: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    """The comment that settles an issue and who gave it: for a closed issue the maintainer's comment nearest its
    closing (else the last before it), for an open one the latest maintainer's reply, else the most-endorsed reply;
    ({}, "") when it has none."""
    replies = [c for c in comments if isinstance(c, dict) and str(c.get("body") or "").strip()]
    if not replies:
        return {}, ""
    maintained = [c for c in replies if str(c.get("author_association") or "").upper() in MAINTAINERS]
    closed_at = str(issue.get("closed_at") or "")
    if str(issue.get("state") or "") == "closed" and closed_at:
        before = [c for c in replies if str(c.get("created_at") or "") <= closed_at]
        by_maintainer = [c for c in before if c in maintained]
        if by_maintainer:
            return by_maintainer[-1], "maintainer"
        if before:
            return before[-1], "last reply before it closed"
    if maintained:
        return maintained[-1], "maintainer"
    return max(replies, key=lambda c: (_reactions(c), str(c.get("created_at") or ""))), "most-endorsed reply"


def _linked(*texts: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(m.group(0) for text in texts for m in _A_LINKED_CHANGE.finditer(text or "")))[:6]


def github_issue(owner: str, repository: str, number: str, fetch: Fetch | None = None) -> Read | dict[str, str]:
    """An issue or pull request with its comments through GitHub's REST API, the resolution first."""
    get = _get("github", fetch)
    base = f"https://api.github.com/repos/{quote(owner)}/{quote(repository)}/issues/{quote(number)}"
    status, body, _ = get(base, _github_headers())
    issue = _json(body) if status == 200 else None
    if not isinstance(issue, dict):
        return {"error": f"GitHub has no issue {owner}/{repository}#{number} (it answered {status})."}
    status, body, _ = get(f"{base}/comments?per_page=100", _github_headers())
    comments = [c for c in (_json(body) or []) if isinstance(c, dict)] if status == 200 else []
    resolution, by = the_resolution(issue, comments)
    state = str(issue.get("state") or "")
    reason = str(issue.get("state_reason") or "")
    merged = (issue.get("pull_request") or {}).get("merged_at") if isinstance(issue.get("pull_request"), dict) else None
    head = f"# {issue.get('title') or ''} ({state}" + (f", {reason}" if reason else "") + (
        f", closed {_day(issue.get('closed_at'))}" if issue.get("closed_at") else "") + (
        f", merged {_day(merged)}" if merged else "") + ")"
    lines = [head, f"{'Pull request' if issue.get('pull_request') else 'Issue'} {owner}/{repository}#{number}, opened "
                   f"{_day(issue.get('created_at'))} by {_who(issue)}, {len(comments)} comment(s): "
                   f"{issue.get('html_url') or ''}",
             _cut(str(issue.get("body") or ""), MOST_ASKED)]
    if resolution:
        lines += ["", f"## The resolution: {by}, {_who(resolution)} ({resolution.get('author_association') or ''}), "
                      f"{_day(resolution.get('created_at'))}", _cut(str(resolution.get("body") or ""), MOST_REPLY)]
    others = [c for c in comments if c is not resolution and str(c.get("body") or "").strip()]
    others.sort(key=lambda c: (str(c.get("author_association") or "").upper() not in MAINTAINERS, -_reactions(c)))
    for comment in others[:MOST_REPLIES]:
        lines += ["", f"## Reply by {_who(comment)} ({comment.get('author_association') or ''}), "
                      f"{_day(comment.get('created_at'))}", _cut(str(comment.get("body") or ""), MOST_REPLY // 2)]
    linked = _linked(str(resolution.get("body") or ""), *(str(c.get("body") or "") for c in comments[-5:]))
    if linked:
        lines += ["", "Linked changes: " + ", ".join(linked)]
    return Read(url=str(issue.get("html_url") or f"https://github.com/{owner}/{repository}/issues/{number}"),
                text="\n".join(lines).strip(), via="GitHub REST API",
                resolution=_cut(str(resolution.get("body") or ""), MOST_REPLY) if resolution else "",
                resolution_by=by, date=_day((resolution or issue).get("created_at") or issue.get("updated_at")),
                state=state, linked=linked)


def _github_file(owner: str, repository: str, rest: str, fetch: Fetch | None) -> Read | dict[str, str]:
    raw = f"https://raw.githubusercontent.com/{quote(owner)}/{quote(repository)}/{quote(rest, safe='/@')}"
    status, body, _ = _get("github files", fetch)(raw, {"Accept": "text/plain"})
    if status != 200:
        return {"error": f"The file {owner}/{repository}/{rest} could not be read (it answered {status})."}
    return Read(url=f"https://github.com/{owner}/{repository}/blob/{rest}", text=body.strip(), via="GitHub raw file")


def _github_releases(owner: str, repository: str, tag: str, fetch: Fetch | None) -> Read | dict[str, str]:
    base = f"https://api.github.com/repos/{quote(owner)}/{quote(repository)}/releases"
    status, body, _ = _get("github", fetch)(f"{base}/tags/{quote(tag)}" if tag else f"{base}?per_page=5",
                                            _github_headers())
    found = _json(body) if status == 200 else None
    releases = [found] if isinstance(found, dict) else [r for r in (found or []) if isinstance(r, dict)]
    if not releases:
        return {"error": f"GitHub lists no release of {owner}/{repository}{f' tagged {tag}' if tag else ''}."}
    lines = []
    for release in releases:
        lines += [f"## {release.get('name') or release.get('tag_name') or ''} ({release.get('tag_name') or ''}, "
                  f"{_day(release.get('published_at'))})", _cut(str(release.get("body") or ""), MOST_REPLY), ""]
    return Read(url=f"https://github.com/{owner}/{repository}/releases" + (f"/tag/{tag}" if tag else ""),
                text="\n".join(lines).strip(), via="GitHub REST API", date=_day(releases[0].get("published_at")))


def _github_readme(owner: str, repository: str, fetch: Fetch | None) -> Read | dict[str, str]:
    status, body, _ = _get("github", fetch)(
        f"https://api.github.com/repos/{quote(owner)}/{quote(repository)}/readme",
        _github_headers("application/vnd.github.raw+json"))
    if status != 200 or not body.strip():
        return {"error": f"GitHub has no README for {owner}/{repository} (it answered {status})."}
    return Read(url=f"https://github.com/{owner}/{repository}", text=body.strip(), via="GitHub REST API")


def _github(url: str, fetch: Fetch | None) -> Read | dict[str, str] | None:
    parts = urlsplit(url)
    if (parts.hostname or "").lower().removeprefix("www.") != "github.com":
        return None
    path = parts.path
    if found := _AN_ISSUE.match(path):
        return github_issue(*found.groups(), fetch=fetch)
    if found := _A_FILE.match(path):
        return _github_file(found.group(1), found.group(2), found.group(3), fetch)
    if found := _RELEASES.match(path):
        return _github_releases(found.group(1), found.group(2), found.group(3) or "", fetch)
    if (found := _A_REPOSITORY.match(path)) and found.group(1) not in {"orgs", "topics", "search", "settings"}:
        return _github_readme(found.group(1), found.group(2), fetch)
    return None


# --- the package registries ----------------------------------------------------------------------------------------

_REGISTRY_PAGES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("npmjs.com", re.compile(r"^/package/((?:@[\w.-]+/)?[\w.-]+)"), "npm"),
    ("pypi.org", re.compile(r"^/project/([\w.-]+)"), "pypi"),
    ("crates.io", re.compile(r"^/crates/([\w-]+)"), "crates"),
)


def _registry(url: str) -> Read | dict[str, str] | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    for site, page, ecosystem in _REGISTRY_PAGES:
        found = page.match(parts.path) if host == site else None
        if not found:
            continue
        from app.tools import docs, package_registry

        name = found.group(1)
        facts = package_registry.look_up(ecosystem, name)
        if facts.get("error") or facts.get("status"):
            return {"error": facts.get("error") or f"The {ecosystem} registry has no package {name!r}."}
        readme = docs.read(name, "", ecosystem)
        lines = [f"# {name} {facts.get('version') or ''}".rstrip(), str(facts.get("description") or ""),
                 *(f"Home: {home}" for home in facts.get("homes") or []), "", str(readme.get("excerpt") or "")]
        return Read(url=url, text="\n".join(line for line in lines if line is not None).strip(),
                    via=f"the {ecosystem} registry")
    return None


# --- the router ------------------------------------------------------------------------------------------------------

def read(url: str, *, fetch: Fetch | None = None) -> Read | dict[str, str] | None:
    """`url` read through its site's official channel: a `Read`, {"error": ...} when the channel has no such item or
    refused, or None when the address has no channel here and its page is read as a page. Never raises."""
    from app.tools.source_breaker import Refused

    url = str(url or "").strip()
    if not url.startswith("https://") and not url.startswith("http://"):
        return None
    try:
        for reader in (_stack_exchange, _github):
            found = reader(url, fetch)
            if found is not None:
                return found
        return _registry(url)
    except Refused as refused:
        return {"error": f"{refused.source} refused the request until {time.strftime('%H:%M UTC', time.gmtime(refused.until))}"
                         " - it is not asked again before then.", "refused": refused.source}
    except Exception as exc:  # noqa: BLE001 - an unreadable channel is an answer, not a crash
        return {"error": f"The page could not be read through its site's own channel ({type(exc).__name__})."}


def has_a_channel(url: str) -> bool:
    """Whether `url` is read through its site's channel rather than as a page."""
    parts = urlsplit(str(url or ""))
    host = (parts.hostname or "").lower().removeprefix("www.")
    if _site_of(host):
        return bool(_A_QUESTION.match(parts.path) or _AN_ANSWER.match(parts.path))
    if host == "github.com":
        return bool(_AN_ISSUE.match(parts.path) or _A_FILE.match(parts.path) or _RELEASES.match(parts.path)
                    or _A_REPOSITORY.match(parts.path))
    return any(host == site and page.match(parts.path) for site, page, _ in _REGISTRY_PAGES)


__all__ = ["MAINTAINERS", "Read", "answers_in_order", "github_issue", "has_a_channel", "read",
           "stack_exchange_question", "the_resolution"]
