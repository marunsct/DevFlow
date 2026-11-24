"""Stack selection and architecture on evidence: one row of facts per candidate (plan HK.8, LF.1301).

A person choosing a library compares candidates on maturity, maintenance, security and fit with their toolchain (in
one survey of 115 developers: maturity 62%, maintenance 44%, security 39%; popularity 30%). The stack selector was
offered lookup tools it never called and chose from training data; the architect read registry releases but no
support window or advisory. So before each of them is asked, the harness reads, for each candidate:

- the current release and its date, and whether it fits this environment's toolchain (the stack facts, HK.1:
  `stack_facts.fact`, the newest stable release this toolchain runs);
- its support window (endoflife.date, by the package's identifier, or by name for a database or a runtime);
- the advisories open on that release (OSV, one batch for every candidate);
- whether a stack pack scaffolds it.

The candidates are the ones the technology comparison weighed (its frameworks, storage, authentication and testing
choices and their alternatives) and the stack it proposed; for the architect, the chosen stack's libraries. The rows
are kept in the stack facts (`evidence`), shown as one table (`for_the_selector`, `for_the_architect`), and each
architecture decision record that names a candidate records the row it relied on in its validation evidence
(`with_the_rows_relied_on`) - written by the harness, not left to the model.

A source that cannot be read says "not known" in its column, never "none". Part of the stack facts (`STACK_FACTS`,
a built-in fix), so off in the tests unless a test turns it on.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

#: Candidates given a row.
MOST_CANDIDATES = 12
#: Registry reads at once.
AT_ONCE = 8
#: The technology comparison's lists whose entries are libraries or products to build on.
LIBRARY_LISTS = ("frameworks", "authentication", "testing_tools")
#: Lists whose entries are products with a support window, not packages (a database server).
PRODUCT_LISTS = ("storage_options",)
#: Words more than this in a name make it a sentence, not a name.
MOST_WORDS = 3

HEADING = "--- Evidence for each candidate, read before this choice (`.harness/stack-facts.json`) ---"
ARCHITECT_HEADING = "--- Evidence for the chosen stack (`.harness/stack-facts.json`) ---"
COLUMNS = ("Candidate", "Package", "Current release (date)", "Support", "Open advisories", "Toolchain fit", "Pack")
#: How an architecture decision record names the row it relied on.
RELIED_ON = "Evidence relied on"
NOT_KNOWN = "not known"

SELECTOR_NOTE = (
    "Read by the harness from the package registries, OSV and endoflife.date for this environment's toolchains. "
    "Prefer a candidate whose current release fits the toolchain here, is inside its support window and has no open "
    "advisory; \"not known\" means the source could not be read, not that the candidate is safe. A brief that names "
    "a technology still wins over this table.")
ARCHITECT_NOTE = (
    "Read by the harness for the libraries of the chosen stack. Pin the release in the table, and in each decision "
    "record's `validation_evidence` cite the row the decision relied on; the harness adds the row to every decision "
    "that names a candidate.")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _a_name(text: str) -> str:
    """A candidate's name from what the comparison wrote: `FastAPI (Python)` is `FastAPI`, `Flask - simpler` is
    `Flask`; "" for a sentence or a "none"."""
    text = _text(text)
    text = re.split(r"\s+[-–—]\s+|[:;,(]|\s+(?:because|which|for|as|with|on|over|instead)\s+", text)[0]
    text = re.sub(r"\s+v?\d[\w.]*$", "", text).strip(" .`'\"")
    if not text or len(text.split()) > MOST_WORDS or re.match(r"^(?:none|n/?a|no |not |-)", text, re.I):
        return ""
    return text


def _get(record: Any, key: str) -> Any:
    return record.get(key) if isinstance(record, dict) else getattr(record, key, None)


def candidates(tools_models: Any) -> list[tuple[str, str]]:
    """(name, kind) of each candidate the comparison weighed - kind "library" or "product" - each once."""
    found: dict[str, tuple[str, str]] = {}

    def add(name: str, kind: str) -> None:
        name = _a_name(name)
        if name and name.lower() not in found:
            found[name.lower()] = (name, kind)

    stack = _get(tools_models, "technology_stack")
    for field_name in ("framework", "frontend_framework"):
        add(_text(_get(stack, field_name)), "library")
    add(_text(_get(stack, "database")), "product")
    for list_name, kind in [*((n, "library") for n in LIBRARY_LISTS), *((n, "product") for n in PRODUCT_LISTS)]:
        for choice in _get(tools_models, list_name) or []:
            add(_text(_get(choice, "name")), kind)
            add(_text(_get(choice, "alternative")), kind)
    return list(found.values())[:MOST_CANDIDATES]


def ecosystems_of(stack: Any) -> list[str]:
    """The registries the stack's languages publish to, in the order named; npm too when it has a separate page."""
    from app.tools.package_registry import ecosystem_named

    named = re.split(r"[\s,/+]+|\band\b", _text(_get(stack, "language")))
    out = [e for e in (ecosystem_named(word) for word in named if word) if e]
    frontend = _text(_get(stack, "frontend_framework"))
    if frontend and not re.match(r"^(?:none|n/?a)\b", frontend, re.I):
        out.append("npm")
    return list(dict.fromkeys(out))


