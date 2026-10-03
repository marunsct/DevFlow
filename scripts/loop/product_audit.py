"""Audit what a run built: the product, its tests, and what the harness said about it.

Runs INSIDE the worker container, piped in on stdin:

    docker compose exec -T worker python - <run-id> [--no-tests] < scripts/loop/product_audit.py

or `scripts/loop/loop.sh product [run-id]`.

`audit_live.py` measures the run - failed calls, repeats, redundant reads. This
looks at the thing the run produced, which is the half a transcript audit
cannot see. It prints the evidence; the judgement stays with whoever reads it
(see docs/monitoring-handover.md, "Audit the generated product"):

  1. the product files, skipping dependencies, caches and test output
  2. code lines per file (non-blank, non-comment - how the brief's line caps are
     counted by the harness's own check)
  3. the acceptance criteria the run's intake recorded, to hold the code against
  4. what the harness itself claimed: each sprint summary's test counts, and the
     last milestone review's acceptance evidence
  5. the product's own test command, run once, so those claims can be compared
     with a real result (skipped with --no-tests)

Technology-agnostic by construction: it runs whichever test command the
project's manifest declares and counts lines in every source file it finds.
"""
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

SKIP = {"node_modules", ".git", ".agent-home", "test-results", "playwright-report",
        "__pycache__", ".venv", "venv", "dist", "build", "coverage", "target", ".pytest_cache"}
CODE_SUFFIXES = {".html", ".htm", ".css", ".scss", ".js", ".mjs", ".cjs", ".ts", ".tsx",
                 ".jsx", ".py", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs", ".vue", ".svelte"}
COMMENT = re.compile(r"^\s*(//|#|/\*|\*|\*/|<!--|-->)")

args = [a for a in sys.argv[1:] if not a.startswith("--")]
run_tests = "--no-tests" not in sys.argv
if not args:
    print("usage: product_audit.py <run-id> [--no-tests]")
    raise SystemExit(2)
run = args[0]

found = glob.glob(f"/app/data/workspaces/*/workspace-{run}")
if not found:
    print(f"no workspace for {run}")
    raise SystemExit(1)
root = Path(found[0])
pin = root / ".project-directory"
project = root / (pin.read_text().strip() if pin.exists() else "")
print(f"workspace: {root}\nproject:   {project.relative_to(root) if project != root else '(none pinned)'}\n")

print("== 1. product files")
files = []
for path in sorted(project.rglob("*")):
    if path.is_file() and not any(part in SKIP for part in path.relative_to(root).parts):
        if path.relative_to(root).parts[0] in ("docs",) or path.name.startswith(".project"):
            continue
        files.append(path)
        print(f"  {path.relative_to(root)}")

try:
    from app.stacks.contract import owned_by_the_harness
except Exception:  # noqa: BLE001 - outside the worker nothing is the harness's
    owned_by_the_harness = lambda root, relative: ""  # noqa: E731

print("\n== 2. code lines (non-blank, non-comment; the harness's own setup is not the product's)")
total = 0
for path in files:
    if path.suffix.lower() not in CODE_SUFFIXES or "test" in path.name.lower() or "spec" in path.name.lower():
        continue
    if owned_by_the_harness(root, path.relative_to(root).as_posix()):
        print(f"      -  {path.relative_to(root)}  (the harness's)")
        continue
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        continue
    code = sum(1 for line in lines if line.strip() and not COMMENT.match(line))
    total += code
    print(f"  {code:5d}  {path.relative_to(root)}  ({len(lines)} raw)")
print(f"  {total:5d}  total product code (tests excluded)")

print("\n== 3. acceptance criteria the intake recorded")
intake = root / "docs" / "product_intake.md"
if intake.exists():
    text = intake.read_text(encoding="utf-8", errors="replace")
    section = re.search(r"(?ims)^#+\s*(acceptance|success)[^\n]*\n(.*?)(?=^#+\s|\Z)", text)
    print((section.group(2) if section else text[:1200]).strip()[:1500])
else:
    print("  (no docs/product_intake.md)")

print("\n== 4. what the harness claimed")
for summary in sorted((root / "docs").glob("sprint_*_summary.md")):
    body = summary.read_text(encoding="utf-8", errors="replace")
    counts = " | ".join(re.findall(r"\*\*(?:Status|Test Cases|Passed|Failed):\*\*\s*[^\n]*", body))
    counts = counts or "; ".join(re.findall(r"(?m)^\s*-?\s*\*\*(?:Passed|Failed)[^\n]*", body))
    print(f"  {summary.name}: {counts or '(no counts)'}")
review = root / "docs" / "milestone_review.md"
if review.exists():
    body = review.read_text(encoding="utf-8", errors="replace")
    evidence = re.search(r"(?s)## Acceptance Evidence\s*(.*?)(?=\n## |\Z)", body)
    status = re.search(r"## Status:\s*(\S+)", body)
    print(f"  milestone_review status: {status.group(1) if status else '?'}")
    if evidence:
        print("  acceptance evidence: " + " ".join(evidence.group(1).split())[:900])

print("\n== 5. the product's own tests")
if not run_tests:
    print("  skipped (--no-tests)")
    raise SystemExit(0)
manifest = project / "package.json"
command = None
if manifest.exists():
    scripts = json.loads(manifest.read_text(encoding="utf-8")).get("scripts", {})
    if "test" in scripts:
        command = ["npm", "test"]
elif any((project / name).exists() for name in ("pyproject.toml", "pytest.ini", "setup.cfg")):
    command = ["python", "-m", "pytest", "-q"]
elif (project / "go.mod").exists():
    command = ["go", "test", "./..."]
elif (project / "Cargo.toml").exists():
    command = ["cargo", "test"]
if command is None:
    print("  no test command declared by a manifest")
    raise SystemExit(0)
print(f"  $ {' '.join(command)}  (in {project.relative_to(root)})")
try:
    done = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=240)
    out = (done.stdout or "") + (done.stderr or "")
    keep = [line for line in out.splitlines()
            if re.search(r"(?i)\b(pass|fail|passed|failed|tests?:|error|skipped)\b", line)]
    print("\n".join("  " + line for line in keep[-25:]))
    print(f"  exit code {done.returncode}")
except subprocess.TimeoutExpired:
    print("  timed out after 240s")
