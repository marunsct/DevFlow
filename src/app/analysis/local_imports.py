"""Check a relative import against the file it names, at the moment it is written.

`syntax_balance._unknown_named_imports` does this for `node:test` and
`node:assert`, whose exports are documented and fixed. A project's own modules
are knowable too - they are right there on disk - and getting them wrong is the
single most common way a test file fails in this harness.

Measured on run-454adf22, where two of five tests failed and neither failure was
about the product:

    SyntaxError: The requested module './app.js' does not provide an export
    named 'default'

    Error [ERR_MODULE_NOT_FOUND]: Cannot find module '.../test/app.mjs'
    imported from '.../test/app-regression-test2.test.mjs'

The first is a test importing a default from a module that has only named
exports. The second is a test inside `test/` importing `./app.mjs` when the
module sits in the directory above. Both are decidable from the two files, and
both cost that run a whole remediation round to discover.

Notes, never refusals. A file may legitimately be written before the module it
imports - a specialist writing a test first is doing the right thing - and this
cannot tell that from a wrong path. So it says what it found and, when the
module is somewhere else in the project, says where.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

#: `import x from './a.js'`, `import {a} from '../b.mjs'`, `export * from './c'`
_RELATIVE = re.compile(
    r"""(?:^|\n)\s*(?:import|export)\b[^;\n]*?from\s*['"](\.[^'"]*)['"]"""
    r"""|(?:^|\n)\s*import\s*['"](\.[^'"]*)['"]"""
    r"""|require\(\s*['"](\.[^'"]*)['"]\s*\)"""
)

#: The names taken out of one import statement, and the module it names.
_NAMED_FROM = re.compile(
    r"""import\s+(?P<clause>[^;'"]*?)\s+from\s*['"](?P<module>\.[^'"]*)['"]"""
)

#: What a module offers: `export default`, `export function a`, `export {a, b}`.
_EXPORT_DEFAULT = re.compile(r"^\s*export\s+default\b", re.M)
_EXPORT_DECLARED = re.compile(
    r"^\s*export\s+(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)",
    re.M,
)
_EXPORT_LIST = re.compile(r"^\s*export\s*\{([^}]*)\}", re.M)
_EXPORT_STAR = re.compile(r"^\s*export\s*\*", re.M)
_MODULE_EXPORTS = re.compile(r"^\s*module\.exports\b", re.M)

#: Extensions Node will try when the import names none. ESM requires the
#: extension, but a `.js` project under CommonJS does not, so both are tried
#: before anything is reported.
_TRIED = ("", ".js", ".mjs", ".cjs", ".json", "/index.js", "/index.mjs", "/index.cjs")

#: Directories that are not the project's own source.
_SKIP = {"node_modules", ".git", "dist", "build", "coverage", ".agent-home"}


def _resolve(source: Path, specifier: str) -> Path | None:
    """The file `specifier` names from `source`, or None if nothing is there."""
    base = (source.parent / specifier).resolve()
    for suffix in _TRIED:
        candidate = Path(str(base) + suffix) if suffix else base
        if candidate.is_file():
            return candidate
    return None


def _elsewhere(project: Path, specifier: str, target: Path | None = None) -> list[str]:
    """Where a module of that name actually is, as project-relative paths.

    Exact on the stem, and never the importing file itself. `rglob("app.*")`
    matched `app.test.mjs` as well as `app.js`, so a broken `./app.cjs` in
    `app.test.mjs` was answered "There is a file of that name at app.js,
    app.test.mjs" - naming a file that is not of that name, and telling the
    file to import itself. Measured on run d6297b2f's `defect_fix_1_0`, which
    got exactly that note.
    """
    name = specifier.rstrip("/").rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    if not stem:
        return []
    here = None
    if target is not None:
        try:
            here = target.resolve()
        except Exception:  # noqa: BLE001 - a hint must never fail the write
            here = None
    found: list[str] = []
    try:
        for candidate in project.rglob("*"):
            if not candidate.is_file() or candidate.stem != stem:
                continue
            if any(part in _SKIP for part in candidate.parts):
                continue
            if here is not None and candidate.resolve() == here:
                continue
            if candidate.suffix.lower() in {".js", ".mjs", ".cjs", ".json", ".ts"}:
                found.append(candidate.relative_to(project).as_posix())
    except Exception:  # noqa: BLE001 - a hint must never fail the write
        return []
    return sorted(found)[:3]


def _exports_of(text: str) -> tuple[set[str], bool, bool]:
    """(named exports, has a default, cannot be determined)."""
    if _MODULE_EXPORTS.search(text):
        # CommonJS: the shape is decided at runtime and cannot be read here.
        return set(), True, True
    names = set(_EXPORT_DECLARED.findall(text))
    for clause in _EXPORT_LIST.findall(text):
        for part in clause.split(","):
            name = part.strip().split(" as ")[-1].strip()
            if name == "default":
                continue
            if name:
                names.add(name)
        if re.search(r"\bas\s+default\b", clause):
            return names, True, False
    unknown = bool(_EXPORT_STAR.search(text))
    return names, bool(_EXPORT_DEFAULT.search(text)), unknown


def _wanted(clause: str) -> tuple[bool, set[str]]:
    """(wants a default, named bindings) from one import clause."""
    clause = clause.strip()
    named: set[str] = set()
    default = False
    braces = re.search(r"\{([^}]*)\}", clause)
    if braces:
        for part in braces.group(1).split(","):
            name = part.strip().split(" as ")[0].strip()
            if name:
                named.add(name)
        clause = clause[: braces.start()].rstrip().rstrip(",")
    head = clause.strip()
    if head and not head.startswith("*"):
        default = True
    return default, named


