"""A commit per accepted milestone, so there is always a known-good state.

Nothing in a run could answer "what did the last sprint actually change?" or
"what did this look like when it last worked?". Every stage re-read the whole
workspace to find out - 257 `read_file` calls over 22 distinct files on
one run - and a sprint that broke something had no state to fall back to.

The commit point is milestone *acceptance*, not sprint start. That is the only
moment the workflow has an opinion that the work is sound: the tests ran, the
reviewer read them and said yes. Committing at sprint start would preserve
whatever the previous sprint left behind, reviewed or not.

Everything here degrades rather than raises. A workspace that is not a git
repository, a git that is not installed, a commit that fails because nothing
changed - none of those are reasons to fail a run that has just passed its
review. The worst case is that the run continues exactly as it did before this
module existed.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

#: Identity on the commits. Not a person: nobody here typed the code, and a
#: real name on a machine-authored commit misleads whoever reads the log later.
AUTHOR_NAME = "Product Workflow"
AUTHOR_EMAIL = "workflow@localhost"

#: Written at init. The agent's package caches live inside the workspace
#: because container mode mounts nothing else (see `sandbox._child_environment`),
#: and one `npm install` leaves tens of thousands of files that are not the
#: product.
_IGNORED = """\
.agent-home/
.harness/
node_modules/
__pycache__/
*.pyc
.venv/
dist/
build/
.DS_Store
.project-directory
.project-stack
.project-memory.json
.work-order-files.json
docs/stage_summaries/
test-results/
playwright-report/
blob-report/
coverage/
.nyc_output/
htmlcov/
.turbo/
.parcel-cache/
.vite/
.cache/
"""
"""The last three are the harness's own bookkeeping, not the product's.

`.project-directory` pins which folder the project lives in, `.project-stack`
records the toolchain the run chose, and `.project-memory.json` holds which
stage last wrote each file. All three sit at the workspace root beside the
work and all three were being committed into the sprint history: `git
ls-files` on one run listed every one of them.

Nothing reads them through git - they are read from disk - so ignoring them
costs nothing and stops a delivered repository carrying three files that mean
nothing to whoever receives it. `HARNESS_FILES` in `tools/repository.py`
already hides the same three from every listing, digest and cross-file check;
this is the fourth place they should never appear.

