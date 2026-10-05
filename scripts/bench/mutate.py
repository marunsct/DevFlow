"""How strong is a run's own locked acceptance suite? Break the product and see.

Runs inside the worker (it has the toolchains and the harness importable):

    python mutate.py <workspace> <result.json> [mutants]

A locked suite that passes says the product does what the tests check; it does
not say the tests check much. One run's suite passed 8 of 9 while the product
scored 2 of 10 on the hidden tests. This copies the workspace, makes one small
change to the product's source at a time - a comparison turned round, a
condition flipped, a constant changed - and runs the suite exactly the way the
harness does (`app.acceptance.suite.run`). A change the suite does not notice
is a behaviour no test holds the product to.

Every change is textual and works on any language whose source uses these
operators; a site inside a comment or a string literal is left alone. A change
can also be equivalent (behaves the same) - those survive by right, so the
score is a floor on suite strength, never a ceiling. A change that makes every
test fail usually broke the program outright; it counts as caught, and is
marked so the reader can discount it.

The result: the baseline (tests that pass unmutated), each change with the
tests it turned red, and the score (changes caught / changes tried).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path

#: (pattern, replacement) pairs. Order matters only for reporting.
OPERATORS: list[tuple[str, str]] = [
    (r"===", "!=="),
    (r"!==", "==="),
    (r"(?<![=!<>])==(?!=)", "!="),
    (r"(?<![=!])!=(?!=)", "=="),
    (r"&&", "||"),
    (r"\|\|", "&&"),
    (r"\band\b", "or"),
    (r"\bor\b", "and"),
    (r"\btrue\b", "false"),
    (r"\bfalse\b", "true"),
    (r"\bTrue\b", "False"),
    (r"\bFalse\b", "True"),
    (r">=", "<"),
    (r"<=", ">"),
    (r"(?<![-=>])>(?![=>])", "<="),
    (r"(?<![<=-])<(?![=<])", ">="),
    (r"\+ 1\b", "- 1"),
    (r"- 1\b", "+ 1"),
]

#: Source a product's behaviour lives in.
SOURCE_SUFFIXES = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".py", ".rb", ".go", ".java", ".php"}

#: Directories that are not the product's own source.
SKIPPED_PARTS = {"node_modules", "dist", "build", "coverage", "__pycache__", ".venv", "venv", ".harness",
                 "tests", "test", "__tests__", "e2e", "acceptance", "docs", "public", "vendor"}

#: File names that are tests or configuration, not behaviour.
SKIPPED_NAME = re.compile(r"(\.test\.|\.spec\.|^test_|_test\.|\.config\.|^conftest\.py$|^setup\.py$)")


def source_files(project: Path, kept: set[str] | frozenset[str] = frozenset()) -> list[Path]:
    """The product's own source: not tests, not configuration, not the harness's kept files.

    `kept` are the pack's runner files (relative to the project), which the
    harness puts back before every suite run - a change there is undone
    before any test sees it.
    """
    files = []
    for path in sorted(project.rglob("*")):
        relative = path.relative_to(project)
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        if relative.as_posix() in kept:
            continue
        if any(part in SKIPPED_PARTS or part.startswith(".") for part in relative.parts[:-1]):
            continue
        if SKIPPED_NAME.search(path.name):
            continue
        files.append(path)
    return files


def _in_comment_or_string(line: str, column: int) -> bool:
    before = line[:column]
    stripped = before.lstrip()
    if stripped.startswith(("//", "#", "*", "/*")) or "//" in before or " #" in before:
        return True
    return any(before.count(quote) % 2 for quote in ("'", '"', "`"))


def sites(files: list[Path], project: Path) -> list[dict]:
    """Every place an operator applies: file, line, column, the text it replaces and its replacement."""
    found = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, start=1):
            if line.lstrip().startswith(("import ", "from ", "export {", "require(")):
                continue
            for pattern, replacement in OPERATORS:
                for match in re.finditer(pattern, line):
                    if _in_comment_or_string(line, match.start()):
                        continue
                    found.append({
                        "file": str(path.relative_to(project)), "line": number, "column": match.start(),
                        "original": match.group(0), "replacement": replacement,
                    })
    return found


def spread(candidates: list[dict], count: int) -> list[dict]:
    """`count` sites spread evenly over the list, so every file gets its share."""
    if len(candidates) <= count:
        return candidates
    step = len(candidates) / count
    return [candidates[int(i * step)] for i in range(count)]


def apply(project: Path, site: dict) -> str:
    """Make the change in place; return the file's original text."""
    path = project / site["file"]
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    line = lines[site["line"] - 1]
    column, length = site["column"], len(site["original"])
    lines[site["line"] - 1] = line[:column] + site["replacement"] + line[column + length:]
    path.write_text("".join(lines), encoding="utf-8")
    return original


def _passing(result) -> set[str]:
    report = getattr(result, "report", None)
    tests = getattr(report, "tests", None) or []
    return {getattr(t, "name", str(t)) for t in tests if getattr(t, "outcome", "") == "passed"}


def mutate(workspace: Path, out: Path, count: int = 12) -> dict:
    from app.acceptance import suite
    from app.stacks import contract

    copy = Path(f"/tmp/mutate-work/{workspace.name}-{int(time.time())}")
    shutil.copytree(workspace, copy, symlinks=True)
    found = contract.the_pack(copy)
    project_name = str(found[1].get("project")) if found else (suite.location(copy) or ("",))[0]
    project = copy / project_name if project_name else copy

    baseline = suite.run(copy, save=False)
    held = _passing(baseline)
    result: dict = {"workspace": str(workspace), "baseline_passing": sorted(held), "mutants": []}
    if not held:
        result["problem"] = "no test passes on the unchanged product, so no change can be caught"
        out.write_text(json.dumps(result, indent=2))
        return result

    kept = set(found[0].kept_files) if found else set()
    for site in spread(sites(source_files(project, kept), project), count):
        original = apply(project, site)
        try:
            after = suite.run(copy, save=False)
        finally:
            (project / site["file"]).write_text(original, encoding="utf-8")
        turned_red = sorted(held - _passing(after))
        result["mutants"].append({
            **site,
            "caught": bool(turned_red),
            "everything_failed": bool(turned_red) and len(turned_red) == len(held),
            "turned_red": turned_red,
        })
    tried = len(result["mutants"])
    caught = sum(m["caught"] for m in result["mutants"])
    specific = sum(m["caught"] and not m["everything_failed"] for m in result["mutants"])
    result.update({
        "tried": tried,
        "caught": caught,
        "score": round(caught / tried, 3) if tried else None,
        "caught_by_a_specific_test": specific,
    })
    out.write_text(json.dumps(result, indent=2))
    shutil.rmtree(copy, ignore_errors=True)
    return result


if __name__ == "__main__":
    workspace, out = Path(sys.argv[1]), Path(sys.argv[2])
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    result = mutate(workspace, out, count)
    if "problem" in result:
        print(result["problem"])
        raise SystemExit(1)
    print(
        f"locked suite caught {result['caught']} of {result['tried']} changes "
        f"(score {result['score']}); {result['caught_by_a_specific_test']} by a specific test "
        "rather than by everything failing"
    )
    for m in result["mutants"]:
        if not m["caught"]:
            print(f"  SURVIVED {m['file']}:{m['line']}  {m['original']} -> {m['replacement']}")