def _package_name(name: str) -> str:
    """A name as a registry spells its package: `Express.js` is `express`, `Spring Boot` is `spring-boot`."""
    plain = re.sub(r"\.js$", "", name.strip(), flags=re.I).lower()
    return re.sub(r"\s+", "-", plain)


def _pack_of(name: str) -> str:
    """The stack pack that scaffolds `name`, or ""."""
    from app.stacks.packs import ALL_PACKS

    word = re.escape(re.sub(r"\.js$", "", name.strip(), flags=re.I))
    pattern = re.compile(rf"(?<![\w.-]){word}(?:\.js)?(?![\w-])", re.I)
    for pack in ALL_PACKS:
        values = [str(pack.stack.get(k) or "") for k in ("framework", "frontend_framework", "testing_framework")]
        if any(pattern.search(re.sub(r"\(.*?\)", " ", v)) for v in values):
            return pack.name
    return ""


def _fit(entry: dict[str, Any], toolchain: dict[str, str]) -> str:
    from app.tools.release_fit import RUNTIME_OF, numbers

    if not entry:
        return NOT_KNOWN
    ecosystem = str(entry.get("ecosystem") or "")
    banner = toolchain.get(ecosystem, "")
    here = f"{RUNTIME_OF.get(ecosystem, ecosystem)} {'.'.join(map(str, numbers(banner)))}" if numbers(banner) else ""
    if entry.get("withdrawn"):
        return f"withdrawn: {entry['withdrawn']}"
    if entry.get("newest") and entry.get("newest") != entry.get("version"):
        return f"{entry['version']} fits{f' {here}' if here else ''}; the newest, {entry['newest']}, needs a newer one"
    if entry.get("needs"):
        return f"fits{f' {here}' if here else ''} (needs {entry['needs']})"
    return f"fits{f' {here}' if here else ''}"


def _registry_fact(name: str, ecosystems: list[str], root: Path | None) -> dict[str, Any]:
    """The candidate's package in the first registry that has it, the newest-released one when several do."""
    from app.stacks import stack_facts

    package = _package_name(name)
    if not re.match(r"^(?:@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*$", package):
        return {}
    found = [f for f in (stack_facts.fact(e, package, root) for e in ecosystems) if f]
    return max(found, key=lambda f: str(f.get("released") or "")) if found else {}


def _support_of(name: str, kind: str, entry: dict[str, Any]) -> dict[str, Any] | str:
    from app.tools import support_dates
    from app.tools.public_data import NotKnown

    try:
        if entry:
            product = support_dates.product_of_package(entry["ecosystem"], entry["package"])
            return support_dates.support(product, str(entry.get("version") or "")) if product else {}
        if kind == "product":
            product = support_dates.product_named(name)
            return support_dates.support(product) if product else {}
        return {}
    except NotKnown:
        return NOT_KNOWN


