"""A README with run instructions, and for a service an API summary, required at release (plan PN.2, behind `RELEASE_DOCS_REQUIRED`).

A product was released with every criterion passing and nothing a person who
did not write it could start it from: the release packs CI and container
files, and no check asked whether the handoff says how to run the product or
what it serves. With the switch on, the release is held back - like a failing
criterion, at most until its attempts run out, then recorded as a gap - when:

- the project has no README;
- the README names no way to run it: none of the pack's own commands or, with
  no pack, of the commands the project and its suite declare, no `start.sh`, no
  entrypoint, and when no pack covers it no block with a command of its own (one
  showing only a request or an answer says nothing of how to run the product);
- for a product whose locked interface contract has HTTP routes, a route that
  no README or document of the project names, method and path on one line.

Every check reads files; none asks a model.
"""

from __future__ import annotations

import logging
import re
import shlex
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `RELEASE_DOCS_REQUIRED` set to on or off overrides this.
ON_BY_DEFAULT = False
#: README names looked for, project directory first, then the workspace root.
README_NAMES = ("README.md", "README.rst", "README.txt", "README")
#: Documents the harness writes about the run, never the product's own.
_THE_HARNESS_S_DOCS = ("decision_log", "product_intake", "reviews", "sprint", "release-evidence")
_A_PARAMETER = re.compile(r"\{[^}/]*\}|:[A-Za-z_]\w*|<[^>/]*>")
_A_TRAILING_SLASH = re.compile(r"(?<=[\w}])/(?=[\s`|),.;:]|$)")
_A_FENCED_BLOCK = re.compile(r"^```[^\n]*\n(.*?)^```", re.M | re.S)
_AN_INDENTED_LINE = re.compile(r"^(?: {4}|\t|\$ )(\S.*)$", re.M)
#: A line of a block that shows a request or its answer, or says nothing: it runs no product.
_NOT_A_WAY_TO_RUN = re.compile(r"(?:\$\s+)?(?:(?:curl|wget|https?|HTTP/)\b|(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s|[#{}\[\]\"'<]|//)")


def enabled() -> bool:
    return is_on("RELEASE_DOCS_REQUIRED", ON_BY_DEFAULT)


def _the_readme(root: Path, project: str) -> Path | None:
    for base in ([root / project] if project else []) + [root]:
        for name in README_NAMES:
            if (base / name).is_file():
                return base / name
    return None


def _the_pinned_project(root: Path) -> str:
    """The project directory the suite and the run's pin name, for a run no pack scaffolded; "" when none.

    Without it a README in the project directory was looked for at the
    workspace root only, and the release was held back for one it had.
    """
    try:
        from app.acceptance import suite

        where = suite.location(root)
        return where[0] if where else ""
    except Exception:  # noqa: BLE001
        return ""


def _what_a_project_with_no_pack_declares(root: Path) -> tuple[list[str], list[str], list[str]]:
    """(install, start, test) commands the harness itself knows of a project no pack covers. Only reads.

    The start command is the one the harness starts the product with, the test
    command the one the suite declares and the release has just run.
    """
    from app.acceptance import start_output, suite
    from app.stacks import contract

    install = [shlex.join(str(a) for a in argv) for argv in (contract.read(root) or {}).get("install") or []]
    started = start_output.command_for(root)
    declared = suite._command(root)  # noqa: SLF001 - the suite's own reading of its declaration
    return install, [shlex.join(started[0])] if started else [], [shlex.join(declared[0])] if declared else []


def _ways_to_run(root: Path, project: str, pack: object | None) -> list[str]:
    ways = ["start.sh"]
    if pack is not None:
        ways += [shlex.join(argv) for argv in getattr(pack, "install", ()) or ()]
        ways += [shlex.join(getattr(pack, name, ()) or ()) for name in ("unit_test", "acceptance_test")]
        ways += [Path(e).name for e in (getattr(pack, "entrypoints", ()) or ()) if e]
        if getattr(pack, "entrypoint", ""):
            ways.append(Path(pack.entrypoint).name)
    else:
        from app.acceptance.interface_contract import the_locked_contract

        install, start, test = _what_a_project_with_no_pack_declares(root)
        ways += start
        # A service nobody can say how to start is not told how to run by the command of its tests.
        if start or not any(c.kind == "http" for c in the_locked_contract(root)):
            ways += [*install, *test]
    return [w for w in dict.fromkeys(ways) if w.strip()]


