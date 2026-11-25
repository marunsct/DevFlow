"""Which specialist's domain a product file is in, from its path alone (plan SK.1).

The builders are role specialists, and the specialists' advice is per domain: the database specialist's on records,
fields and keys, the UI/UX specialist's on the page, the backend specialist's on the service, the security
specialist's on sign-in and who may do what. A work order is planned by role, so its files can be in another role's
domain. Measured on a medium run (thorough delivery, a Python service with a React page): only the backend and
testing builders ran; the backend builder wrote the database models with no database guidance and none of the
database specialist's adopted items in its request, and the models came out with integer ids, no timestamps and no
indexes - which the database specialist then reported as not built.

So each file is read for its domain, the way a person reads a tree they have never seen: a stylesheet, a page
template or a component is the interface; `models/`, `db.py`, `migrations/` or a `.sql` file is the data layer;
`routes/`, `api/`, `controllers/`, `server.js` is the service; `auth`, `login`, `session`, `password`, `token` is
sign-in and authorisation. The words are the generic vocabulary of every stack; a tool's own file names (an ORM's
schema file, a migration tool's folder) and server-side template engines are in `app.plugins.seed`. Tests,
documents, build configuration and vendored files have no domain (`app.analysis.file_kinds`).

A path can be in more than one domain (`routes/auth.py` is the service and sign-in). The primary domain - the one
whose word comes last in the path, the file's own name before its folders - decides which role owns the file.
Security is never an owner: it is a concern on top of another domain, so its advice and guidance ride along.
"""

from __future__ import annotations

import fnmatch
import re
from collections import Counter
from typing import Iterable, Literal

from app.analysis.file_kinds import SCRIPTED_MARKUP_SUFFIXES, classify_file, is_presentation

Domain = Literal["interface", "data", "service", "security"]

#: The domains, in the order a section lists them.
DOMAINS: tuple[Domain, ...] = ("data", "service", "interface", "security")

#: The specialist role whose advice and guidance belong to each domain.
ADVICE_ROLE: dict[str, str] = {
    "interface": "ui_ux", "data": "database", "service": "backend", "security": "security_reliability",
}
#: The roles that own the files of a domain, as builders. Security owns none (see the module's docstring).
OWNER: dict[str, str] = {"interface": "ui_ux", "data": "database", "service": "backend"}
#: The builder roles a work order may be moved between by its files' domain.
BUILDER_ROLES = frozenset(OWNER.values())

#: Component files of the page frameworks: markup and script together, in a script language's own suffix.
_COMPONENT_SUFFIXES = (".jsx", ".tsx")

_INTERFACE_WORDS = frozenset({
    "frontend", "ui", "components", "component", "pages", "page", "screens", "screen", "layouts", "layout",
    "widgets", "widget", "templates", "template", "styles", "style", "stylesheet", "theme", "static", "public",
})
_DATA_WORDS = frozenset({
    "models", "model", "entities", "entity", "schema", "schemas", "db", "database", "databases", "migrations",
    "migration", "migrate", "repositories", "repository", "repo", "repos", "store", "stores", "storage",
    "persistence", "orm", "dao", "daos", "crud", "tables", "table", "seeds", "sql", "sqlite",
})
_SERVICE_WORDS = frozenset({
    "api", "apis", "routes", "route", "router", "routers", "routing", "controllers", "controller", "handlers",
    "handler", "endpoints", "endpoint", "server", "middleware", "middlewares", "resolvers", "resolver", "rest",
    "graphql",
})
_SECURITY_WORDS = frozenset({
    "auth", "authn", "authz", "authentication", "authorization", "authorisation", "login", "logout", "signin",
    "signup", "session", "sessions", "password", "passwords", "credential", "credentials", "token", "tokens", "jwt",
    "oauth", "permission", "permissions", "acl", "rbac", "security", "guard", "guards", "secrets",
})
#: A folder that holds only the page's side of a product with a service and a page.
_PAGE_SIDE = frozenset({"frontend"})
#: Two words that say sign-in when they stand side by side: `sign_in.py`, `SignUp.tsx`, `log-in`.
_SIGN_IN = re.compile(r"\b(?:sign|log) (?:in|up|on|out)\b")

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SPLIT = re.compile(r"[^a-z0-9]+")


