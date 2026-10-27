"""The compiler's errors that name something which does not exist, added to the "product does not start" defect (behind `START_DEFECT_NAMES_COMPILER_ERRORS`).

Measured over three small-model runs on a TypeScript service: the product did not start for the first half hour, and
each fixer was shown the one crash the runtime printed - a package path Hono does not export, then a name
`node:fs/promises` does not have, then a host written `127.0.0-1` - one at a time, a fix and a round apart. The
compiler had the whole list at the first round (14 errors in one project). A pack that declares a `typecheck`
command has it run once when the product fails to start, and the errors that name a missing name, export, member or
module - not the type complaints Node's own type stripping never reads - go with the defect, with what each package
really exports where the language service knows it.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable, Sequence

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False

#: How many errors go with the defect.
MOST_ERRORS = 12

#: Errors about something that is not there: a name, a module, an export, a member, a path. The rest are type
#: complaints (an implicit `any`, a value of the wrong type) that do not stop a program Node runs as it is.
_MISSING = frozenset({2304, 2305, 2306, 2307, 2339, 2551, 2552, 2614, 2724, 2792})

#: A value of the wrong kind where a function or a component is wanted - a router handed to `app.use` for `app.route`
#: made every request throw in one run - and "no overload matches".
_THE_WRONG_KIND = frozenset({2345, 2769})

#: A type imported as a value (`import { Note }` where `Note` is an interface), and its re-export form. Node's type
#: stripping keeps the import and the program stops with "does not provide an export named 'Note'": measured on a
#: small-model run, the start defect named another error and the fixers never saw this one.
_A_TYPE_IMPORTED_AS_A_VALUE = frozenset({1484, 1485})

_ERROR = re.compile(r"^(?P<file>[^\s(][^(]*)\((?P<line>\d+),\d+\):\s+error\s+TS(?P<code>\d+):\s+(?P<message>.*)$")

Runner = Callable[[Sequence[str], str, str], dict[str, Any]]


def enabled() -> bool:
    return is_on("START_DEFECT_NAMES_COMPILER_ERRORS", ON_BY_DEFAULT)


def parse(output: str) -> list[tuple[str, int, int, str]]:
    """`(file, line, code, message)` for each error line of the compiler's output that names something missing."""
    found: list[tuple[str, int, int, str]] = []
    lines = str(output or "").splitlines()
    for at, line in enumerate(lines):
        match = _ERROR.match(line.strip())
        if match is None or "node_modules" in match["file"]:
            continue
        code = int(match["code"])
        if code in _MISSING or code in _THE_WRONG_KIND or code in _A_TYPE_IMPORTED_AS_A_VALUE:
            message = match["message"].strip()
            # And the innermost line of its explanation, the one that says what is wrong: measured on one run,
            # "No overload matches this call." went to the fixers without "Type 'void' is not assignable to type
            # 'HandlerResponse<any>'" (a handler that returned nothing), and the product never started.
            below = []
            for following in lines[at + 1:]:
                if not following[:1].isspace():
                    break
                if following.strip():
                    below.append(following.strip())
            if below and below[-1] != message:
                message = f"{message} {below[-1][:240]}"
            found.append((match["file"].strip(), int(match["line"]), code, message))
    # The product's files first: its own faults stop it, a test's do not.
    return sorted(found, key=lambda item: (item[0].startswith(("test", "acceptance", "tests"))))


def _what_the_module_has(project: Path, file: str, line: int, message: str) -> str:
    """The sentence naming what the module an import reads really exports, when the language service can say."""
    # A name a module lacks, or a package path it does not export (`Cannot find module 'hono/middleware'`).
    if "has no exported member" not in message and "Cannot find module '" not in message:
        return ""
    try:
        from app.analysis.language_service import the_names_the_module_has

        importer = project / file
        text = importer.read_text(encoding="utf-8", errors="replace").splitlines()[line - 1]
        return the_names_the_module_has(project, importer, {"message": message, "text": text})
    except Exception:  # noqa: BLE001 - the error stands as the compiler said it
        return ""


def _in_a_kept_file(project: Path, file: str, line: int, prefix: str = "") -> str:
    """What to do about an error in a file the harness keeps: the file stays, what it uses changes.

    Measured on a small-model run: `createApp` was made `async`, the kept `src/main.ts` then handed `serve` the
    `fetch` of a Promise, every request answered 500, and the compiler's error was on `main.ts` line 7 - a file no
    stage may change - so nothing pointed at `createApp`.
    """
    try:
        whole = (project / file).read_text(encoding="utf-8", errors="replace")
        text = whole.splitlines()[line - 1].strip()
    except (OSError, IndexError):
        whole, text = "", ""
    shown = f" (`{text[:160]}`)" if text else ""
    # Where the names on that line come from, so the change lands in the file that defines them.
    sources = []
    for names, spec in _NAMED_IMPORT.findall(whole):
        used = [name for name in re.findall(r"[A-Za-z_$][\w$]*", names) if name != "type" and re.search(rf"\b{re.escape(name)}\b", text)]
        if used and spec.startswith("."):
            target = (Path(file).parent / spec).as_posix()
            sources.append(f"`{', '.join(used)}` in `{prefix}{target.removeprefix('./')}`")
    where = f" - {'; '.join(sources)}" if sources else ", in the product's own files"
    return (f" - this file is the harness's and stays exactly as it is{shown}: change what it uses{where}, so that "
            "this line is right as written.")


#: `import { a, b } from './x.ts'` - the names and the module.
_NAMED_IMPORT = re.compile(r"""import\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]""")


def the_errors(repo_root: str | Path, runner: Runner | None = None) -> str:
    """The text to add to the start defect: the compiler's missing-name errors, or "" when off, undeclared or clean."""
    if not enabled():
        return ""
    try:
        from app.stacks import contract

        found = contract.the_pack(repo_root)
        if found is None or not getattr(found[0], "typecheck", ()):
            return ""
        pack, record = found
        project = str(record.get("project") or "")
        if runner is None:
            from app.stacks.scaffold import sandbox_runner

            runner = sandbox_runner(repo_root)
        outcome = runner(list(pack.typecheck), "default", project) or {}
        output = f"{outcome.get('stdout') or ''}\n{outcome.get('stderr') or ''}"
        errors = parse(output)[:MOST_ERRORS]
        if not errors:
            return ""
        base = Path(repo_root) / project if project else Path(repo_root)
        prefix = f"{project}/" if project else ""
        kept = contract.kept_paths(repo_root)
        lines = [
            f"- {prefix}{file} line {line}: {message}{_what_the_module_has(base, file, line, message)}"
            f"{_in_a_kept_file(base, file, line, prefix) if f'{prefix}{file}' in kept else ''}"
            for file, line, _code, message in errors
        ]
        return (
            f"\n\nThe compiler (`{' '.join(pack.typecheck)}`) also reports these names, modules or members that do not "
            "exist in the product's files. Each is something the product cannot run with, not only the first one the "
            "runtime stopped on; correct all of them in this one change:\n" + "\n".join(lines)
        )
    except Exception:  # noqa: BLE001 - a check that cannot run adds nothing
        logger.debug("Could not add the compiler's errors to the start defect", exc_info=True)
        return ""


__all__ = ["MOST_ERRORS", "ON_BY_DEFAULT", "enabled", "parse", "the_errors"]