def rows(named: Iterable[tuple[str, str]], ecosystems: list[str], root: str | Path | None) -> list[dict[str, Any]]:
    """One row of facts per candidate (see the module's note). Never raises; a column that could not be read is
    "not known"."""
    from app.stacks import stack_facts
    from app.tools import osv
    from app.tools.public_data import NotKnown
    from app.tools.support_dates import described

    named = list(named)[:MOST_CANDIDATES]
    root = Path(root) if root else None
    if not named:
        return []
    with ThreadPoolExecutor(max_workers=AT_ONCE) as pool:
        facts = list(pool.map(lambda c: _registry_fact(c[0], ecosystems, root) if c[1] == "library" else {}, named))
        supports = list(pool.map(lambda pair: _support_of(pair[0][0], pair[0][1], pair[1]), zip(named, facts)))
    try:
        toolchain = stack_facts.toolchains(sorted({f["ecosystem"] for f in facts if f}), root) if any(facts) else {}
    except Exception:  # noqa: BLE001
        toolchain = {}
    releases = [osv.Release(f["ecosystem"], f["package"], str(f["version"])) for f in facts if f]
    try:
        advisories: dict[Any, list[Any]] | None = osv.advisories(releases, root) if releases else {}
    except NotKnown:
        advisories = None
    out = []
    for (name, kind), entry, support in zip(named, facts, supports):
        row: dict[str, Any] = {"candidate": name, "kind": kind, "pack": _pack_of(name) if kind == "library" else ""}
        if entry:
            release = osv.Release(entry["ecosystem"], entry["package"], str(entry["version"]))
            found = None if advisories is None else advisories.get(release, [])
            row.update({
                "ecosystem": entry["ecosystem"], "package": entry["package"], "current": str(entry["version"]),
                "released": str(entry.get("released") or ""), "fit": _fit(entry, toolchain),
                "advisories": NOT_KNOWN if found is None else (
                    "none known" if not found else ", ".join(
                        f"{a.id} ({(a.severity or 'severity not stated').lower()}"
                        + (f", fixed in {a.fixed}" if a.fixed else "") + ")" for a in found[:3])
                    + (f" and {len(found) - 3} more" if len(found) > 3 else "")),
            })
        elif kind == "library":
            row.update({"fit": NOT_KNOWN, "advisories": NOT_KNOWN})
        row["support"] = support if isinstance(support, str) else (described(support) if support else (
            "not tracked by endoflife.date" if kind == "product" or entry else NOT_KNOWN))
        out.append(row)
    return out


def _cell(text: Any) -> str:
    return _text(text).replace("|", "/") or "-"


def row_line(row: dict[str, Any]) -> str:
    """One row as a line of the table."""
    package = f"{row['ecosystem']} `{row['package']}`" if row.get("package") else (
        "a product, not a package" if row.get("kind") == "product" else "not matched by name in a registry")
    current = (f"{row['current']}" + (f" ({row['released']})" if row.get("released") else "")) if row.get("current") \
        else "-"
    pack = f"yes ({row['pack']})" if row.get("pack") else ("no" if row.get("kind") == "library" else "-")
    cells = (row.get("candidate"), package, current, row.get("support"), row.get("advisories") or "-",
             row.get("fit") or "-", pack)
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def row_sentence(row: dict[str, Any]) -> str:
    """One row as a sentence a decision record keeps: each column that says something, by its name."""
    cells = row_line(row).strip("| ").split(" | ")
    said = [f"{name.lower()}: {cell}" for name, cell in zip(COLUMNS[1:], cells[1:]) if cell != "-"]
    return f"{cells[0]} - " + "; ".join(said)


def table(found: list[dict[str, Any]]) -> str:
    if not found:
        return ""
    return "\n".join(["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS),
                      *(row_line(r) for r in found)])


def _keep(root: str | Path | None, found: list[dict[str, Any]]) -> None:
    from app.stacks import stack_facts

    if not root or not found:
        return

    def change(sheet: dict[str, Any]) -> dict[str, Any]:
        evidence = dict(sheet.get("evidence") or {})
        kept = {str(r.get("candidate")).lower(): r for r in evidence.get("rows") or [] if isinstance(r, dict)}
        kept.update({str(r["candidate"]).lower(): r for r in found})
        return {**sheet, "evidence": {"read": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                      "rows": list(kept.values())}}

    stack_facts.amend(root, change)


