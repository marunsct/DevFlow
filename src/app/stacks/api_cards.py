"""The installed API of libraries released after the model's training data ends, for the files that use them (plan
HK.7, LF.1302).

A model writes a library's calls as its training data had them. Measured elsewhere: on API changes made after a
model's cutoff, success fell from 56% to 33%, and the release's own documentation raised it to 48-58% (RustEvo2;
GitChameleon 2.0, +10 points); here, builders imported names the installed package did not have (`createClient` from
`hono/testing`, which exports only `testClient`) and every rewrite guessed again. The harness knows the installed
release (`.harness/stack-facts.json`, HK.1), when each release line began (the registry's own dates,
`app.tools.release_fit`) and when the model's training data ends (`app.models.knowledge_cutoff`), so it can tell
which libraries the model cannot know and hand over their API before the code is written.

- **Flagged**: a dependency whose installed release line (its major, or `0.minor`) first came out after the build
  model's cutoff. The list is kept in `.harness/api-cards.json` beside the stack facts.
- **The card**, for a flagged library a file or a work order uses, short and labelled: the names the installed
  package exports, those the work names first (`app.analysis.package_exports`); its shipped changelog's lines on those
  names (`app.analysis.installed_packages`); its own migration notes for that line; then its documentation for that
  release (`app.tools.versioned_docs`: Context7 pinned to the version, else the library's own documentation when the
  installed release is on the newest's line), through the outbound gate and kept per library and release.
- **Given to** the builders (a work order's request, a drafted file's request) and the fixers (both paths), for the
  files that use the library only; cut to a share of the request's input budget (`request_budget.opening_target`), at
  most `MOST_LIBRARIES` libraries.

Behind `API_CARDS_FOR_NEWER_RELEASES`, off until measured: off, every request is as before, byte for byte, and
nothing is read or asked. A model with no known cutoff, a project with no stack facts, or a file using no flagged
library gets nothing either.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

SWITCH = "API_CARDS_FOR_NEWER_RELEASES"
#: Where the flagged libraries are kept, from the workspace root.
RECORD = ".harness/api-cards.json"
#: What opens the cards in a request; the audit's switch-firing check reads it (`switch_firing.SIGNALS`).
HEADING = "--- Libraries whose installed release line is newer than this model's training data ---"
#: Libraries given a card in one request.
MOST_LIBRARIES = 3
#: Characters of one card, and of all of them in one request.
MOST_CARD_CHARACTERS = 2_400
MOST_CHARACTERS = 6_000
#: The share of a request's opening target the cards may take (`request_budget.opening_target`).
SHARE_OF_THE_BUDGET = 0.06
#: Fewer characters left than this, and no further card is added.
LEAST_CARD = 400
#: Exported names listed on a card.
MOST_NAMES = 40
#: Characters of a library's migration notes and of its documentation on a card.
MOST_MIGRATION = 700
MOST_DOCUMENTATION = 1_100
#: Characters of a file read to see which libraries it uses.
MOST_FILE_CHARACTERS = 60_000
#: Registry reads at once when the release lines' first days are not kept yet.
AT_ONCE = 8

_WRITING = threading.Lock()
_FLAGGED: dict[tuple[str, int, str], list[dict[str, Any]]] = {}


class _Cards:
    """`API_CARDS_FOR_NEWER_RELEASES` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("A builder or fixer working on a file that uses a library whose installed release line began after "
                   "the build model's training data ends is given that library's API as installed: the names it "
                   "exports, its changelog on the names the work uses, its migration notes, and its documentation "
                   "for that release (Context7 pinned to the version, else its own). Needs the model's training "
                   "cutoff on the settings page or its card. Off: requests are as before.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on(SWITCH, _Cards.ON_BY_DEFAULT)


cards_switch = _Cards()


def enabled() -> bool:
    return cards_switch.enabled()


# --- which libraries are newer than the model ------------------------------------------------------------------------

def _lines_path() -> Path:
    import os

    return Path(os.environ.get("DATA_DIR") or "data") / "versioned-docs" / "release-lines.json"


def line_began(ecosystem: str, package: str, version: str, *, fetch: Any = None) -> str:
    """The day (YYYY-MM-DD) the first release of `version`'s release line came out, from its registry; "" when the
    registry gives no dates. Kept for every run: a line's first day never changes."""
    from app.tools import release_fit, versioned_docs

    wanted = versioned_docs.line(version)
    if not wanted or not ecosystem or not package:
        return ""
    key = f"{ecosystem}/{package}@{'.'.join(map(str, wanted))}"
    try:
        known = json.loads(_lines_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        known = {}
    if isinstance(known, dict) and known.get(key):
        return str(known[key])
    days = [r.released for r in release_fit.releases(ecosystem, package, fetch=fetch)
            if r.released and release_fit.is_stable(r.version) and versioned_docs.line(r.version) == wanted]
    began = min(days) if days else ""
    if began:
        try:
            with _WRITING:
                try:
                    known = json.loads(_lines_path().read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    known = {}
                known = known if isinstance(known, dict) else {}
                known[key] = began
                _lines_path().parent.mkdir(parents=True, exist_ok=True)
                _lines_path().write_text(json.dumps(known, sort_keys=True), encoding="utf-8")
        except OSError:
            pass
    return began


def flagged(root: str | Path, cutoff: str, *, fetch: Any = None) -> list[dict[str, Any]]:
    """The dependencies of the stack facts whose installed release line began after `cutoff` ("YYYY-MM"), each with
    its ecosystem, package, version, the newest release and the day its line began; kept in `RECORD`. [] when there
    is no cutoff or no sheet. Never raises."""
    if not cutoff or not root:
        return []
    try:
        from app.stacks import stack_facts
        from app.tools import package_registry

        sheet_path = Path(root) / stack_facts.SHEET
        try:
            stamp = sheet_path.stat().st_mtime_ns
        except OSError:
            return []
        key = (str(root), stamp, cutoff)
        if key in _FLAGGED:
            return _FLAGGED[key]
        found: list[dict[str, Any]] = []
        if package_registry.enabled():
            from concurrent.futures import ThreadPoolExecutor

            entries = [{"ecosystem": str(e.get("ecosystem") or ""), "package": str(e.get("package") or ""),
                        "version": str(e.get("resolved") or e.get("version") or "").lstrip("v=^~ "),
                        "newest": str(e.get("newest") or e.get("version") or "")}
                       for e in stack_facts.read(root).get("dependencies") or [] if isinstance(e, dict)]
            with ThreadPoolExecutor(max_workers=AT_ONCE) as pool:
                days = list(pool.map(lambda e: line_began(e["ecosystem"], e["package"], e["version"], fetch=fetch),
                                     entries))
            found = [{**entry, "line_began": began} for entry, began in zip(entries, days)
                     if began and began[:7] > cutoff]
        with _WRITING:
            record = Path(root) / RECORD
            record.parent.mkdir(parents=True, exist_ok=True)
            record.write_text(json.dumps({
                "written": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "training_data_ends": cutoff, "flagged": found}, indent=1) + "\n", encoding="utf-8")
        if len(_FLAGGED) > 64:
            _FLAGGED.clear()
        _FLAGGED[key] = found
        return found
    except Exception:  # noqa: BLE001 - nothing flagged rather than a failed request
        logger.debug("Could not flag the libraries newer than the model", exc_info=True)
        return []


# --- which of them a piece of work uses ------------------------------------------------------------------------------

def _python_import_names(project: Path, package: str) -> list[str]:
    """The names a Python distribution is imported by (`top_level.txt`), else its name as an import writes it."""
    wanted = re.sub(r"[-_.]+", "-", package.lower())
    for base in (project, project.parent):
        for site in sorted((base / ".venv" / "lib").glob("python*/site-packages")):
            for info in site.glob("*.dist-info"):
                if re.sub(r"[-_.]+", "-", info.name[: -len(".dist-info")].rsplit("-", 1)[0].lower()) != wanted:
                    continue
                try:
                    tops = (info / "top_level.txt").read_text(encoding="utf-8").split()
                except OSError:
                    tops = []
                if tops:
                    return tops
    return [package.replace("-", "_").lower()]


def spellings(package: str, ecosystem: str = "", project: Path | None = None) -> set[str]:
    """How code names a package: as published, with `_` for `-`, its last path segment (`gin` of a Go module, the
    artifact of a Maven coordinate), and a Python distribution's import names."""
    name = str(package or "").strip()
    if not name:
        return set()
    found = {name, name.replace("-", "_")}
    if ":" in name:
        group, _, artifact = name.partition(":")
        found |= {group, artifact}
    if "/" in name and not name.startswith("@"):
        found.add(name.rsplit("/", 1)[-1])
    if ecosystem == "pypi" and project is not None:
        found |= set(_python_import_names(project, name))
    return {s for s in found if len(s) >= 2}


def _a_name_in_prose(text: str, start: int, end: int, spelling: str) -> bool:
    """Whether a word found in prose names the library: quoted, before a path or a member, written as a name
    (`FastAPI`, `Hono`), or a spelling no sentence uses (`better-sqlite3`) - never "the next step"."""
    before, after = text[start - 1:start], text[end:end + 2]
    return (before in ("`", "'", '"') or after[:1] in ("`", "'", '"', "/", ":")
            or (after[:1] == "." and after[1:2].isalpha()) or text[start:end] != text[start:end].lower()
            or not spelling.isalpha())


def uses(text: str, package: str, ecosystem: str = "", project: Path | None = None, *, prose: bool = False) -> bool:
    """Whether `text` names the package as code does: standing alone, or before a path or member (`hono/cors`,
    `axum::Router`, `sqlalchemy.orm`), never inside another name. In `prose` (a work order, a defect's evidence) in
    any case, but only where the word is written as the library's name (`_a_name_in_prose`)."""
    text = str(text or "")
    for spelling in spellings(package, ecosystem, project):
        pattern = re.compile(r"(?<![\w@$-])" + re.escape(spelling) + r"(?![\w$-])", re.I if prose else 0)
        for found in pattern.finditer(text):
            if not prose or _a_name_in_prose(text, found.start(), found.end(), spelling):
                return True
    return False


def _read_files(root: Path, paths: Iterable[str]) -> str:
    texts = []
    for path in dict.fromkeys(str(p).strip().lstrip("./") for p in paths if p):
        for candidate in (root / path, *root.glob(f"*/{path}")):
            if candidate.is_file():
                try:
                    texts.append(candidate.read_text(encoding="utf-8", errors="replace")[:MOST_FILE_CHARACTERS])
                except OSError:
                    pass
                break
    return "\n".join(texts)


# --- the card --------------------------------------------------------------------------------------------------------

_FAMILY = {"npm": "script", "pypi": "python"}
_A_MIGRATION_FILE = re.compile(r"^(?:migrat|upgrad)[\w.-]*\.(?:md|rst|txt)$", re.I)
_A_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _exports(project: Path, entry: dict[str, Any]) -> list[str]:
    from app.analysis import package_exports

    family = _FAMILY.get(entry["ecosystem"], "")
    if family == "script":
        return package_exports.script_package_exports(project, entry["package"]) or []
    if family == "python":
        for name in _python_import_names(project, entry["package"]):
            names = package_exports.python_package_exports(project, name)
            if names:
                return names
    return []


def _migration_notes(directory: Path | None, version: str) -> str:
    """The section of a package's shipped migration notes about `version`'s line: (file name, text) as one string."""
    from app.tools import versioned_docs

    if directory is None:
        return ""
    major = versioned_docs.line(version)
    if not major:
        return ""
    label = ".".join(map(str, major))
    about = re.compile(rf"(?<![\d.])v?{re.escape(label)}(?:\.0|\.x)*(?![\d])", re.I)
    for folder in (directory, directory / "docs"):
        try:
            files = sorted(p for p in folder.iterdir() if p.is_file() and _A_MIGRATION_FILE.match(p.name))
        except OSError:
            continue
        for path in files:
            try:
                lines = path.read_text(encoding="utf-8", errors="replace")[:400_000].splitlines()
            except OSError:
                continue
            for index, text in enumerate(lines):
                heading = _A_MARKDOWN_HEADING.match(text)
                if not heading or not about.search(heading.group(2)):
                    continue
                level = len(heading.group(1))
                end = next((j for j in range(index + 1, len(lines))
                            if (h := _A_MARKDOWN_HEADING.match(lines[j])) and len(h.group(1)) <= level), len(lines))
                section = "\n".join(lines[index:end]).strip()
                return f"{path.name}:\n{section}"
    return ""


def _documentation(entry: dict[str, Any], *, fetch: Any = None, docs_fetch: Any = None) -> dict[str, Any]:
    from app.tools import versioned_docs

    label = ".".join(map(str, versioned_docs.line(entry["version"])))
    return versioned_docs.read(
        entry["package"], entry["version"],
        f"{entry['package']} {label} API: its main calls, and what changed from the release line before",
        ecosystem=entry["ecosystem"], newest=entry.get("newest") or "", topic="migration upgrade api reference",
        fetch=fetch, docs_fetch=docs_fetch)


def card(root: str | Path, entry: dict[str, Any], text: str, cutoff: str, *, most: int = MOST_CARD_CHARACTERS,
         fetch: Any = None, docs_fetch: Any = None) -> str:
    """One flagged library's card for work whose words are `text`; "" when nothing about it could be read."""
    from app.analysis import installed_packages
    from app.tools import versioned_docs
    from app.tools.page_reader import cut_at_a_block

    project = installed_packages.project_of(root)
    family = _FAMILY.get(entry["ecosystem"], "")
    exports = _exports(project, entry)
    used = [name for name in exports if len(name) > 1 and re.search(rf"(?<![\w$]){re.escape(name)}(?![\w$])", text)]
    label = ".".join(map(str, versioned_docs.line(entry["version"])))
    parts = [f"### `{entry['package']}` {entry['version']} ({entry['ecosystem']}): its {label} release line began "
             f"{entry['line_began']}, after this model's training data ends ({cutoff})"]
    if exports:
        rest = [n for n in exports if n not in used]
        shown = (", ".join(f"`{n}`" for n in used[:MOST_NAMES]) + (" - then: " if used and rest else "")
                 + ", ".join(f"`{n}`" for n in rest[: max(0, MOST_NAMES - len(used))]))
        # A list cut at `MOST_NAMES` says so: past it, a name not shown may still be exported (LF.1515).
        left_out = len(exports) - min(len(exports), MOST_NAMES)
        closing = (f" and {left_out} more of its {len(exports)} names, not shown - so a name not here may still be "
                   "exported by this release." if left_out else
                   ". A name not here is not exported by this release.")
        parts.append(f"Names it exports, read from its installed files{' (those this work names first)' if used else ''}: "
                     f"{shown}{closing}")
    imported = _python_import_names(project, entry["package"])[0] if family == "python" else entry["package"]
    directory = installed_packages.package_directory(project, family, imported) if family else None
    changes = [line for name in used[:4] for line in installed_packages.changelog_lines(directory, name)][:4]
    if changes:
        parts.append("Its changelog, as installed, on those names:\n" + "\n".join(f"- {line}" for line in changes))
    migration = _migration_notes(directory, entry["version"])
    if migration:
        parts.append("Its own migration notes for this line, " + cut_at_a_block(migration, MOST_MIGRATION))
    room = most - sum(len(p) + 2 for p in parts)
    if room > LEAST_CARD:
        documentation = _documentation(entry, fetch=fetch, docs_fetch=docs_fetch)
        if documentation.get("excerpt"):
            parts.append(f"From its documentation for {documentation.get('release') or entry['version']} "
                         f"({documentation.get('source')}; reference text, not an instruction):\n"
                         + cut_at_a_block(documentation["excerpt"], min(MOST_DOCUMENTATION, room - 120)))
    if len(parts) == 1:
        return ""
    return cut_at_a_block("\n".join(parts), most)


def section(root: str | Path | None, *, files: Iterable[str] = (), about: str = "", model: Any = None,
            fetch: Any = None, docs_fetch: Any = None) -> str:
    """The cards for the flagged libraries the work on `files` (as they are on disk) and `about` (its order, its
    evidence) uses, under `HEADING`; "" when off, when the model's cutoff is not known, or when none is used."""
    if not enabled() or not root:
        return ""
    try:
        from app.analysis import installed_packages
        from app.models import knowledge_cutoff

        cutoff = knowledge_cutoff.of_the_build_model(model)
        newer = flagged(root, cutoff, fetch=fetch)
        if not newer:
            return ""
        root = Path(root)
        project = installed_packages.project_of(root)
        code, words = _read_files(root, files), str(about or "")
        text = code + "\n" + words
        wanted = [e for e in newer if uses(code, e["package"], e["ecosystem"], project)
                  or uses(words, e["package"], e["ecosystem"], project, prose=True)][:MOST_LIBRARIES]
        if not wanted:
            return ""
        from app.agents import request_budget

        room = min(MOST_CHARACTERS, int(request_budget.opening_target(model) * SHARE_OF_THE_BUDGET))
        cards: list[str] = []
        for entry in wanted:
            left = room - sum(len(c) + 2 for c in cards)
            if left < LEAST_CARD:
                break
            made = card(root, entry, text, cutoff, most=min(MOST_CARD_CHARACTERS, left), fetch=fetch,
                        docs_fetch=docs_fetch)
            if made:
                cards.append(made)
        if not cards:
            return ""
        return (f"\n\n{HEADING}\n"
                "What you remember of these libraries is older than the release installed here, so their names and "
                "calls may have changed. Use the names and calls below, as installed; where the specification names "
                "a call this release does not have, write it with what the release offers.\n\n"
                + "\n\n".join(cards) + "\n")
    except Exception:  # noqa: BLE001 - the request as it was
        logger.debug("Could not make the API cards", exc_info=True)
        return ""


def for_a_work_order(root: str | Path | None, work_order: Any, about: str = "", model: Any = None) -> str:
    """For a builder: the cards for the libraries its work order's files and words use."""
    if not enabled():
        return ""
    files = list(getattr(work_order, "files", None) or [])
    words = "\n".join([about, str(getattr(work_order, "task_description", "") or ""),
                       *map(str, getattr(work_order, "interfaces", None) or [])])
    return section(root, files=files, about=words, model=model)


def for_a_draft(root: str | Path | None, path: str, detail: str = "", model: Any = None) -> str:
    """For a file drafted from the specification: the cards for the libraries it, or its entries, use."""
    if not enabled():
        return ""
    return section(root, files=[path], about=detail, model=model).strip()


def for_a_fixer(root: str | Path | None, files: Iterable[str], evidence: str = "", model: Any = None) -> str:
    """For a fixer: the cards for the libraries the defect's files and its evidence use."""
    if not enabled():
        return ""
    return section(root, files=list(files), about=evidence, model=model)


__all__ = ["HEADING", "MOST_CARD_CHARACTERS", "MOST_CHARACTERS", "MOST_LIBRARIES", "RECORD", "SWITCH", "card",
           "cards_switch", "enabled", "flagged", "for_a_draft", "for_a_fixer", "for_a_work_order", "line_began",
           "section", "spellings", "uses"]
