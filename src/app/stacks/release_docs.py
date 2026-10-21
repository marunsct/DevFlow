"""A README with run instructions, and for a service an API summary, required at release (plan PN.2, behind `RELEASE_DOCS_REQUIRED`).

A product was released with every criterion passing and nothing a person who
did not write it could start it from: the release packs CI and container
files, and no check asked whether the handoff says how to run the product or
what it serves. With the switch on, the release is held back - like a failing
criterion, at most until its attempts run out, then recorded as a gap - when:

- the project has no README;
- the README names no way to run it: none of the pack's own commands, no
  `start.sh`, no entrypoint, and no command block when no pack covers it;
- for a product whose locked interface contract has HTTP routes, a route that
  no README or document of the project names, method and path on one line.

Every check reads files; none asks a model.
"""

from __future__ import annotations

import logging
import re
import shlex
from pathlib import Path

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `RELEASE_DOCS_REQUIRED` set to on or off overrides this.
ON_BY_DEFAULT = False
#: README names looked for, project directory first, then the workspace root.
README_NAMES = ("README.md", "README.rst", "README.txt", "README")
#: Documents the harness writes about the run, never the product's own.
_THE_HARNESS_S_DOCS = ("decision_log", "product_intake", "reviews", "sprint", "release-evidence")
_A_PARAMETER = re.compile(r"\{[^}/]*\}|:[A-Za-z_]\w*|<[^>/]*>")
_A_COMMAND_BLOCK = re.compile(r"```|^(?: {4}|\t|\$ )\S", re.M)


def enabled() -> bool:
    return is_on("RELEASE_DOCS_REQUIRED", ON_BY_DEFAULT)


def _the_readme(root: Path, project: str) -> Path | None:
    for base in ([root / project] if project else []) + [root]:
        for name in README_NAMES:
            if (base / name).is_file():
                return base / name
    return None


def _ways_to_run(root: Path, project: str, pack: object | None) -> list[str]:
    ways = ["start.sh"]
    if pack is not None:
        ways += [shlex.join(argv) for argv in getattr(pack, "install", ()) or ()]
        ways += [shlex.join(getattr(pack, name, ()) or ()) for name in ("unit_test", "acceptance_test")]
        ways += [Path(e).name for e in (getattr(pack, "entrypoints", ()) or ()) if e]
        if getattr(pack, "entrypoint", ""):
            ways.append(Path(pack.entrypoint).name)
    return [w for w in dict.fromkeys(ways) if w.strip()]


def _the_product_s_documents(root: Path, project: str) -> str:
    texts = []
    for base in dict.fromkeys(([root / project] if project else []) + [root]):
        for path in [*(base / n for n in README_NAMES), *sorted((base / "docs").glob("**/*.md"))]:
            if path.is_file() and not any(part in path.relative_to(root).as_posix() for part in _THE_HARNESS_S_DOCS):
                try:
                    texts.append(path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
    return "\n".join(texts)


def _shape(path: str) -> str:
    return _A_PARAMETER.sub("{}", path.rstrip("/") or "/")


def _routes_not_named(documents: str, routes: list[tuple[str, str]]) -> list[str]:
    lines = [(line.upper(), _shape(line)) for line in documents.splitlines()]
    missing = []
    for method, path in routes:
        shaped = _shape(path)
        named = any(re.search(rf"\b{method}\b", upper) and re.search(re.escape(shaped) + r"(?![\w/{])", shaped_line)
                    for upper, shaped_line in lines)
        if not named:
            missing.append(f"{method} {path}")
    return missing


def what_the_handoff_lacks(repo_root: str | Path) -> list[str]:
    """What the release is missing of the product's documentation; [] when off or complete. Never raises."""
    if not enabled():
        return []
    try:
        from app.acceptance.interface_contract import the_locked_contract
        from app.stacks import contract

        root = Path(repo_root)
        found = contract.the_pack(root)
        pack, record = found if found else (None, contract.read(root) or {})
        project = str((record or {}).get("project") or "")
        readme = _the_readme(root, project)
        if readme is None:
            return ["The project has no README: someone who did not write it cannot tell how to install, "
                    "run or test it. Write one in the project directory with those commands."]
        lacks = []
        text = readme.read_text(encoding="utf-8", errors="replace")
        ways = _ways_to_run(root, project, pack)
        if not any(way in text for way in ways) and not (pack is None and _A_COMMAND_BLOCK.search(text)):
            lacks.append(f"`{readme.relative_to(root).as_posix()}` says nowhere how to run the product: name the "
                         "commands that install, start and test it" + (f" (here: {', '.join(ways[:4])})" if ways else "") + ".")
        routes = list(dict.fromkeys((c.method, c.path) for c in the_locked_contract(root) if c.kind == "http"))
        missing = _routes_not_named(_the_product_s_documents(root, project), routes)
        if missing:
            lacks.append("No document of the product summarises these routes it serves (method and path on one "
                         "line, with what each takes and returns): " + ", ".join(missing[:12])
                         + (f" and {len(missing) - 12} more" if len(missing) > 12 else "") + ".")
        return lacks
    except Exception:  # noqa: BLE001 - a release is not held back by a check that could not run
        logger.warning("Could not check the product's documentation", exc_info=True)
        return []


__all__ = ["ON_BY_DEFAULT", "README_NAMES", "enabled", "what_the_handoff_lacks"]
