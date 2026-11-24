"""Support windows for runtimes, frameworks and databases, from endoflife.date (plan HK.6, HK.8, LF.1300-LF.1301).

A person checks that the runtime and framework they ship on are still supported; the harness had no end-of-life fact
anywhere. endoflife.date publishes each product's release cycles - when each was released, when its support ends,
whether it is still maintained, its latest release - through a keyless API (v1).

- `product_named(word)`: the product a name means (`node`, `.NET SDK`, `PostgreSQL`), matched on the product's own
  name, label and aliases - no table of products here.
- `product_of_package(ecosystem, package)`: the product a package is (`pypi/django`), by the package identifiers
  (purl) endoflife.date lists for its products.
- `support(product, version)`: the cycle `version` belongs to (the longest of its leading numbers that names a
  cycle) and that cycle's dates; with no version, the newest cycle.
- `described(entry)`: one line a stage reads.

Only product names leave (through the one outbound gate, `app.tools.outbound`); the product list and the identifier
list are read whole and matched here. A service that cannot answer raises `public_data.NotKnown`.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import quote, unquote

from app.tools.public_data import NotKnown, ask

SOURCE = "endoflife.date"
CHANNEL = "support dates"
HOST = "endoflife.date"
PRODUCTS = f"https://{HOST}/api/v1/products"
PRODUCT = f"https://{HOST}/api/v1/products/"
IDENTIFIERS = f"https://{HOST}/api/v1/identifiers/purl"
#: Seconds the lists and a product's cycles are kept: support dates change seldom.
KEPT_FOR = 24 * 3_600.0

#: The runtime each of the harness's ecosystems runs on, as `product_named` is asked for it.
RUNTIME = {"npm": "node", "pypi": "python", "crates": "rust", "go": "go", "maven": "java", "rubygems": "ruby",
           "packagist": "php", "nuget": ".NET"}
#: The package-identifier (purl) type of each of the harness's ecosystems.
PURL_TYPE = {"npm": "npm", "pypi": "pypi", "crates": "cargo", "go": "golang", "maven": "maven", "rubygems": "gem",
             "packagist": "composer", "nuget": "nuget"}


def _plain(word: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(word or "").lower())


def _result(answer: Any) -> Any:
    return answer.get("result") if isinstance(answer, dict) and "result" in answer else answer


def _products() -> list[dict[str, Any]]:
    found = _result(ask(SOURCE, PRODUCTS, channel=CHANNEL, said="the product list", kept_for=KEPT_FOR))
    if not isinstance(found, list):
        raise NotKnown(f"{SOURCE} answered with no product list")
    return [p for p in found if isinstance(p, dict) and p.get("name")]


def _variants(word: str) -> list[str]:
    """`word` as a product may be named: as written, without a trailing "js" or "sdk", with "js" (`node` is
    `nodejs`, `Vue.js` is `vue`, `.NET SDK` is `.NET`)."""
    plain = _plain(word)
    out = [plain]
    for suffix in ("js", "sdk"):
        if plain.endswith(suffix) and len(plain) > len(suffix) + 1:
            out.append(plain[: -len(suffix)])
    out.append(plain + "js")
    return [v for v in dict.fromkeys(out) if v]


def product_named(word: str) -> str:
    """The endoflife.date product `word` names, or "" when none does. Raises `NotKnown`."""
    if not _plain(word):
        return ""
    products = _products()
    for variant in _variants(word):
        for product in products:
            names = [product.get("name"), product.get("label"), *(product.get("aliases") or [])]
            if variant in {_plain(n) for n in names if n}:
                return str(product["name"])
    return ""


def _purl(ecosystem: str, package: str) -> str:
    kind = PURL_TYPE.get(ecosystem)
    if not kind or not package:
        return ""
    name = str(package).strip().lower()
    if ecosystem == "maven":
        name = name.replace(":", "/")
    if ecosystem == "pypi":
        name = re.sub(r"[-_.]+", "-", name)
    return f"pkg:{kind}/{name}"


def _purl_of(identifier: Any) -> str:
    """An identifier without its version and qualifiers, unquoted, in lower case."""
    text = unquote(str(identifier or "")).strip().lower()
    text = re.split(r"[?#]", text)[0]
    if "@" in text.rsplit("/", 1)[-1]:
        text = text[: text.rfind("@")]
    if text.startswith("pkg:pypi/"):
        text = "pkg:pypi/" + re.sub(r"[-_.]+", "-", text[len("pkg:pypi/"):])
    return text


def product_of_package(ecosystem: str, package: str) -> str:
    """The endoflife.date product whose identifiers name this package, or "". Raises `NotKnown`."""
    wanted = _purl(ecosystem, package)
    if not wanted:
        return ""
    found = _result(ask(SOURCE, IDENTIFIERS, channel=CHANNEL, said="the package identifier list", kept_for=KEPT_FOR))
    if not isinstance(found, list):
        raise NotKnown(f"{SOURCE} answered with no identifier list")
    for item in found:
        if not isinstance(item, dict):
            continue
        product = item.get("product")
        name = product.get("name") if isinstance(product, dict) else product
        if name and _purl_of(item.get("identifier") or item.get("id")) == wanted:
            return str(name)
    return ""


def _cycles(product: str) -> tuple[str, list[dict[str, Any]]]:
    """(the product's label, its release cycles, newest first)."""
    answer = _result(ask(SOURCE, PRODUCT + quote(product), channel=CHANNEL, said=product, kept_for=KEPT_FOR))
    if answer is None:
        return product, []
    if not isinstance(answer, dict):
        raise NotKnown(f"{SOURCE} answered with no cycles for {product}")
    releases = [r for r in answer.get("releases") or [] if isinstance(r, dict) and r.get("name")]
    return str(answer.get("label") or product), releases


def _numbers(text: Any) -> tuple[int, ...]:
    from app.tools.release_fit import numbers

    return numbers(str(text or "").lstrip("vV"))


def _the_cycle(releases: list[dict[str, Any]], version: str) -> dict[str, Any] | None:
    have = _numbers(version)
    if not have:
        return None
    best, length = None, 0
    for release in releases:
        cycle = _numbers(release.get("name"))
        if cycle and len(cycle) > length and have[: len(cycle)] == cycle:
            best, length = release, len(cycle)
    return best


def _day(value: Any) -> str:
    text = str(value or "")
    return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else ""


def support(product: str, version: str = "", *, today: date | None = None) -> dict[str, Any]:
    """The support facts of `product` at `version` ({} when it has no cycle for that version). Raises `NotKnown`."""
    if not product:
        return {}
    label, releases = _cycles(product)
    if not releases:
        return {}
    newest = max(releases, key=lambda r: _numbers(r.get("name")))
    cycle = _the_cycle(releases, version) if version else newest
    if cycle is None:
        return {}
    today = today or date.today()
    ends = _day(cycle.get("eolFrom"))
    ended = bool(cycle.get("isEol")) or bool(ends and ends <= today.isoformat())
    latest = cycle.get("latest") if isinstance(cycle.get("latest"), dict) else {}
    entry = {
        "product": product, "label": label, "cycle": str(cycle.get("name")), "version": version,
        "released": _day(cycle.get("releaseDate")), "ends": ends, "ended": ended,
        "maintained": bool(cycle.get("isMaintained", not ended)), "latest": str(latest.get("name") or ""),
        "latest_released": _day(latest.get("date")), "newest_cycle": str(newest.get("name")),
    }
    return {k: v for k, v in entry.items() if v not in ("", None)}


def described(entry: dict[str, Any]) -> str:
    """`Node.js 22: supported until 2027-04-30` - one line, or "not known" for no entry."""
    if not entry:
        return "not known"
    name = f"{entry.get('label') or entry.get('product')} {entry.get('cycle')}"
    if entry.get("ended"):
        text = f"{name}: past its end of support" + (f" (since {entry['ends']})" if entry.get("ends") else "")
        if entry.get("newest_cycle") and entry.get("newest_cycle") != entry.get("cycle"):
            text += f"; {entry['newest_cycle']} is the newest line"
        return text
    return f"{name}: supported" + (f" until {entry['ends']}" if entry.get("ends") else ", no end date published")


__all__ = ["CHANNEL", "HOST", "NotKnown", "PURL_TYPE", "RUNTIME", "SOURCE", "described", "product_named", "product_of_package",
           "support"]
