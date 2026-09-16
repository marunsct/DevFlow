"""Parse a JavaScript file with the parser that will actually load it.

`syntax_balance` counts brackets for the C family and says so plainly: it is a
structure check, not a parse, and it cannot see a missing semicolon or a
misplaced keyword. That is why a JavaScript file is warned about and a Python
file is refused - `ast.parse` is proof and brace counting is not.

For JavaScript there is proof available and it costs nothing. `node --check`
parses a file and reports its syntax errors without executing a line of it,
and Node is on the allowlist of every role because the products this harness
builds are mostly JavaScript. Measured in the worker container: five checks in
83 milliseconds.

run-454adf22 is what this is for. `app.js` was written with a stray `try`, and
the whole of `test_round_0` was spent discovering `SyntaxError: Unexpected
token 'try'` at line 83 and routing it back as a defect - a round trip through
the test round, the triage and a defect-fix stage, for something the parser
would have named at the moment of the write.

Only `.js`, `.cjs` and `.mjs`. `.jsx`, `.ts` and `.tsx` are not JavaScript and
Node will not parse them; running this on one would report a syntax error in a
file that is perfectly correct, which is the one outcome worth avoiding.

The check runs on a temporary sibling of the real file, so `package.json`'s
`type` resolves exactly as it will for the real one - `.js` is ESM or CommonJS
depending on that, and getting it wrong would invent errors.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

#: Extensions Node parses as JavaScript.
PARSEABLE = (".js", ".cjs", ".mjs")

#: A parse that takes longer than this is not a parse. Node reports a syntax
#: error in milliseconds; a hang means something else is wrong, and a write
#: must not wait on it.
TIMEOUT_SECONDS = 10

#: `/path/to/file.mjs:83` then the offending line, a caret line, and the
#: message. The parts worth repeating are the line number and the message.
_LINE = re.compile(r"^[^\n]*?:(\d+)$", re.M)
_MESSAGE = re.compile(r"^(SyntaxError:.*)$", re.M)


def _node() -> str | None:
    return shutil.which("node")


def parse_error(path: Path, content: str) -> str | None:
    """Node's syntax error for `content` at `path`, or None. Never raises.

    None also means "could not be checked" - no Node, a timeout, anything
    unexpected. A write must not fail because a check could not run, and this
    is the same rule every other hint in this codebase follows.
    """
    if path.suffix.lower() not in PARSEABLE:
        return None
    node = _node()
    if node is None:
        return None
    probe = path.with_name(f"{path.stem}.{uuid.uuid4().hex[:8]}.tmp{path.suffix}")
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text(content, encoding="utf-8")
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [node, "--check", str(probe)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not run `node --check` on %s", path, exc_info=True)
        return None
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - the file is in our own workspace
            logger.debug("Could not remove the parse probe %s", probe)
    if result.returncode == 0:
        return None

    report = f"{result.stderr}\n{result.stdout}"
    message = _MESSAGE.search(report)
    line = _LINE.search(report)
    where = f" on line {line.group(1)}" if line else ""
    detail = message.group(1) if message else "the file could not be parsed"
    return (
        f"Node cannot parse this file{where}: {detail}. "
        "This is `node --check`, the same parser that loads the file, so the "
        "error is certain - it is not a guess about style."
    )


__all__ = ["PARSEABLE", "parse_error"]