The directories after them are a test runner's own output, and they are here
for the same reason. Measured on one run's first sprint:
`todo-app/test-results/.last-run.json` was committed alongside the product,
and a reviewer reading that diff has to work out that it is not part of the
work. The list is `sandbox._RUNNER_OUTPUT_DIRECTORIES`, which
`repository._iter_repo_files` already prunes from every listing and digest -
so, again, git was the one place nobody had looked. A test ties the two lists
together.
"""

_TIMEOUT_SECONDS = 30


def _git(root: Path, *args: str, index: Path | None = None) -> subprocess.CompletedProcess | None:
    """Run one git command in `root`, or return None if git cannot run at all.

    `index` is an index file of its own, so a snapshot never disturbs the
    index the sprint commits are made from.
    """
    binary = shutil.which("git")
    if binary is None:
        return None
    env = {"GIT_TERMINAL_PROMPT": "0", "HOME": str(root / ".agent-home"), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    if index is not None:
        env["GIT_INDEX_FILE"] = str(index)
    try:
        return subprocess.run(
            [binary, *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        logger.debug("git %s failed in %s", args, root, exc_info=True)
        return None


def is_repository(repo_root: str | Path) -> bool:
    """Whether `repo_root` is already a git repository."""
    return (Path(repo_root) / ".git").is_dir()


def initialise_repository(repo_root: str | Path) -> bool:
    """Make the workspace a git repository with one baseline commit.

    The baseline matters: without it the first milestone commit has nothing to
    diff against, and "what changed this sprint" is the whole point.

    Returns whether the workspace is a repository afterwards.
    """
    root = Path(repo_root)
    if not root.is_dir():
        return False
    if is_repository(root):
        return True

    if _git(root, "init", "--quiet") is None:
        logger.info("git is not available; this run will have no sprint history")
        return False

    (root / ".gitignore").write_text(_IGNORED, encoding="utf-8")
    _git(root, "config", "user.name", AUTHOR_NAME)
    _git(root, "config", "user.email", AUTHOR_EMAIL)
    # A run's history is its own; nothing here should be pushed anywhere.
    _git(root, "config", "commit.gpgsign", "false")

    _git(root, "add", "-A")
    _git(root, "commit", "--quiet", "--allow-empty", "-m",
         "Baseline: the workspace before the first sprint")
    return is_repository(root)


def commit_milestone(
    repo_root: str | Path, *, sprint: int, goal: str, summary: str = ""
) -> str | None:
    """Commit the workspace as it stands and tag it for this sprint.

    Called when a milestone review accepts. Returns the short commit hash, or
    None when there was nothing to commit or git could not run - both of which
    are ordinary and neither of which should disturb the run.
    """
    root = Path(repo_root)
    if not is_repository(root) and not initialise_repository(root):
        return None

    if _git(root, "add", "-A") is None:
        return None

    subject = f"Sprint {sprint}: {goal}".strip()
    # A commit subject is a line, not a paragraph. The goal can be a sentence.
    if len(subject) > 72:
        subject = subject[:69].rstrip() + "..."
    body = summary.strip()
    message = f"{subject}\n\n{body}" if body else subject

    result = _git(root, "commit", "--quiet", "-m", message)
    if result is None:
        return None

    # "nothing to commit" is ordinary: a sprint that changed no files still
    # passed its review, and the state at its end is still a real state.
    committed = result.returncode == 0
    if not committed:
        logger.debug("no new commit for sprint %s: %s", sprint, result.stdout.strip())

    # Tagged either way, so `sprint-N` always names the end of sprint N. Tagging
    # only on a new commit left a later `git diff sprint-1` pointing at a tag
    # that did not exist, which returns nothing and looks like "nothing
    # changed" rather than "the question could not be answered".
    _git(root, "tag", "-f", f"sprint-{sprint}")

    if not committed:
        return None
    revision = _git(root, "rev-parse", "--short", "HEAD")
    commit = revision.stdout.strip() if revision and revision.returncode == 0 else None
    if commit:
        logger.info("Committed sprint %s as %s", sprint, commit)
    return commit


def commit_all(repo_root: str | Path, message: str) -> str | None:
    """Commit everything in the workspace with `message`; the short hash, or None.

    None when there was nothing to commit or git could not run - neither is a
    reason to disturb the run.
    """
    root = Path(repo_root)
    if not is_repository(root) and not initialise_repository(root):
        return None
    if _git(root, "add", "-A") is None:
        return None
    subject, _, body = message.strip().partition("\n")
    if len(subject) > 72:
        subject = subject[:69].rstrip() + "..."
    result = _git(root, "commit", "--quiet", "-m", f"{subject}\n{body}".rstrip())
    if result is None or result.returncode != 0:
        return None
    revision = _git(root, "rev-parse", "--short", "HEAD")
    return revision.stdout.strip() if revision and revision.returncode == 0 else None


def last_good_commit(repo_root: str | Path) -> str | None:
    """The most recent accepted-milestone commit, if there is one."""
    result = _git(Path(repo_root), "rev-parse", "--short", "HEAD")
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() or None


def changed_since(repo_root: str | Path, reference: str) -> list[str]:
    """Paths that changed since `reference` - a sprint tag or a commit.

    What a later stage needs to know about an earlier one, without re-reading
    the workspace to work it out.

    Includes files that are new since `reference` and not yet tracked.
    `git diff --name-only` lists only tracked paths, so a file the sprint created
    and never committed was invisible - and a file the sprint created is the
    commonest thing a later stage needs to know about. Caught by a test of
    `_the_files_this_milestone_changed`, which used this to find what a stage had
    written and did not report: a new `index.html` was missing from the answer.
    """
    root = Path(repo_root)
    result = _git(root, "diff", "--name-only", reference)
    if result is None or result.returncode != 0:
        return []
    found = [line for line in result.stdout.splitlines() if line.strip()]
    new = _git(root, "ls-files", "--others", "--exclude-standard")
    if new is not None and new.returncode == 0:
        found.extend(line for line in new.stdout.splitlines() if line.strip())
    # Deduplicated in order, because a path can be both staged and reported new
    # by some git versions and a caller should not have to know that.
    seen: set[str] = set()
    ordered: list[str] = []
    for name in found:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def accepted_sprints(repo_root: str | Path) -> list[int]:
    """The sprint numbers this workspace has a `sprint-<n>` tag for, in order."""
    result = _git(Path(repo_root), "tag", "--list", "sprint-*")
    if result is None or result.returncode != 0:
        return []
    numbers = {int(name[len("sprint-"):]) for name in result.stdout.split() if name[len("sprint-"):].isdigit()}
    return sorted(numbers)


__all__ = [
    "AUTHOR_EMAIL",
    "accepted_sprints",
    "AUTHOR_NAME",
    "changed_since",
    "commit_milestone",
    "initialise_repository",
    "is_repository",
    "last_good_commit",
]


# --- stage snapshots, for rewinding a run --------------------------------------

#: Where a snapshot of the workspace is kept, one per stage started: outside
#: every branch and tag, so the sprint history is untouched.
SNAPSHOT_REFS = "refs/harness/stages/"

#: What a snapshot leaves out: installed packages, caches and build or test
#: output, which an install or a build makes again. The harness's own records
#: (`.harness/`, `.project-*`, stage summaries) are kept, though git ignores
#: them for commits: a rewound run must not keep the decisions or the locked
#: suite of the stages it went back before.
_NOT_SNAPSHOTTED = (
    "node_modules", ".venv", "venv", ".agent-home", "__pycache__", "dist", "build", "target",
    ".next", ".gradle", "test-results", "playwright-report", "blob-report", "coverage",
    ".nyc_output", "htmlcov", ".turbo", ".parcel-cache", ".vite", ".cache", ".pytest_cache",
)


def _pathspec() -> list[str]:
    return ["--", ".", *(f":(exclude,glob)**/{name}/**" for name in _NOT_SNAPSHOTTED)]


def _identity() -> list[str]:
    return ["-c", f"user.name={AUTHOR_NAME}", "-c", f"user.email={AUTHOR_EMAIL}"]


def snapshot_workspace(repo_root: str | Path, label: str) -> str | None:
    """Record the workspace as it is now under `SNAPSHOT_REFS`; the ref, or None.

    Taken as each stage starts (`workflow._snapshotting`), so a run can be
    rewound to that stage with its files as they were then. Never raises.
    """
    import re
    import time

    root = Path(repo_root)
    if not is_repository(root):
        return None
    index = root / ".git" / "harness-snapshot-index"
    added = _git(root, "add", "-A", "-f", *_pathspec(), index=index)
    tree = _git(root, "write-tree", index=index)
    if added is None or tree is None or tree.returncode != 0:
        return None
    head = _git(root, "rev-parse", "--verify", "-q", "HEAD")
    parent = ["-p", head.stdout.strip()] if head is not None and head.returncode == 0 and head.stdout.strip() else []
    commit = _git(root, *_identity(), "commit-tree", tree.stdout.strip(), *parent, "-m", f"Before {label}")
    if commit is None or commit.returncode != 0:
        return None
    name = re.sub(r"[^A-Za-z0-9_.-]", "-", label)[:80] or "stage"
    ref = f"{SNAPSHOT_REFS}{int(time.time() * 1000):013d}-{name}"
    updated = _git(root, "update-ref", ref, commit.stdout.strip())
    return ref if updated is not None and updated.returncode == 0 else None


def workspace_snapshots(repo_root: str | Path) -> list[tuple[int, str, str]]:
    """Every stage snapshot, oldest first: (milliseconds since the epoch, stage, commit)."""
    root = Path(repo_root)
    if not is_repository(root):
        return []
    listed = _git(root, "for-each-ref", "--format=%(refname) %(objectname)", SNAPSHOT_REFS)
    found = []
    for line in (listed.stdout.splitlines() if listed is not None and listed.returncode == 0 else []):
        ref, _, commit = line.partition(" ")
        stamp, _, stage = ref[len(SNAPSHOT_REFS):].partition("-")
        if stamp.isdigit():
            found.append((int(stamp), stage, commit))
    return sorted(found)


def restore_snapshot(repo_root: str | Path, commit: str) -> bool:
    """Put the workspace back as `commit` recorded it; whether that was done.

    The files it did not have are removed and the ones it had are written
    back; installed packages and caches are left alone. The branch and the
    sprint tags go back to where they were then, so the sprint history does
    not claim work the rewound run has not done again. What the workspace
    held before the rewind is itself snapshotted first.
    """
    root = Path(repo_root)
    if not is_repository(root):
        return False
    snapshot_workspace(root, "before-rewind")
    index = root / ".git" / "harness-snapshot-index"
    now = _git(root, "ls-files", "-z", index=index)
    then = _git(root, "ls-tree", "-r", "-z", "--name-only", commit)
    if now is None or then is None or then.returncode != 0:
        return False
    kept = {path for path in then.stdout.split("\0") if path}
    for path in (path for path in now.stdout.split("\0") if path and path not in kept):
        try:
            (root / path).unlink()
        except OSError:
            pass
    restore = root / ".git" / "harness-restore-index"
    if _git(root, "read-tree", commit, index=restore) is None:
        return False
    written = _git(root, "checkout-index", "-a", "-f", index=restore)
    restore.unlink(missing_ok=True)
    if written is None or written.returncode != 0:
        return False
    parent = _git(root, "rev-parse", "--verify", "-q", f"{commit}^")
    if parent is not None and parent.returncode == 0 and parent.stdout.strip():
        base = parent.stdout.strip()
        _git(root, "update-ref", "HEAD", base)
        _git(root, "read-tree", base)
        tags = _git(root, "tag", "-l", "sprint-*")
        for tag in (tags.stdout.split() if tags is not None else []):
            ancestor = _git(root, "merge-base", "--is-ancestor", tag, base)
            if ancestor is not None and ancestor.returncode != 0:
                _git(root, "tag", "-d", tag)
    return True