#: At most this many importers named in one note. Past a handful the message
#: is longer than the change that caused it.
MAX_IMPORTERS_NAMED = 4


#: A comment. `_RELATIVE` is anchored to the start of a line and so ignores
#: these already; `_NAMED_FROM` is not, and matches an import anywhere it
#: appears - including inside one.
_A_COMMENT = re.compile(r"""//[^\n]*|/\*.*?\*/""", re.S)


def _without_comments(text: str) -> str:
    """`text` with comments blanked, newlines kept."""
    return _A_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def who_would_break(target: Path, content: str, project: Path | None = None) -> list[str]:
    """Files importing names this module is about to stop exporting.

    `import_problems` asks "does what this file imports exist?" and is checked
    when that file is written. Nothing asked the reverse: when the *imported*
    module is written, does what it still exports satisfy the files that import
    it? Removing an export is silent, and the answer arrives a stage later as a
    failing test run.

    That silence is what keeps a run oscillating. Runs 0c5aabdb, d6297b2f and
    0afef410 all reached a genuine conflict - `index.html` loading `app.js`
    with a plain `<script>` tag needs a classic script, while `app.test.mjs`
    doing `import { addTask } from './app.js'` needs a module - and each of
    them alternated between satisfying one and satisfying the other. On run
    0afef410 the milestone reviewer named the fix that satisfies both, adding
    `type="module"` to the tag; the stage removed the exports instead, and
    nothing said the suite had just stopped being able to import anything.

    Silent for a module that uses `export *` or CommonJS, where what is
    exported cannot be read from the source.
    """
    project = project or target.parent
    if target.suffix.lower() not in {".js", ".mjs", ".cjs"}:
        return []
    exported, has_default, undecidable = _exports_of(content)
    if undecidable or _EXPORT_STAR.search(content):
        return []

    problems: list[str] = []
    try:
        # `os.walk` rather than `rglob`, so a skipped directory is never
        # descended into. This runs on every write, and `rglob` lists all of
        # `node_modules` before discarding it - about 5us an entry, which a
        # real install turns into a quarter of a second per write.
        for folder, subfolders, names in os.walk(project):
            subfolders[:] = [name for name in subfolders if name not in _SKIP]
            for name in sorted(names):
                importer = Path(folder) / name
                if importer == target:
                    continue
                if importer.suffix.lower() not in {".js", ".mjs", ".cjs"}:
                    continue
                text = _without_comments(
                    importer.read_text(encoding="utf-8", errors="replace")
                )
                for match in _NAMED_FROM.finditer(text):
                    if _resolve(importer, match.group("module")) != target:
                        continue
                    default, named = _wanted(match.group("clause"))
                    missing = sorted(named - exported)
                    if default and not has_default:
                        missing = ["default", *missing]
                    if not missing:
                        continue
                    problems.append(
                        f"{importer.relative_to(project).as_posix()} imports "
                        + ", ".join(f"`{name}`" for name in missing[:MAX_IMPORTERS_NAMED])
                        + f" from this file, and after this write it exports "
                        + (
                            "nothing"
                            if not exported and not has_default
                            else ", ".join(f"`{name}`" for name in sorted(exported)[:MAX_IMPORTERS_NAMED])
                        )
                        + ". That import throws when the file is loaded, so the "
                        "suite stops running - no syntax check catches it. Keep "
                        "the export, or change what imports it in the same step."
                    )
                    if len(problems) >= MAX_IMPORTERS_NAMED:
                        return problems
    except Exception:  # noqa: BLE001 - a hint must never fail the write
        return problems
    return problems


def import_problems(target: Path, content: str, project: Path | None = None) -> list[str]:
    """Everything wrong with this file's relative imports. Never raises."""
    if target.suffix.lower() not in {".js", ".mjs", ".cjs"}:
        return []
    project = project or target.parent
    problems: list[str] = []
    try:
        seen: set[str] = set()
        for groups in _RELATIVE.findall(content):
            specifier = next((g for g in groups if g), "")
            if not specifier or specifier in seen:
                continue
            seen.add(specifier)
            if _resolve(target, specifier) is not None:
                continue
            others = _elsewhere(project, specifier, target)
            where = (
                f" There is a file of that name at {', '.join(others)}."
                if others
                else ""
            )
            problems.append(
                f"`{specifier}` does not resolve to any file from "
                f"'{target.name}'.{where} The import fails when this file is "
                "loaded, which no syntax check catches."
            )

        for match in _NAMED_FROM.finditer(content):
            specifier = match.group("module")
            resolved = _resolve(target, specifier)
            if resolved is None or resolved.suffix.lower() not in {".js", ".mjs", ".cjs"}:
                continue
            try:
                exported, has_default, unknown = _exports_of(
                    resolved.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeDecodeError):
                continue
            if unknown:
                continue
            wants_default, named = _wanted(match.group("clause"))
            if wants_default and not has_default:
                offered = ", ".join(sorted(exported)) or "nothing"
                problems.append(
                    f"`{specifier}` has no default export, so a default import "
                    f"from it fails when the file is loaded. It exports: {offered}. "
                    f"Use `import {{ ... }} from '{specifier}'`."
                )
            for name in sorted(named - exported):
                offered = ", ".join(sorted(exported)) or "nothing"
                problems.append(
                    f"`{specifier}` does not export `{name}`, so this import "
                    f"fails when the file is loaded. It exports: {offered}."
                )
    except Exception:  # noqa: BLE001 - a hint must never fail the write
        return problems
    return problems


__all__ = ["import_problems", "who_would_break"]