def _the_product_s_documents(root: Path, project: str) -> str:
    texts = []
    for base in dict.fromkeys(([root / project] if project else []) + [root]):
        readmes = [base / n for n in README_NAMES]
        for path in [*readmes, *sorted((base / "docs").glob("**/*.md"))]:
            # The harness's documents by their path under `docs/`: matched on the
            # whole path, a project called `book-reviews` had every document left out.
            within = path.relative_to(base / "docs").as_posix() if path not in readmes else ""
            if path.is_file() and not any(part in within for part in _THE_HARNESS_S_DOCS):
                try:
                    texts.append(path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
    return "\n".join(texts)


def _a_block_runs_something(text: str, root: Path) -> bool:
    """Whether a block of the README holds a line that could start the product: not a request, an answer, or the install and test commands the harness wrote."""
    install, _, test = _what_a_project_with_no_pack_declares(root)
    lines = [line for block in _A_FENCED_BLOCK.findall(text) for line in block.splitlines()]
    lines += _AN_INDENTED_LINE.findall(_A_FENCED_BLOCK.sub("", text))
    return any(line.strip() and not _NOT_A_WAY_TO_RUN.match(line.strip()) and line.strip() not in {*install, *test}
               for line in lines)


def _shape(path: str) -> str:
    return _A_PARAMETER.sub("{}", path.rstrip("/") or "/")


def _routes_not_named(documents: str, routes: list[tuple[str, str]]) -> list[str]:
    # A path written with its trailing slash (`/items/`) is the same route the
    # contract's shape names without it.
    lines = [(line.upper(), _A_TRAILING_SLASH.sub("", _shape(line))) for line in documents.splitlines()]
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
        project = str((record or {}).get("project") or "") or _the_pinned_project(root)
        readme = _the_readme(root, project)
        if readme is None:
            return ["The project has no README: someone who did not write it cannot tell how to install, "
                    "run or test it. Write one in the project directory with those commands."]
        lacks = []
        text = readme.read_text(encoding="utf-8", errors="replace")
        ways = _ways_to_run(root, project, pack)
        if not any(way in text for way in ways) and not (pack is None and _a_block_runs_something(text, root)):
            # With no pack `start.sh` is only what a README may name: not offered as the product's when it has none.
            shown = [w for w in ways if pack is not None or w != "start.sh" or (root / project / w).is_file()]
            lacks.append(f"`{readme.relative_to(root).as_posix()}` says nowhere how to run the product: name the "
                         "commands that install, start and test it" + (f" (here: {', '.join(shown[:4])})" if shown else "") + ".")
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


def _the_pack_s_start(pack: Any) -> list[str]:
    """How the pack starts the product when it has no start script: its kept `start` script, or nothing."""
    scripts = getattr(pack, "kept_scripts", None) or {}
    if isinstance(scripts, dict) and scripts.get("start"):
        return ["npm start"] if str(getattr(pack, "language", "")) in ("javascript", "typescript") else []
    return []


def _the_running_and_testing_sections(where: str, commands: list[str], install: list[str], test: list[str]) -> str:
    """Install and start in one section, the start on its own line said to keep running, and the tests apart.

    One fence holding the start and then the tests could not run as written: the start never returns (HR2.PR.2).
    """
    installing = [c for c in commands if c in install]
    testing = [c for c in commands if c in test and c not in installing]
    starting = [c for c in commands if c not in installing and c not in testing]
    out = ""
    if installing or starting:
        out += f"\n## Running it\n\n{where}\n\n"
        if installing:
            out += "```sh\n" + "\n".join(installing) + "\n```\n\n"
        if starting:
            out += ("Then start it; it stays running until you stop it (Ctrl-C):\n\n"
                    "```sh\n" + "\n".join(starting) + "\n```\n")
    if testing:
        out += f"\n## Testing it\n\n{where} (in another terminal; the acceptance tests need it running):\n\n" \
               "```sh\n" + "\n".join(testing) + "\n```\n"
    return out


#: A Configuration entry of the specification: `- variable: PORT; type: ...; default: 8000; description: ...`.
_A_VARIABLE = re.compile(r"^\s*[-*]\s*variable:\s*`?([A-Za-z_][A-Za-z0-9_]*)`?\s*;(.*)$", re.IGNORECASE)


def _the_configuration(root: Path) -> list[tuple[str, str, str]]:
    """(name, default, what it sets) for each variable the specification's Configuration section lists."""
    try:
        text = (root / "docs" / "technical_specification.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    section = re.search(r"^## Configuration\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    found: list[tuple[str, str, str]] = []
    for line in (section.group(1) if section else "").splitlines():
        match = _A_VARIABLE.match(line)
        if not match:
            continue
        fields = {}
        for part in match.group(2).split(";"):
            key, _, value = part.partition(":")
            fields[key.strip().lower()] = " ".join(value.split()).replace("|", "/")
        default = re.sub(r"\s*\(.*?\)", "", fields.get("default", ""))[:60]
        found.append((match.group(1), default, fields.get("description", "")[:160]))
    return list(dict.fromkeys(found))


#: A shell default in a start script: `${PORT:-8000}`, `${DATA_DIR:-data}`.
_A_SHELL_DEFAULT = re.compile(r"\$\{([A-Z][A-Z0-9_]*):-([^}]*)\}")


def _what_the_start_script_reads(base: Path) -> list[tuple[str, str, str]]:
    """(name, default, "") for each variable `start.sh` reads with a default; [] with no start script."""
    try:
        text = (base / "start.sh").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return list(dict.fromkeys((name, default.strip().strip("\"'"), "read by `start.sh`")
                              for name, default in _A_SHELL_DEFAULT.findall(text)))


def complete_the_handoff(repo_root: str | Path) -> list[str]:
    """Write what the harness itself knows into the README - how to run the product, the routes it serves; the files written.

    A model was sent back from the release for a README while every fact it
    needs is the harness's own: the pack's commands and the routes locked in
    the interface contract. Measured on a Measure run that passed every hidden
    test: the product had no README, so with this check on every release
    would have gone back to the lead for one. Written from those facts, it
    costs no model call; what it cannot know is still asked for. Off with
    the switch; never raises. With no pack the facts are the project's own
    start command and the suite's declared one, measured on a run that spent two
    rounds of the sprint on a one-line README; with none of them known, no README
    is begun and the lack stays. Only ever appends.
    """
    if not enabled():
        return []
    try:
        from app.acceptance.interface_contract import the_locked_contract
        from app.stacks import contract

        root = Path(repo_root)
        found = contract.the_pack(root)
        pack, record = found if found else (None, contract.read(root) or {})
        project = str((record or {}).get("project") or "") or _the_pinned_project(root)
        if pack is None:
            install, start, test = _what_a_project_with_no_pack_declares(root)
            if not (install or start or test) and _the_readme(root, project) is None:
                return []
        readme = _the_readme(root, project) or (root / project / "README.md" if project else root / "README.md")
        text = readme.read_text(encoding="utf-8", errors="replace") if readme.is_file() else (
            f"# {(record or {}).get('title') or project or root.name}\n")
        added = ""
        ways = _ways_to_run(root, project, pack)
        if not any(way in text for way in ways):
            base = root / project if project else root
            if pack is None:
                commands = [*install, *start, *test]
            else:
                commands = [shlex.join(argv) for argv in getattr(pack, "install", ()) or ()]
                commands += ["sh start.sh"] if (base / "start.sh").is_file() else _the_pack_s_start(pack)
                commands += [shlex.join(getattr(pack, name, ()) or ()) for name in ("unit_test", "acceptance_test")]
            # A command the README already has is not added again, on a later attempt included.
            commands = [c for c in dict.fromkeys(commands) if c.strip() and c not in text]
            if commands:
                # A README at the workspace root runs the project's commands from the project.
                where = (f"From `{project}/`:" if project and readme.parent != root / project else "From this directory:")
                added += _the_running_and_testing_sections(where, commands, install if pack is None else [
                    shlex.join(argv) for argv in getattr(pack, "install", ()) or ()],
                    test if pack is None else [shlex.join(getattr(pack, name, ()) or ()) for name in ("unit_test", "acceptance_test")])
        # The specification's variables, else the ones the start script reads with their defaults (HR2.G.4).
        declared = _the_configuration(root) or _what_the_start_script_reads(root / project if project else root)
        variables = [v for v in declared if v[0] not in text]
        if variables:
            # What the product reads, from the specification's own Configuration (HR2.PR.2): 3 of 63 READMEs named
            # `PORT` or `DATA_DIR`, though every specification listed them.
            added += ("\n## Configuration\n\n| Variable | Default | What it sets |\n| --- | --- | --- |\n"
                      + "\n".join(f"| `{name}` | {default or ''} | {meaning} |" for name, default, meaning in variables) + "\n")
        locked = [c for c in the_locked_contract(root) if c.kind == "http"]
        # Named in the README itself: the specification under `docs/` naming the routes once kept the table out of
        # the README a stranger reads (HR2.PR.2: 3 of 63 READMEs named a route).
        missing = set(_routes_not_named(text + "\n" + added, list(
            dict.fromkeys((c.method, c.path) for c in locked))))
        rows = [f"| {c.method} | `{c.path}` | {c.status or ''} |" for c in locked if f"{c.method} {c.path}" in missing]
        if rows:
            added += ("\n## What it serves\n\n| Method | Path | Answers |\n| --- | --- | --- |\n"
                      + "\n".join(dict.fromkeys(rows)) + "\n")
        if not added:
            return []
        readme.parent.mkdir(parents=True, exist_ok=True)
        readme.write_text(text.rstrip("\n") + "\n" + added, encoding="utf-8")
        return [readme.relative_to(root).as_posix()]
    except Exception:  # noqa: BLE001 - what is left is asked for, as before
        logger.warning("Could not complete the product's README", exc_info=True)
        return []


__all__ = ["ON_BY_DEFAULT", "README_NAMES", "complete_the_handoff", "enabled", "what_the_handoff_lacks"]
