"""Parse TypeScript and JSX with the TypeScript compiler's own parser.

`node --check` reads JavaScript and nothing else, so `.ts`, `.tsx` and `.jsx`
were the one family of files a web project is made of that went unparsed at
the write. A grammar would do - see `app.analysis.grammar_parse` - but measured
over 3,600 real TypeScript files a grammar reported an error in about one in a
hundred that the compiler accepts, and a check that refuses a correct file
costs a run more than the broken file would have.

So the compiler is asked, in the mode that parses and nothing more:
`transpileModule` reports syntax errors only - no types, no imports resolved,
no project configuration read - so a file is never refused for something that
is not a syntax error, and nothing has to be installed first for the answer to
be right.

The compiler is the project's own when it has one (`node_modules/typescript`
above the file), so the syntax accepted is the syntax that project's build
accepts; otherwise the one installed beside Node. With neither, this says
nothing, and the grammar's reading is offered as a note instead.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

#: Extensions the TypeScript parser reads that Node's does not.
PARSEABLE = (".ts", ".tsx", ".mts", ".cts", ".jsx")

#: Loading the compiler is most of the cost; a parse is milliseconds after it.
TIMEOUT_SECONDS = 20

#: Reads the source on stdin, prints the first syntax error as JSON and exits
#: 1, or exits 0. Exit 3 is "the compiler could not be loaded", which is not
#: an opinion about the file.
_CHECK = r"""
let ts;
try { ts = require(process.argv[1]); } catch (e) { process.exit(3); }
let src = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', d => src += d).on('end', () => {
  const out = ts.transpileModule(src, {
    fileName: process.argv[2],
    reportDiagnostics: true,
    compilerOptions: { jsx: ts.JsxEmit.Preserve, target: ts.ScriptTarget.ESNext,
                       module: ts.ModuleKind.ESNext, allowJs: true },
  });
  const d = (out.diagnostics || []).find(x => x.category === ts.DiagnosticCategory.Error && x.file);
  if (!d) process.exit(0);
  const at = d.file.getLineAndCharacterOfPosition(d.start || 0);
  process.stdout.write(JSON.stringify({
    line: at.line + 1,
    message: ts.flattenDiagnosticMessageText(d.messageText, ' '),
  }));
  process.exit(1);
});
"""


@lru_cache(maxsize=1)
def _beside_node() -> str | None:
    """The compiler installed globally next to the Node on PATH, or None."""
    node = shutil.which("node")
    if node is None:
        return None
    for prefix in (Path(node).resolve().parent.parent, Path(node).parent.parent, Path("/usr/local")):
        candidate = prefix / "lib" / "node_modules" / "typescript"
        if (candidate / "lib" / "typescript.js").is_file():
            return str(candidate)
    return None


def compiler_for(path: Path | None) -> str | None:
    """The TypeScript package to parse `path` with: the project's, else the global one."""
    if path is not None:
        for directory in (path.parent, *list(path.parent.parents)[:6]):
            candidate = directory / "node_modules" / "typescript"
            try:
                if (candidate / "lib" / "typescript.js").is_file():
                    return str(candidate)
            except OSError:
                break
    return _beside_node()


def parse_error(path: Path, content: str) -> str | None:
    """The compiler's syntax error for `content` at `path`, or None. Never raises.

    None also means "could not be checked" - no Node, no compiler, a timeout.
    A write must not fail because a check could not run.
    """
    if path.suffix.lower() not in PARSEABLE:
        return None
    node = shutil.which("node")
    compiler = compiler_for(path)
    if node is None or compiler is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [node, "-e", _CHECK, compiler, path.name],
            input=content,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not run the TypeScript parser on %s", path, exc_info=True)
        return None
    if result.returncode != 1:
        return None
    try:
        found = json.loads(result.stdout)
        line, message = int(found["line"]), str(found["message"]).strip()
    except (ValueError, KeyError, TypeError):
        return None
    from app.analysis.javascript_parse import _around_the_failure

    return (
        f"TypeScript cannot parse this file on line {line}: {message} "
        "This is the TypeScript compiler's own parser, reporting syntax only - no "
        "types are checked - so the error is certain. A parser names the line where "
        "it gave up; what is missing is often at the end of the line before."
        + _around_the_failure(str(line), content)
    )


__all__ = ["PARSEABLE", "compiler_for", "parse_error"]
