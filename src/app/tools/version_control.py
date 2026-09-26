"""A commit per accepted milestone, so there is always a known-good state.

Nothing in a run could answer "what did the last sprint actually change?" or
"what did this look like when it last worked?". Every stage re-read the whole
workspace to find out - 257 `read_file` calls over 22 distinct files on
run-61c5a5b6 - and a sprint that broke something had no state to fall back to.

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
ls-files` on run-07cd52ae listed every one of them.

Nothing reads them through git - they are read from disk - so ignoring them
costs nothing and stops a delivered repository carrying three files that mean
nothing to whoever receives it. `HARNESS_FILES` in `tools/repository.py`
already hides the same three from every listing, digest and cross-file check;
this is the fourth place they should never appear.

The directories after them are a test runner's own output, and they are here
for the same reason. Measured on run-fbe23618's first sprint:
`todo-app/test-results/.last-run.json` was committed alongside the product,
and a reviewer reading that diff has to work out that it is not part of the
work. The list is `sandbox._RUNNER_OUTPUT_DIRECTORIES`, which
`repository._iter_repo_files` already prunes from every listing and digest -
so, again, git was the one place nobody had looked. A test ties the two lists
together.
"""

_TIMEOUT_SECONDS = 30


def _git(root: Path, *args: str) -> subprocess.CompletedProcess | None:
    """Run one git command in `root`, or return None if git cannot run at all."""
    binary = shutil.which("git")
    if binary is None:
        return None
    try:
        return subprocess.run(
            [binary, *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
            env={"GIT_TERMINAL_PROMPT": "0", "HOME": str(root / ".agent-home"), "PATH": "/usr/bin:/bin:/usr/local/bin"},
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
    """
    result = _git(Path(repo_root), "diff", "--name-only", reference)
    if result is None or result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


__all__ = [
    "AUTHOR_EMAIL",
    "AUTHOR_NAME",
    "changed_since",
    "commit_milestone",
    "initialise_repository",
    "is_repository",
    "last_good_commit",
]