def for_the_selector(tools_models: Any, root: str | Path | None) -> str:
    """The evidence table for the stack selector's request; "" when off or there is no candidate. Never raises."""
    from app.stacks import stack_facts

    if not stack_facts.enabled():
        return ""
    try:
        named = candidates(tools_models)
        found = rows(named, ecosystems_of(_get(tools_models, "technology_stack")), root)
        _keep(root, found)
        return f"{HEADING}\n{SELECTOR_NOTE}\n{table(found)}\n\n" if found else ""
    except Exception:  # noqa: BLE001 - the request as it was
        logger.warning("Could not read the evidence for the candidates", exc_info=True)
        return ""


def for_the_architect(root: str | Path | None, stack: Any) -> str:
    """The evidence table for the chosen stack's libraries and database, for the architect; "" when off. Never
    raises."""
    from app.agents.research_brief import libraries_of
    from app.stacks import stack_facts

    if not stack_facts.enabled() or stack is None:
        return ""
    try:
        # The database is a product with a support window, not a package, whatever list names it.
        database = _a_name(_text(_get(stack, "database")))
        named = [(name, "library") for name in libraries_of(stack) if name.lower() != database.lower()]
        if database:
            named.append((database, "product"))
        found = rows(named, ecosystems_of(stack), root)
        _keep(root, found)
        return f"{ARCHITECT_HEADING}\n{ARCHITECT_NOTE}\n{table(found)}" if found else ""
    except Exception:  # noqa: BLE001
        logger.warning("Could not read the evidence for the chosen stack", exc_info=True)
        return ""


def _names_it(text: str, row: dict[str, Any]) -> bool:
    """Whether `text` names the row's candidate - by the candidate's name, not its package's, which can be a plain
    word (`next`)."""
    word = str(row.get("candidate") or "")
    plain = re.escape(re.sub(r"\.js$", "", word, flags=re.I))
    return bool(word) and re.search(rf"(?<![\w-]){plain}(?:\.js)?(?![\w-])", text, re.I) is not None


def with_the_rows_relied_on(specification: Any, root: str | Path | None) -> Any:
    """`specification` with each decision record that names a candidate citing that candidate's row in its validation
    evidence; as it was when off, with no rows kept, or no decision names one. Never raises."""
    from app.stacks import stack_facts

    try:
        if not stack_facts.enabled() or specification is None or not hasattr(specification, "model_copy"):
            return specification
        evidence = stack_facts.read(root).get("evidence") or {}
        kept = [r for r in evidence.get("rows") or [] if isinstance(r, dict) and r.get("candidate")]
        decisions = list(getattr(specification, "decisions", None) or [])
        if not kept or not decisions:
            return specification
        read = str(evidence.get("read") or "")[:10]
        changed = False
        out = []
        for record in decisions:
            text = f"{getattr(record, 'title', '')} {getattr(record, 'decision', '')}"
            cited = str(getattr(record, "validation_evidence", "") or "")
            lines = [f"{RELIED_ON} (stack facts{f', read {read}' if read else ''}): {row_sentence(r)}"
                     for r in kept if _names_it(text, r)]
            lines = [line for line in lines if line not in cited]
            if lines and hasattr(record, "model_copy"):
                record = record.model_copy(update={"validation_evidence": "\n".join([cited, *lines]).strip()})
                changed = True
            out.append(record)
        return specification.model_copy(update={"decisions": out}) if changed else specification
    except Exception:  # noqa: BLE001 - the specification as written
        logger.debug("Could not record the evidence in the decisions", exc_info=True)
        return specification


__all__ = ["ARCHITECT_HEADING", "COLUMNS", "HEADING", "RELIED_ON", "candidates", "ecosystems_of", "for_the_architect",
           "for_the_selector", "row_line", "row_sentence", "rows", "table", "with_the_rows_relied_on"]
