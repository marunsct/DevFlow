"""What an IDE would underline in a source file, from the language service an IDE uses.

JavaScript and TypeScript are read by the TypeScript language service (below);
Python by Pyright, the engine of VS Code's Python support (at the end).

A parse says whether a file can be read. An IDE says more, before anything
runs: a name nothing defines, an import of something a module does not export,
a relative import of a file that is not there. Those are the failures this
harness's runs kept meeting only at test time - `init is not defined`,
`render is not defined`, a test importing a name its module never exported -
each costing a test round and a fix stage to find.

VS Code gets them from the TypeScript language service, which reads JavaScript
too. So does this: the compiler installed beside Node (or the project's own),
over the whole project, with the file as it is about to be written.

Only what is certain is reported. Measured over the 138 stored JavaScript
products, type checking on plain JavaScript is overwhelmingly noise - implicit
`any`, possibly-null, `Element` read as `HTMLElement` - which is why an IDE does
not show it for a `.js` file either. These codes are kept because each means
the code fails when it runs:

    2304, 2552  a name nothing defines          -> ReferenceError
    2448-2450   a const/let, class or enum used before its declaration runs
                                                -> ReferenceError ("Cannot access
                                                   'x' before initialization")
    2305, 2614  an import of a missing export   -> SyntaxError at load
    1192, 2613  a default import of none (2613 when a named export of
                that name exists: `import X` for `export const X`)
                                                -> SyntaxError at load
    2306        an import from a file that is not a module
    2307        a relative import of a file that does not exist
    2339, 2551  a call of a method no built-in type has, on a value of a
                built-in type (an element, a string, an array)
                                                -> TypeError ("... is not a
                                                   function"). One run's page
                                                   called `list.removeChildren()`
                                                   and every test failed on load.
                                                   Only a name no built-in type
                                                   declares, so an element typed
                                                   too loosely (`select()` on an
                                                   `HTMLElement`) is never flagged.

and only where they mean that: never inside a comment (a JSDoc type is not
code), never on a name read only through `typeof` (which cannot throw), never
a package import (a package's types may simply not be installed), and the
globals a file may use are those of where it runs - a browser's for a page's
code, Node's for a service's. Over the stored products that left 80 reports in
15 products, every one sampled a real fault.

Notes, never refusals: a name may be defined by a file another work order has
not written yet, as an IDE's underline can be while a change is half made.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

#: Files the TypeScript service reads; Python goes to Pyright (below).
SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts")
#: Every file some language service here reads.
ALL_SUFFIXES = (*SUFFIXES, ".py")

#: Program creation, the DOM's declarations included, is most of the cost.
TIMEOUT_SECONDS = 30

#: How many findings one note carries.
MOST_FINDINGS = 8

#: Where a file's code runs, which decides the globals it may use.
BROWSER, NODE, BOTH = "browser", "node", "both"

_SCRIPT = r"""
const [compiler, project, target, runtime, checkNames] = process.argv.slice(1);
const ts = require(compiler);
const fs = require('fs'), path = require('path');
let content = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', d => content += d).on('end', () => {
  const SKIP = new Set(['node_modules', 'test-results', 'playwright-report', '.git', 'dist', 'build',
                        'coverage', '.agent-home', '.venv', '.harness']);
  const roots = [];
  (function walk(d, depth) {
    if (depth > 8) return;
    let entries = [];
    try { entries = fs.readdirSync(d, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      if (SKIP.has(e.name)) continue;
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p, depth + 1);
      else if (/\.(m?js|cjs|jsx|ts|tsx|mts|cts)$/.test(e.name) && !/\.d\.ts$/.test(e.name)) roots.push(p);
    }
  })(project, 0);
  const wanted = path.resolve(target);
  if (!roots.includes(wanted)) roots.push(wanted);
  const NODE_GLOBALS = '/harness/node-globals.d.ts';
  const nodeGlobals = 'declare var process: any; declare var require: any; declare var module: any;'
    + ' declare var exports: any; declare var __dirname: string; declare var __filename: string;'
    + ' declare var Buffer: any; declare var global: any; declare var setImmediate: any;'
    + ' declare var clearImmediate: any;';
  if (runtime !== 'browser') roots.push(NODE_GLOBALS);
  const options = {
    allowJs: true, checkJs: true, noEmit: true, strict: false, noImplicitAny: false,
    strictNullChecks: false, target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler, jsx: ts.JsxEmit.Preserve,
    lib: ['lib.esnext.d.ts', 'lib.dom.d.ts', 'lib.dom.iterable.d.ts'], types: [], skipLibCheck: true,
    maxNodeModuleJsDepth: 0, allowImportingTsExtensions: true,
    // A browser loads modules as ES modules and nothing else: a default import
    // from a module with no default export fails as the page loads. Node may
    // be importing CommonJS, where it would not, so there it is left alone.
    allowSyntheticDefaultImports: runtime !== 'browser', esModuleInterop: runtime !== 'browser',
  };
  const host = ts.createCompilerHost(options);
  const read = host.readFile.bind(host), exists = host.fileExists.bind(host), get = host.getSourceFile.bind(host);
  host.readFile = f => path.resolve(f) === wanted ? content : f === NODE_GLOBALS ? nodeGlobals : read(f);
  host.fileExists = f => path.resolve(f) === wanted || f === NODE_GLOBALS || exists(f);
  host.getSourceFile = (f, lang, onError, fresh) => {
    if (path.resolve(f) === wanted) return ts.createSourceFile(f, content, lang, true);
    if (f === NODE_GLOBALS) return ts.createSourceFile(f, nodeGlobals, lang, true);
    return get(f, lang, onError, fresh);
  };
  const program = ts.createProgram(roots, options, host);
  const NAMES = new Set([2304, 2552, 2448, 2449, 2450]);
  const IMPORTS = new Set([2305, 2614, 1192, 2613, 2306, 2307]);
  // A call of a method on a built-in type that no built-in type has at all.
  const MISSING_MEMBER = new Set([2339, 2551]);
  const checker = program.getTypeChecker();
  let libMembers = null;
  function builtInMembers() {
    if (libMembers) return libMembers;
    libMembers = new Set();
    for (const lib of program.getSourceFiles()) {
      if (!program.isSourceFileDefaultLibrary(lib)) continue;
      (function visit(n) {
        if ((ts.isInterfaceDeclaration(n) || ts.isClassDeclaration(n) || ts.isTypeLiteralNode(n)) && n.members) {
          for (const m of n.members) {
            if (m.name && (ts.isIdentifier(m.name) || ts.isStringLiteral(m.name))) libMembers.add(m.name.text);
          }
        }
        ts.forEachChild(n, visit);
      })(lib);
    }
    return libMembers;
  }
  function nodeAt(sf, pos) {
    let found;
    (function visit(n) {
      if (pos < n.getStart(sf) || pos >= n.getEnd()) return;
      found = n;
      ts.forEachChild(n, visit);
    })(sf);
    return found;
  }
  function builtIn(type) {
    const parts = type.isUnion() ? type.types : [type];
    return parts.length > 0 && parts.every(t => {
      const s = t.getSymbol() || t.aliasSymbol;
      const decls = (s && s.getDeclarations()) || [];
      return decls.length > 0 && decls.every(d => program.isSourceFileDefaultLibrary(d.getSourceFile()));
    });
  }
  function aMethodNoBuiltInHas(d, sf) {
    if (!MISSING_MEMBER.has(d.code) || d.start == null) return false;
    const name = nodeAt(sf, d.start);
    if (!name || !ts.isIdentifier(name)) return false;
    const access = name.parent;
    if (!access || !ts.isPropertyAccessExpression(access) || access.name !== name) return false;
    const call = access.parent;
    if (!call || !ts.isCallExpression(call) || call.expression !== access) return false;
    if (builtInMembers().has(name.text)) return false;
    return builtIn(checker.getTypeAtLocation(access.expression));
  }
  function comments(sf) {
    const ranges = [];
    const scanner = ts.createScanner(ts.ScriptTarget.ESNext, false, ts.LanguageVariant.Standard, sf.text);
    let kind;
    while ((kind = scanner.scan()) !== ts.SyntaxKind.EndOfFileToken) {
      if (kind === ts.SyntaxKind.SingleLineCommentTrivia || kind === ts.SyntaxKind.MultiLineCommentTrivia) {
        ranges.push([scanner.getTokenStart(), scanner.getTokenEnd()]);
      }
    }
    return ranges;
  }
  // A function handed to the page (`page.evaluate(() => init())`) runs in the
  // page, where the product's own globals live; what it names is the page's.
  const PAGE_CALLS = new Set(['evaluate', 'evaluateHandle', 'evaluateAll', 'addInitScript',
    'waitForFunction', '$eval', '$$eval', 'exposeFunction']);
  function runsInThePage(sf, pos) {
    for (let n = nodeAt(sf, pos); n; n = n.parent) {
      if ((ts.isArrowFunction(n) || ts.isFunctionExpression(n)) && n.parent && ts.isCallExpression(n.parent)) {
        const callee = n.parent.expression;
        if (ts.isPropertyAccessExpression(callee) && PAGE_CALLS.has(callee.name.text)) return true;
      }
    }
    return false;
  }
  function keep(d, sf, names) {
    if (d.start == null) return false;
    const member = names && aMethodNoBuiltInHas(d, sf);
    if (!(IMPORTS.has(d.code) || (names && NAMES.has(d.code)) || member)) return false;
    if (comments(sf).some(([a, b]) => d.start >= a && d.start < b)) return false;
    const before = sf.text.slice(Math.max(0, d.start - 12), d.start);
    if (NAMES.has(d.code) && /typeof\s*\(?\s*$/.test(before)) return false;
    if (NAMES.has(d.code) && runsInThePage(sf, d.start)) return false;
    if (d.code === 2307 || d.code === 2306) {
      const at = sf.text.slice(d.start, d.start + (d.length || 0));
      if (!/^['"`]\.{1,2}\//.test(at)) return false;
    }
    return true;
  }
  function describe(d, sf) {
    const at = sf.getLineAndCharacterOfPosition(d.start);
    return { line: at.line + 1, code: d.code,
             message: ts.flattenDiagnosticMessageText(d.messageText, ' ').split(path.resolve(project) + path.sep).join(''),
             text: sf.text.split('\n')[at.line].trim().slice(0, 160) };
  }
  // The file an import at `pos` loads, as the compiler resolves it; '' when it
  // resolves to nothing, null when `pos` is not in an import or export.
  function importedFile(sf, pos) {
    for (let n = nodeAt(sf, pos); n; n = n.parent) {
      if ((ts.isImportDeclaration(n) || ts.isExportDeclaration(n)) && n.moduleSpecifier) {
        const symbol = checker.getSymbolAtLocation(n.moduleSpecifier);
        const declaration = symbol && (symbol.getDeclarations() || [])[0];
        return declaration ? path.resolve(declaration.getSourceFile().fileName) : '';
      }
    }
    return null;
  }
  const here = [], elsewhere = [];
  const relativeTarget = path.relative(project, wanted);
  const stem = path.basename(wanted).replace(/\.[^.]+$/, '');
  for (const sf of program.getSourceFiles()) {
    const name = path.resolve(sf.fileName);
    if (!roots.includes(name) || name === NODE_GLOBALS) continue;
    const diagnostics = program.getSemanticDiagnostics(sf);
    if (name === wanted) {
      for (const d of diagnostics) if (keep(d, sf, checkNames === '1')) here.push(describe(d, sf));
    } else {
      for (const d of diagnostics) {
        if (![2305, 2614, 1192, 2613].includes(d.code) || !keep(d, sf, false)) continue;
        // Another file of the same name - `frontend/src/api/client.js` beside
        // `src/api/client.js` - is not this one: its importers are not blamed.
        const loads = importedFile(sf, d.start);
        const said = ts.flattenDiagnosticMessageText(d.messageText, ' ');
        const ours = loads === null ? said.includes(stem) : loads === wanted;
        if (ours) elsewhere.push({ file: path.relative(project, name), ...describe(d, sf) });
      }
    }
  }
  process.stdout.write(JSON.stringify({ here, elsewhere }));
});
"""


@dataclass
class Underlined:
    """What the language service found: in the file, and in files that import it."""

    here: list[dict] = field(default_factory=list)
    elsewhere: list[dict] = field(default_factory=list)

    def note(self) -> str:
        """The findings as prose for the stage that just wrote the file, or ""."""
        parts = []
        if self.here:
            grouped: dict[str, list[dict]] = {}
            for finding in self.here:
                grouped.setdefault(finding["message"], []).append(finding)
            lines = "\n".join(
                f"  line{'s' if len(found) > 1 else ''} {', '.join(str(f['line']) for f in found[:6])}: "
                f"{message}  ({found[0]['text']})"
                for message, found in list(grouped.items())[:MOST_FINDINGS]
            )
            parts.append(
                "IDE DIAGNOSTIC WARNING - The language service detected errors (e.g. ReferenceError/TypeError/SyntaxError) in this file that will fail when executed:\n"
                f"{lines}\n"
                "Fix these errors now before completing this stage."
            )
        if self.elsewhere:
            lines = "\n".join(
                f"  {f['file']} line {f['line']}: {f['message']}" for f in self.elsewhere[:MOST_FINDINGS]
            )
            parts.append(
                "And in files that import this one, which will now fail as they load:\n"
                f"{lines}\n"
                "Ensure exports and imports match."
            )
        if not parts:
            return ""
        # Work orders run side by side or one after another, so one importing a
        # file another work order has yet to write is expected, in either
        # execution mode. Without this a stage told to fix such an import now
        # wrote the other work order's file and was refused.
        return "\n".join(parts) + (
            "\nAn import of a file another work order is about to write clears when it "
            "does; leave that file to its owner."
        )


#: A test that imports its runner's functions: Playwright's and Node's own
#: runner define no globals, so every name such a file uses is one it defines
#: or imports. Measured on one run: QA's repair of a locked suite called
#: `getTask`, which nothing defined, and the suite was locked with a test that
#: could never pass - names were checked only in the product's code, because a
#: Jest or Vitest test may use globals its runner supplies.
_IMPORTS_ITS_RUNNER = re.compile(r"""(?:\bfrom\s+|\brequire\(\s*)['"](?:@playwright/test|node:test)['"]""")


def imports_its_runner(content: str) -> bool:
    """Whether a test file takes its runner's functions by import, so no name comes from a global."""
    return bool(_IMPORTS_ITS_RUNNER.search(content or ""))


def runs_in(repo_root: str | Path) -> str:
    """Where this run's product code runs, from its stack pack; both when unknown."""
    try:
        from app.stacks.contract import the_pack

        found = the_pack(repo_root)
    except Exception:  # noqa: BLE001
        found = None
    if found is None:
        return BOTH
    return found[0].code_runs_in or BOTH


def underlined(repo_root: str | Path, target: Path, content: str, project: Path | None = None) -> Underlined | None:
    """The language service's certain findings for `target` holding `content`; None when it cannot run.

    Names are checked only in the product's own code: tests run under a runner
    that supplies globals of its own, so there only imports are checked.
    """
    if target.suffix.lower() not in SUFFIXES:
        return None
    node = shutil.which("node")
    try:
        from app.analysis.typescript_parse import compiler_for

        compiler = compiler_for(target)
    except Exception:  # noqa: BLE001
        compiler = None
    if node is None or compiler is None:
        return None
    root = Path(repo_root)
    project = project or target.parent
    try:
        relative = target.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        relative = target.name
    try:
        from app.analysis.file_kinds import classify_file
        from app.stacks.contract import owned_by_the_harness

        if owned_by_the_harness(root, relative):
            return Underlined()
        kind = classify_file(relative)
        check_names = kind == "application" or (kind == "test" and imports_its_runner(content))
    except Exception:  # noqa: BLE001
        kind, check_names = "application", False
    # A test runs in Node and may reach into the page (`page.evaluate`), so it
    # may use the globals of both; the product's own code those of where it runs.
    runtime = runs_in(root) if kind == "application" else BOTH
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [node, "-e", _SCRIPT, compiler, str(project), str(target), runtime, "1" if check_names else "0"],
            input=content, capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("The language service could not run on %s", target, exc_info=True)
        return None
    if result.returncode != 0:
        logger.debug("The language service failed on %s: %s", target, result.stderr[-400:])
        return None
    try:
        found = json.loads(result.stdout or "{}")
    except ValueError:
        return None
    return Underlined(here=list(found.get("here") or []), elsewhere=list(found.get("elsewhere") or []))


# --- Python ---------------------------------------------------------------------

#: Pyright - VS Code's Python engine - with type checking off and only the rules
#: whose findings fail when the code runs. Measured: silent on the three Python
#: benchmark references, and it found each of a name nothing defines, an import
#: of a symbol its module lacks and a relative import of a missing module.
_PYRIGHT_RULES = {
    "typeCheckingMode": "off",
    "reportUndefinedVariable": "error",
    "reportAttributeAccessIssue": "error",
    "reportMissingImports": "error",
    "reportMissingModuleSource": "none",
}

#: Which of its findings are kept, by rule.
_PYTHON_RULES = frozenset({"reportUndefinedVariable", "reportAttributeAccessIssue", "reportMissingImports"})


def _pyright() -> str | None:
    """Pyright's entry script, installed beside Node, or None."""
    node = shutil.which("node")
    if node is None:
        return None
    for prefix in (Path(node).resolve().parent.parent, Path(node).parent.parent, Path("/usr/local")):
        candidate = prefix / "lib" / "node_modules" / "pyright" / "index.js"
        if candidate.is_file():
            return str(candidate)
    return None


def _a_local_import(message: str, project: Path) -> bool:
    """Whether an unresolved import names this project's own code (relative, or a top-level name here)."""
    import re

    found = re.search(r'Import "([^"]+)" could not be resolved', message)
    if not found:
        return True
    name = found.group(1)
    if name.startswith("."):
        return True
    top = name.split(".", 1)[0]
    return (project / top).is_dir() or (project / f"{top}.py").is_file() or (project / "src" / top).is_dir()


def _pyright_diagnostics(project: Path) -> list[dict] | None:
    """Pyright's diagnostics for every file of `project`, from one run; None when it cannot run."""
    import os
    import tempfile

    node, pyright = shutil.which("node"), _pyright()
    if node is None or pyright is None:
        return None
    try:
        with tempfile.TemporaryDirectory() as scratch:
            # Outside the product, so nothing is added to it; Pyright takes
            # only relative paths from its configuration, and the project is
            # the root its imports resolve from.
            here = os.path.relpath(project, scratch)
            config = dict(_PYRIGHT_RULES)
            config.update({
                "include": [here],
                "exclude": [f"{here}/**/.venv", f"{here}/**/node_modules", f"{here}/**/__pycache__"],
                "executionEnvironments": [{"root": here}],
            })
            if (project / ".venv").is_dir():
                config.update({"venvPath": here, "venv": ".venv"})
            path = Path(scratch) / "pyrightconfig.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            result = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [node, pyright, "--outputjson", "--project", str(path)],
                capture_output=True, text=True, timeout=TIMEOUT_SECONDS, cwd=scratch,
            )
        output = result.stdout or "{}"
        found = json.loads(output[output.find("{"):] if "{" in output else "{}")
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Pyright could not run on %s", project, exc_info=True)
        return None
    return list(found.get("generalDiagnostics") or [])


def _kept(diagnostic: dict, project: Path) -> tuple[int, str] | None:
    """The line and message of a finding that fails when the code runs, or None."""
    if diagnostic.get("rule") not in _PYTHON_RULES or diagnostic.get("severity") != "error":
        return None
    message = str(diagnostic.get("message") or "").strip()
    if not _a_local_import(message, project):
        return None
    return int(((diagnostic.get("range") or {}).get("start") or {}).get("line", 0)) + 1, message


def _finding(diagnostic: dict, line: int, message: str, lines: list[str]) -> dict:
    text = lines[line - 1].strip()[:160] if 0 < line <= len(lines) else ""
    return {"line": line, "code": diagnostic.get("rule"), "message": message, "text": text}


def python_underlined(repo_root: str | Path, target: Path, content: str, project: Path | None = None) -> Underlined | None:
    """Pyright's certain findings for a Python file already written as `content`; None when it cannot run.

    Pyright reads files from disk, so this answers for the file as written: a
    caller asking about content not yet on disk gets None.
    """
    if target.suffix.lower() != ".py":
        return None
    try:
        if target.read_text(encoding="utf-8", errors="replace") != content:
            return None
    except OSError:
        return None
    project = project or target.parent
    diagnostics = _pyright_diagnostics(project)
    if diagnostics is None:
        return None
    wanted = target.resolve()
    stem = target.stem
    lines = content.splitlines()
    here, elsewhere = [], []
    for diagnostic in diagnostics:
        kept = _kept(diagnostic, project)
        if kept is None:
            continue
        line, message = kept
        file = Path(str(diagnostic.get("file") or ""))
        if file.resolve() == wanted:
            here.append(_finding(diagnostic, line, message, lines))
        elif diagnostic.get("rule") == "reportAttributeAccessIssue" and "unknown import symbol" in message:
            try:
                source = file.read_text(encoding="utf-8", errors="replace").splitlines()[line - 1]
            except (OSError, IndexError):
                source = ""
            if stem in source:
                elsewhere.append({"file": file.relative_to(project).as_posix() if file.is_relative_to(project) else file.name,
                                  "line": line, "code": diagnostic.get("rule"), "message": message, "text": source.strip()[:160]})
    return Underlined(here=here, elsewhere=elsewhere)


def python_underlined_together(project: Path, targets: list[Path]) -> dict[Path, list[dict]] | None:
    """Each Python file's own findings, from one Pyright run over `project`; None when it cannot run.

    Pyright reads the whole project whichever file it is asked about, so asking
    file by file read it once a file: measured at the gate, 2 s a file and 45 s
    for one batch of 22 - which is why the gate read only the first 12 by name,
    and never read the router three test rounds then failed on, one missing
    name a round.
    """
    diagnostics = _pyright_diagnostics(project)
    if diagnostics is None:
        return None
    wanted = {target.resolve(): target for target in targets}
    found: dict[Path, list[dict]] = {target: [] for target in targets}
    lines_of: dict[Path, list[str]] = {}
    for diagnostic in diagnostics:
        kept = _kept(diagnostic, project)
        target = wanted.get(Path(str(diagnostic.get("file") or "")).resolve())
        if kept is None or target is None:
            continue
        if target not in lines_of:
            try:
                lines_of[target] = target.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                lines_of[target] = []
        found[target].append(_finding(diagnostic, *kept, lines_of[target]))
    return found


_FROM_IMPORT = __import__("re").compile(r"^\s*from\s+(\.*[\w.]*)\s+import\b")


def _python_module_defines(project: Path, importer: Path, line: str) -> tuple[Path, list[str]] | None:
    """The module a `from M import ...` line reads, and the top-level names it defines; None when not found here."""
    import ast

    found = _FROM_IMPORT.match(line or "")
    if found is None:
        return None
    spec = found.group(1)
    dots = len(spec) - len(spec.lstrip("."))
    parts = [part for part in spec.lstrip(".").split(".") if part]
    base = importer.parent
    for _ in range(max(0, dots - 1)):
        base = base.parent
    for start in ([base] if dots else [project, project / "src"]):
        stem = start.joinpath(*parts) if parts else start
        for candidate in (stem.with_suffix(".py"), stem / "__init__.py"):
            if candidate.is_file():
                try:
                    tree = ast.parse(candidate.read_text(encoding="utf-8", errors="replace"))
                except SyntaxError:
                    return candidate, []
                names: list[str] = []
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        names.append(node.name)
                    elif isinstance(node, ast.Assign):
                        names += [t.id for t in node.targets if isinstance(t, ast.Name)]
                    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                        names.append(node.target.id)
                    elif isinstance(node, (ast.Import, ast.ImportFrom)):
                        names += [(a.asname or a.name).split(".")[0] for a in node.names if a.name != "*"]
                return candidate, sorted(dict.fromkeys(names))
    if not dots:
        from app.analysis import package_exports

        names = package_exports.python_package_exports(project, spec)
        if names is not None:
            return Path(spec), names
    return None


_SCRIPT_IMPORT_FROM = __import__("re").compile(r"""\bfrom\s+['"]([^'"]+)['"]|\brequire\(\s*['"]([^'"]+)['"]\s*\)""")
#: What a JavaScript or TypeScript module exports: `export function f`, `export const c`, `export { a, b as c }`, `export default`.
_SCRIPT_EXPORTED = __import__("re").compile(
    r"^\s*export\s+(?:declare\s+)?(?:default\s+)?(?:async\s+)?(?:abstract\s+)?"
    r"(?:function\*?|class|const|let|var|interface|type|enum|namespace)\s+([A-Za-z_$][\w$]*)",
    __import__("re").M,
)
_SCRIPT_EXPORT_LIST = __import__("re").compile(r"^\s*export\s*(?:type\s*)?\{([^}]*)\}", __import__("re").M)
_SCRIPT_DEFAULT = __import__("re").compile(r"^\s*export\s+default\b", __import__("re").M)
_SCRIPT_EXTENSIONS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")


def _script_module_defines(project: Path, importer: Path, line: str) -> tuple[Path, list[str]] | None:
    """The module a relative `import ... from './m'` line reads, and the names it exports; None when not found here."""
    import re

    found = _SCRIPT_IMPORT_FROM.search(line or "")
    specifier = (found.group(1) or found.group(2)) if found else ""
    if not specifier:
        return None
    if not specifier.startswith("."):
        # A package, not a file of the project: what it really exports (a relative Path marks it as not the project's).
        from app.analysis import package_exports

        names = package_exports.script_package_exports(project, specifier)
        return (Path(specifier), names) if names is not None else None
    stem = (importer.parent / specifier).resolve()
    # TypeScript writes `./m.js` for a file that is `m.ts`.
    bare = stem.with_suffix("") if stem.suffix in _SCRIPT_EXTENSIONS else stem
    candidates = [stem] if stem.suffix in _SCRIPT_EXTENSIONS else []
    candidates += [Path(f"{bare}{extension}") for extension in _SCRIPT_EXTENSIONS]
    candidates += [bare / f"index{extension}" for extension in _SCRIPT_EXTENSIONS]
    for candidate in candidates:
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8", errors="replace")
            names = list(_SCRIPT_EXPORTED.findall(text))
            for listed in _SCRIPT_EXPORT_LIST.findall(text):
                for part in listed.split(","):
                    name = re.split(r"\s+as\s+", part.strip())[-1].strip()
                    if name and name != "default":
                        names.append(name)
            if _SCRIPT_DEFAULT.search(text):
                names.append("default")
            return candidate, sorted(dict.fromkeys(names))
    return None


#: What a module defines, by the importer's suffix: `(project, importer, import line) -> (module, names)`.
_MODULE_DEFINES: dict[str, Callable[[Path, Path, str], tuple[Path, list[str]] | None]] = {
    ".py": _python_module_defines,
    **{suffix: _script_module_defines for suffix in (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")},
}


def what_the_module_defines(project: Path, importer: Path, line: str) -> tuple[Path, list[str]] | None:
    """The module an import line reads and the names it defines, for a language that can say; else None."""
    reader = _MODULE_DEFINES.get(importer.suffix.lower())
    try:
        return reader(project, importer, line) if reader else None
    except Exception:  # noqa: BLE001 - a finding goes out as it was
        return None


#: A name an import asks for that the module does not have: Pyright's wording, then TypeScript's.
_A_MISSING_NAME = __import__("re").compile(
    r"\"([^\"]+)\" is unknown import symbol|has no exported member '([^']+)'|has no default export"
)


def the_names_the_module_has(project: Path, importer: Path, finding: dict) -> str:
    """A sentence naming what the module an import reads really defines, for a finding about a missing name; else "".

    The compiler says which name is missing and not which exist, so a writer guesses again: measured over one night,
    `create_access_token` imported from a module that defined `create_token`, `createApp` from one that exported
    `app`. The harness can read the module; a model's guess at it is not a fact.
    """
    message = str(finding.get("message") or "")
    wanted = _A_MISSING_NAME.search(message)
    if wanted is None:
        return _the_paths_the_package_has(project, message)
    answer = what_the_module_defines(project, importer, str(finding.get("text") or ""))
    if answer is None:
        return ""
    module, names = answer
    if not module.is_absolute():
        # A package: nothing in the project can add a name to it.
        return (f" `{module.as_posix()}` is a package; it exports only: {', '.join(names[:25]) or 'nothing readable'}"
                " - import one of those, or write the function yourself")
    try:
        shown = module.relative_to(project).as_posix()
    except ValueError:
        shown = module.name
    return (f" `{shown}` defines: {', '.join(names[:25])}" if names else f" `{shown}` defines no names")


_A_MISSING_MODULE = __import__("re").compile(r"Cannot find module '([^']+)'")


def _the_paths_the_package_has(project: Path, message: str) -> str:
    """A sentence naming the import paths of an installed package, after a finding about a path it does not export; else ""."""
    found = _A_MISSING_MODULE.search(message)
    if found is None:
        return ""
    from app.analysis import package_exports

    paths = package_exports.package_paths(project, found.group(1))
    if not paths:
        return ""
    return f" `{found.group(1)}` is not a path that package exports; the paths it exports are: {', '.join(paths[:30])}"


#: The service that reads each suffix, as a finding names it; the rest are the TypeScript service's.
_SERVICE_NAMES = {".py": "Pyright"}
#: Suffixes whose service reads the whole project in one run, so a batch of
#: them is read in that one run: `(project, targets) -> {target: findings}`.
_READ_TOGETHER: dict[str, Callable[[Path, list[Path]], dict[Path, list[dict]] | None]] = {}


def service_name(path: str | Path) -> str:
    """The language service that reads this file, as a finding should name it."""
    return _SERVICE_NAMES.get(Path(str(path)).suffix.lower(), "the TypeScript language service")


def underlined_in(
    repo_root: str | Path, relatives: list[str], project: Path | None, most_one_by_one: int,
) -> dict[str, list[dict]]:
    """Each file's certain findings, by its path relative to `repo_root`; a file not read is left out.

    A language whose service reads the whole project in one run is read so,
    every file of it at once, whatever the batch's size; the others file by
    file, in the order given, up to `most_one_by_one`. Measured at the gate:
    Pyright asked file by file re-read the project each time, 2 s a file, and
    a cap on the count, applied by name, left the router of a 22-file batch
    unread while its imports stopped the service three rounds running.
    """
    root = Path(repo_root)
    found: dict[str, list[dict]] = {}
    together: dict[tuple[str, Path], list[str]] = {}
    one_by_one: list[str] = []
    for relative in relatives:
        suffix = Path(relative).suffix.lower()
        if suffix in _READ_TOGETHER:
            together.setdefault((suffix, project or (root / relative).parent), []).append(relative)
        else:
            one_by_one.append(relative)
    for (suffix, where), group in together.items():
        try:
            read = _READ_TOGETHER[suffix](where, [root / relative for relative in group])
        except Exception:  # noqa: BLE001 - a check that cannot run finds nothing
            read = None
        for relative in group:
            found[relative] = (read or {}).get(root / relative) or []
    for relative in one_by_one[:most_one_by_one]:
        target = root / relative
        try:
            result = underlined_any(root, target, target.read_text(encoding="utf-8", errors="replace"), project)
        except Exception:  # noqa: BLE001 - a check that cannot run finds nothing
            result = None
        found[relative] = result.here if result is not None else []
    return found


def underlined_any(repo_root: str | Path, target: Path, content: str, project: Path | None = None) -> Underlined | None:
    """The language service for this file's language, or None when there is none here."""
    if target.suffix.lower() == ".py":
        return python_underlined(repo_root, target, content, project)
    return underlined(repo_root, target, content, project)


_READ_TOGETHER[".py"] = lambda project, targets: python_underlined_together(project, targets)


__all__ = [
    "BOTH", "BROWSER", "NODE", "SUFFIXES", "Underlined", "python_underlined", "python_underlined_together", "runs_in",
    "service_name", "the_names_the_module_has", "underlined", "underlined_any", "underlined_in", "what_the_module_defines",
]
