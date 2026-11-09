"""A test that asks for a literal id and creates nothing first cannot pass on an empty product (plan item 20, behind `IDS_READ_WITHOUT_A_CREATE`).

The same fault as `suite.tests_that_sign_in_as_nobody`, in its other form: every test starts from an empty product, so
`GET /notes/1` with nothing created answers 404 on every right product, and the round charges that to the product. By
its shape, and only when nothing in the test could have made the record: no write and no helper that creates, no hook
or fixture in the file, and no expected refusal, since asking for what is absent is how a 404 is proved.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `IDS_READ_WITHOUT_A_CREATE` set to on or off overrides this.
ON_BY_DEFAULT = False
MOST_FINDINGS = 6
_JAVASCRIPT_OR_PYTHON = (".py", ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts")
#: A read, change or removal of a path ending in a literal number: `request.get('/notes/1')`, `fetch(`${base}/notes/1`)`.
_A_LITERAL_ID = re.compile(
    r"""\b(?:get|put|patch|delete|fetch)\s*\(\s*(?:f?['"`])(?:[^'"`\n]*?)(/[A-Za-z][\w-]*/\d+)(?:['"`/?])""", re.I)
_MAKES_SOMETHING = re.compile(
    r"\.post\s*\(|['\"]POST['\"]|method:\s*['\"`]POST|create|seed|insert|add[A-Z_]|make[A-Z_]|sign_?up|register", re.I)
_SETS_UP = re.compile(r"\bbeforeEach\b|\bbeforeAll\b|\.extend\s*\(|@pytest\.fixture|\bdef setup|\bconftest\b")
_EXPECTS_A_REFUSAL = re.compile(r"\b40[0134]\b|\b422\b|toBeGreaterThanOrEqual\(\s*400|>=\s*400|not\.toBeOK|\.ok\(\)\)\.toBe\(false")


def enabled() -> bool:
    return is_on("IDS_READ_WITHOUT_A_CREATE", ON_BY_DEFAULT)


def findings(repo_root: str | Path) -> list[str]:
    """One line per test asking for an id it never created; [] when off. Never raises."""
    if not enabled():
        return []
    try:
        return _found(repo_root)
    except Exception:  # noqa: BLE001 - the other checks stand without this one
        logger.debug("The check of ids read without a create failed", exc_info=True)
        return []


def _found(repo_root: str | Path) -> list[str]:
    from app.acceptance import suite

    root = Path(repo_root)
    problems: list[str] = []
    for path in suite.suite_files(repo_root):
        if path.suffix.lower() not in _JAVASCRIPT_OR_PYTHON:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _SETS_UP.search(text):
            continue
        tests = suite._A_PYTHON_TEST if path.suffix.lower() == ".py" else suite._A_TEST_CALL  # noqa: SLF001
        starts = [m.start() for m in tests.finditer(text)]
        for at, start in enumerate(starts):
            block = text[start:starts[at + 1] if at + 1 < len(starts) else len(text)]
            if _MAKES_SOMETHING.search(block) or _EXPECTS_A_REFUSAL.search(block):
                continue
            match = _A_LITERAL_ID.search(block)
            if match is None:
                continue
            line = text.count("\n", 0, start + match.start()) + 1
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line {line}: the test asks for `{match.group(1)}`, an id the "
                "test never created. Every test starts from an empty product, so that record does not exist on any "
                "right product. Create the record through the product first and use the id its answer gives."
            )
    return problems[:MOST_FINDINGS]


__all__ = ["ON_BY_DEFAULT", "findings"]