def _words(path: str) -> list[str]:
    """The path's words in order, folders first: `src/userStore.ts` -> src, user, store, ts."""
    return [word for word in _SPLIT.split(_CAMEL.sub(" ", path).lower()) if word]


def _matches(path: str, globs: Iterable[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, glob) or fnmatch.fnmatch(name, glob) for glob in globs)


def _stack_tables() -> tuple[tuple[str, ...], tuple[str, ...]]:
    try:
        from app.plugins.seed import DATA_LAYER_FILES, INTERFACE_TEMPLATE_SUFFIXES

        return tuple(DATA_LAYER_FILES), tuple(INTERFACE_TEMPLATE_SUFFIXES)
    except Exception:  # noqa: BLE001 - the generic words still apply
        return (), ()


def domains_of(relative_path: str) -> tuple[Domain, ...]:
    """The domains this product file is in, its primary domain first; () for a test, document, configuration or
    vendored file, or a file whose path says nothing of its domain (`main.py`, `app.js`)."""
    path = str(relative_path or "").replace("\\", "/").strip().lstrip("./")
    if not path or classify_file(path) != "application":
        return ()
    lowered = path.lower()
    data_files, templates = _stack_tables()
    words = _words(path)
    security = bool(_SECURITY_WORDS.intersection(words) or _SIGN_IN.search(" ".join(words)))
    # A stylesheet or an image is the interface, whatever its name says: `tokens.css` holds design tokens.
    if is_presentation(lowered):
        return ("interface",)
    if lowered.endswith((*SCRIPTED_MARKUP_SUFFIXES, *_COMPONENT_SUFFIXES, *templates)):
        return ("interface", "security") if security else ("interface",)
    if lowered.endswith(".sql") or _matches(lowered, data_files):
        return ("data",)
    # By the words of the path: the last word that names a domain is the file's own (its name, then its folder).
    found: list[Domain] = []
    for word in reversed(words):
        for domain, vocabulary in (("data", _DATA_WORDS), ("service", _SERVICE_WORDS),
                                   ("interface", _INTERFACE_WORDS)):
            if word in vocabulary and domain not in found:
                found.append(domain)  # type: ignore[arg-type]
    # Everything under a page's own folder is the page's, its calls to the service included (`frontend/src/api.ts`).
    if _PAGE_SIDE.intersection(words) and "interface" in found:
        found.remove("interface")
        found.insert(0, "interface")
    if security:
        found.append("security")
    return tuple(found)


def primary_domain(relative_path: str) -> str:
    """The domain that decides who owns the file: its first domain other than security; "" when none."""
    return next((domain for domain in domains_of(relative_path) if domain in OWNER), "")


def domains_of_files(files: Iterable[str]) -> dict[str, list[str]]:
    """Each domain the files touch, with the files in it, in `DOMAINS` order; a file may be in several."""
    by_domain: dict[str, list[str]] = {}
    for path in files or ():
        for domain in domains_of(str(path)):
            by_domain.setdefault(domain, []).append(str(path))
    return {domain: by_domain[domain] for domain in DOMAINS if domain in by_domain}


def main_domain(files: Iterable[str]) -> str:
    """The one owning domain more than half of the files are in (by their primary domain); "" when none is."""
    listed = [str(path) for path in files or () if str(path).strip()]
    if not listed:
        return ""
    counted = Counter(domain for domain in (primary_domain(path) for path in listed) if domain)
    if not counted:
        return ""
    domain, count = counted.most_common(1)[0]
    return domain if count * 2 > len(listed) else ""


__all__ = ["ADVICE_ROLE", "BUILDER_ROLES", "DOMAINS", "Domain", "OWNER", "domains_of", "domains_of_files",
           "main_domain", "primary_domain"]
