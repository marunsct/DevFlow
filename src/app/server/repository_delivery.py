"""A changed existing product delivered back to the repository it was seeded from (plan WS.7, behind `PULL_REQUEST_DELIVERY`).

A run seeded from a repository ended with the change in the run's own
workspace: the owner downloaded a zip and carried the change back by hand, so
the change was never reviewed where the product lives. With the switch on, a
completed seeded run ends with its change delivered:

- seeded from a git repository with a delivery token the owner supplied for
  it (`WorkspaceSource.delivery_token`), the change is pushed as a branch named
  from the run and a pull request is opened against the branch it was cloned
  from, its description the handover page and the last sprint summary;
- otherwise - no token, an archive upload, a host whose API is not known, or a
  push that failed - the same change is written as a git bundle and a patch
  under `.harness/delivery/`, which the handover pack carries for download,
  and the outcome says why.

The change is one commit on top of the commit the run was seeded from, made
without touching the workspace's own index or files: the product as it ships
(`sprint.product_archive.files_of`, the harness's process documents left out),
with a product the run moved into its pinned directory put back where the
repository keeps it. A file the run deleted is deleted; a file left out of the
product archive (ignored, generated) is left as the base had it.

The token is never in the workspace, the run record, a log line or an error:
it is sealed with the stored credentials' key (`runtime_settings.seal`) in the
data directory, reaches git through `GIT_ASKPASS` and the host API through one
header, and is removed once a pull request is open. The host's API is called
in one place (`open_pull_request`), so another host is one more entry in
`HOSTS`.
"""
from __future__ import annotations

import json
import logging
import os
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `PULL_REQUEST_DELIVERY` set to on or off overrides this; off until measured.
ON_BY_DEFAULT = False
#: What the admin page says this switch does.
explanation = ("A completed run seeded from a repository delivers its change back there: pushed as a branch named "
               "from the run, with a pull request opened against the branch it was cloned from, when the owner gave "
               "a delivery token for that repository; otherwise as a git bundle and a patch in the handover pack. "
               "Off until measured.")
#: What a delivery says it did; the switch's firing signal (`switch_firing.SIGNALS`).
SAYS = "Delivered to the seeded repository"
#: What seeding a run records for its delivery: the source, the base commit and branch, never the token.
RECORD = ".harness/delivery.json"
#: What the delivery did.
OUTCOME = ".harness/delivery-outcome.json"
#: Where a bundle and a patch are written for download (the handover pack carries them).
DOWNLOADS = ".harness/delivery"
#: Branches the harness pushes start with this.
BRANCH_PREFIX = "harness/"
#: The longest a pull request's description may be: GitHub refuses past 65,536 characters.
MOST_BODY_CHARACTERS = 60_000
#: Top-level folders the harness's stages write their own records in, never the product's change.
_ITS_OWN_FOLDERS = frozenset({"large_tool_results", ".agent-home", ".harness"})
PUSH_TIMEOUT_SECONDS = 300
API_TIMEOUT_SECONDS = 30


class DeliveryError(RuntimeError):
    """A push or a host call failed; the message never carries the token."""


def enabled() -> bool:
    return is_on("PULL_REQUEST_DELIVERY", ON_BY_DEFAULT)


# --------------------------------------------------------------------------- names


def branch_name(name: str, run_id: str = "") -> str:
    """A branch name from the run's name, in characters every host takes, with the run's id to keep it unique."""
    slug = re.sub(r"[^a-z0-9._-]+", "-", str(name or "").lower())
    slug = re.sub(r"\.{2,}", ".", re.sub(r"-{2,}", "-", slug)).strip("-._")[:48].rstrip("-._")
    suffix = re.sub(r"[^a-z0-9]+", "", str(run_id or "").lower())[-8:]
    slug = "-".join(part for part in (slug or "change", suffix) if part)
    if slug.endswith(".lock"):
        slug = slug[: -len(".lock")] + "-lock"
    return BRANCH_PREFIX + slug


# --------------------------------------------------------------------------- the credential


def _credentials_directory() -> Path:
    return Path(os.environ.get("DATA_DIR", ".")) / "delivery-credentials"


def _credential_file(run_id: str) -> Path:
    safe = "".join(c for c in str(run_id) if c.isalnum() or c in "-_") or "run"
    return _credentials_directory() / f"{safe}.token"


def _keep_the_token(run_id: str, token: str) -> None:
    from app.server.runtime_settings import seal

    path = _credential_file(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(seal(token))


def _the_token(run_id: str) -> str:
    try:
        from app.server.runtime_settings import unseal

        return unseal(_credential_file(run_id).read_text(encoding="utf-8").strip())
    except FileNotFoundError:
        return ""
    except Exception:  # noqa: BLE001 - an unreadable token is no token; the bundle says so
        logger.warning("The delivery token of run %s could not be read; the change is delivered as a bundle", run_id)
        return ""


def _forget_the_token(run_id: str) -> None:
    try:
        _credential_file(run_id).unlink()
    except OSError:
        pass


# --------------------------------------------------------------------------- git


def _git(root: Path, *args: str, stdin: str | None = None, env: dict[str, str] | None = None,
         timeout: int = 60) -> subprocess.CompletedProcess:
    from app.tools.version_control import AUTHOR_EMAIL, AUTHOR_NAME, git_safely

    base = {"GIT_TERMINAL_PROMPT": "0", "HOME": str(root / ".agent-home"), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "GIT_AUTHOR_NAME": AUTHOR_NAME, "GIT_AUTHOR_EMAIL": AUTHOR_EMAIL,
            "GIT_COMMITTER_NAME": AUTHOR_NAME, "GIT_COMMITTER_EMAIL": AUTHOR_EMAIL}
    return subprocess.run(  # noqa: S603 - argv list, no shell
        [*git_safely(), *args], cwd=str(root), input=stdin, capture_output=True, text=True, errors="replace",
        timeout=timeout, check=False, env={**base, **(env or {})})


def _value(root: Path, *args: str) -> str:
    try:
        result = _git(root, *args)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def remember(run_id: str, workspace: str | Path, source: object | None) -> None:
    """At the start of a seeded run, record what its change is delivered against. Never raises; nothing when off."""
    try:
        from app.acceptance.regression_contract import seeded

        root = Path(workspace)
        if not enabled() or not seeded(root):
            return
        kind = str(getattr(source, "type", "") or "")
        record: dict[str, Any] = {"kind": kind, "base_commit": _value(root, "rev-parse", "HEAD")}
        if kind == "git":
            from app.server.seeding import validate_git_url

            record["url"] = validate_git_url(str(getattr(source, "url", "") or ""))
            record["base_ref"] = str(getattr(source, "ref", "") or "") or _value(root, "rev-parse", "--abbrev-ref", "HEAD")
            token = str(getattr(source, "delivery_token", "") or "").strip()
            if token:
                _keep_the_token(run_id, token)
        (root / RECORD).parent.mkdir(parents=True, exist_ok=True)
        (root / RECORD).write_text(json.dumps(record), encoding="utf-8")
    except Exception:  # noqa: BLE001 - a run is never refused for its delivery
        logger.warning("Could not record what run %s delivers against", run_id, exc_info=False)


def _delivered_files(root: Path) -> dict[str, Path]:
    """{path in the repository's layout: the workspace file} for the product as it ships."""
    from app.sprint.product_archive import _first_line, files_of, is_a_process_document
    from app.stacks.seeded_product import MOVE_RECORD
    from app.tools.repository import is_harness_bookkeeping

    try:
        moved = json.loads((root / MOVE_RECORD).read_text(encoding="utf-8"))
        project = str(moved.get("project") or "")
    except (OSError, ValueError, AttributeError):
        project = ""
    delivered: dict[str, Path] = {}
    for relative in files_of(root):
        path = root / relative
        # The harness's own records beside the product (`.project-directory`, a large tool answer): never the change.
        if is_harness_bookkeeping(path) or Path(relative).parts[0] in _ITS_OWN_FOLDERS:
            continue
        if relative.endswith(".md") and relative.startswith("docs/"):
            try:
                with path.open("rb") as handle:
                    if is_a_process_document(relative, _first_line(handle.read(2000))):
                        continue
            except OSError:
                continue
        target = relative[len(project) + 1:] if project and relative.startswith(project + "/") else relative
        delivered.setdefault(target, path)
    return delivered


def _source_of(root: Path, repository_path: str) -> Path:
    """Where the workspace keeps a file of the base, after any move into the pinned directory."""
    from app.stacks.seeded_product import MOVE_RECORD

    try:
        moved = json.loads((root / MOVE_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return root / repository_path
    if Path(repository_path).parts[0] in (moved.get("moved") or []):
        return root / str(moved.get("project") or "") / repository_path
    return root / repository_path


def delivered_commit(root: str | Path, base: str, message: str) -> str:
    """One commit on `base` holding the product as it ships, made in a separate index; its id. Raises DeliveryError."""
    root = Path(root)
    delivered = _delivered_files(root)
    with tempfile.TemporaryDirectory(prefix="delivery-") as scratch:
        index = {"GIT_INDEX_FILE": str(Path(scratch) / "index")}
        if _git(root, "read-tree", base, env=index).returncode != 0:
            raise DeliveryError("The commit the run was seeded from is not in the workspace's history.")
        listed = _git(root, "ls-tree", "-r", "-z", "--name-only", base)
        removed = [name for name in listed.stdout.split("\0")
                   if name and name not in delivered and not os.path.lexists(_source_of(root, name))]
        names = sorted(delivered)
        hashed = _git(root, "hash-object", "-w", "--stdin-paths", stdin="\n".join(str(delivered[n]) for n in names) + "\n")
        shas = hashed.stdout.split()
        if hashed.returncode != 0 or len(shas) != len(names):
            raise DeliveryError("The product's files could not be written to the workspace's history.")
        lines = [f"0 {'0' * 40}\t{name}" for name in removed]
        for name, sha in zip(names, shas):
            mode = "100755" if os.access(delivered[name], os.X_OK) else "100644"
            lines.append(f"{mode} {sha}\t{name}")
        if _git(root, "update-index", "-z", "--index-info", stdin="\0".join(lines) + "\0", env=index).returncode != 0:
            raise DeliveryError("The delivered tree could not be assembled.")
        tree = _git(root, "write-tree", env=index).stdout.strip()
    made = _git(root, "commit-tree", tree, "-p", base, stdin=message)
    if made.returncode != 0 or not made.stdout.strip():
        raise DeliveryError("The delivered commit could not be made.")
    return made.stdout.strip()


def push(root: str | Path, url: str, commit: str, branch: str, token: str) -> None:
    """Push `commit` as `branch` to `url`, the token through `GIT_ASKPASS`. Raises DeliveryError without the token."""
    from app.server.seeding import _allowed_schemes, _clone_environment, _write_askpass, validate_git_url
    from app.tools.version_control import git_safely

    safe_url = validate_git_url(url)
    file_policy = "always" if "file" in _allowed_schemes() else "never"
    with tempfile.TemporaryDirectory(prefix="delivery-") as scratch:
        environment = _clone_environment(token, _write_askpass(Path(scratch)))
        try:
            result = subprocess.run(  # noqa: S603 - argv list, no shell
                [*git_safely(), "-c", "protocol.ext.allow=never", "-c", f"protocol.file.allow={file_policy}",
                 "push", "--porcelain", "--", safe_url, f"{commit}:refs/heads/{branch}"],
                cwd=str(root), capture_output=True, text=True, errors="replace", timeout=PUSH_TIMEOUT_SECONDS,
                env=environment, check=False)
        except subprocess.TimeoutExpired:
            raise DeliveryError(f"The push timed out after {PUSH_TIMEOUT_SECONDS} seconds.") from None
        except OSError as error:
            raise DeliveryError(f"git could not run: {error}") from None
    if result.returncode != 0:
        said = " ".join(line for line in (result.stderr or "").splitlines() if line.strip())[-300:]
        raise DeliveryError("The push was refused: " + (said.replace(token, "***") if token else said))


# --------------------------------------------------------------------------- the host


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """POST `payload` as JSON; (status, the JSON answer). The one network call to a host's API."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as answer:  # noqa: S310 - https only
            return answer.status, json.loads(answer.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8") or "{}")
        except ValueError:
            body = {}
        return error.code, body


def _github(owner_and_name: str, token: str, head: str, base: str, title: str, body: str) -> str:
    status, answer = _post_json(
        f"https://api.github.com/repos/{owner_and_name}/pulls",
        {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "product-workflow-harness"},
        {"title": title, "head": head, "base": base, "body": body, "maintainer_can_modify": True},
    )
    if status not in (200, 201) or not answer.get("html_url"):
        said = str(answer.get("message") or "")[:200]
        raise DeliveryError(f"GitHub did not open the pull request (HTTP {status}){': ' + said if said else ''}.")
    return str(answer["html_url"])


#: Host name -> the function that opens a pull request on it: (owner/name, token, head, base, title, body) -> its URL.
HOSTS: dict[str, Callable[[str, str, str, str, str, str], str]] = {"github.com": _github}


def open_pull_request(url: str, token: str, head: str, base: str, title: str, body: str) -> str | None:
    """Open a pull request from `head` into `base` on the repository at `url`; its URL, or None for a host not in `HOSTS`."""
    parsed = urlparse(url)
    opener = HOSTS.get((parsed.hostname or "").lower())
    if opener is None:
        return None
    owner_and_name = parsed.path.strip("/").removesuffix(".git")
    if owner_and_name.count("/") != 1:
        raise DeliveryError("The repository URL does not name an owner and a repository.")
    return opener(owner_and_name, token, head, base, title, body)


# --------------------------------------------------------------------------- the delivery


def description(root: str | Path, run_id: str) -> str:
    """The pull request's description: the handover page, then the last sprint summary, within the host's limit."""
    root = Path(root)
    parts: list[str] = []
    try:
        from app.handover.handover_document import write_for

        parts.append(write_for(root, run_id=run_id).strip())
    except Exception:  # noqa: BLE001 - a description without the page
        logger.debug("No handover page for the description", exc_info=True)
    summaries = sorted((root / "docs").glob("sprint_*_summary.md"),
                       key=lambda path: int(re.sub(r"\D", "", path.stem) or 0))
    if summaries:
        try:
            parts.append(summaries[-1].read_text(encoding="utf-8", errors="replace").strip())
        except OSError:
            pass
    text = "\n\n---\n\n".join(part for part in parts if part) or "The change this run made."
    return text if len(text) <= MOST_BODY_CHARACTERS else text[:MOST_BODY_CHARACTERS - 40].rstrip() + "\n\n[cut at the host's limit]"


@dataclass(frozen=True)
class Outcome:
    #: "pull_request", "branch" (pushed; no pull request API for the host) or "bundle".
    kind: str
    branch: str
    message: str
    url: str = ""
    files: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "branch": self.branch, "message": self.message, "url": self.url,
                "files": list(self.files)}


def _for_download(root: Path, commit: str, base: str, branch: str, why: str) -> Outcome:
    folder = root / DOWNLOADS
    folder.mkdir(parents=True, exist_ok=True)
    stem = branch.removeprefix(BRANCH_PREFIX)
    _git(root, "update-ref", f"refs/heads/{branch}", commit)
    bundle, patch = folder / f"{stem}.bundle", folder / f"{stem}.patch"
    _git(root, "bundle", "create", str(bundle), f"{base}..{branch}", timeout=PUSH_TIMEOUT_SECONDS)
    patched = _git(root, "format-patch", "-1", "--binary", "--stdout", commit, timeout=PUSH_TIMEOUT_SECONDS)
    if patched.returncode == 0:
        patch.write_text(patched.stdout, encoding="utf-8")
    files = tuple(path.relative_to(root).as_posix() for path in (bundle, patch) if path.is_file())
    return Outcome("bundle", branch, f"{SAYS} as a git bundle and a patch for download in the handover pack "
                                     f"(branch {branch}, on the commit it was seeded from): {why}", files=files)


def deliver(run_id: str, repo_root: str | Path, *, name: str = "") -> Outcome | None:
    """Deliver a completed seeded run's change: a pull request, else a bundle and a patch; None when off or not seeded.

    Never raises: the run is complete whatever the delivery does, and the outcome says what happened.
    """
    root = Path(repo_root)
    if not enabled():
        return None
    try:
        record = json.loads((root / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        outcome = _deliver(run_id, root, record, name)
    except Exception as error:  # noqa: BLE001 - see the docstring
        logger.warning("Run %s could not deliver its change: %s", run_id, type(error).__name__)
        outcome = Outcome("none", "", f"The change could not be delivered: {type(error).__name__}.")
    try:
        (root / OUTCOME).write_text(json.dumps(outcome.as_dict()), encoding="utf-8")
        from app.observability.transcript import record as transcript

        transcript(run_id, "complete", "repository_delivery", message=outcome.message, delivered_as=outcome.kind,
                   branch=outcome.branch, url=outcome.url, files=list(outcome.files))
    except Exception:  # noqa: BLE001 - the outcome is evidence
        logger.debug("Could not record the delivery", exc_info=True)
    return outcome


def _deliver(run_id: str, root: Path, record: dict[str, Any], name: str) -> Outcome:
    base = str(record.get("base_commit") or "")
    if not base:
        raise DeliveryError("The run recorded no commit it was seeded from.")
    branch = branch_name(name, run_id)
    title = " ".join(str(name or "").split())[:200] or f"The change made by run {run_id}"
    commit = delivered_commit(root, base, f"{title}\n\nDelivered by the product workflow harness, run {run_id}.\n")
    url, token = str(record.get("url") or ""), _the_token(run_id)
    if not url:
        return _for_download(root, commit, base, branch, "the run was not seeded from a repository URL.")
    if not token:
        return _for_download(root, commit, base, branch, "no delivery token was given for the repository.")
    try:
        push(root, url, commit, branch, token)
    except Exception as error:  # noqa: BLE001 - the change is still delivered, for download
        return _for_download(root, commit, base, branch, str(error) if isinstance(error, DeliveryError)
                             else "the push could not run.")
    base_ref = str(record.get("base_ref") or "")
    try:
        opened = open_pull_request(url, token, branch, base_ref, title, description(root, run_id)) if base_ref else None
    except DeliveryError as error:
        return Outcome("branch", branch, f"{SAYS} as branch {branch}; the pull request was not opened: {error}")
    if opened is None:
        return Outcome("branch", branch, f"{SAYS} as branch {branch}; this host has no pull request API the harness "
                                         "knows, so open one from the branch.")
    _forget_the_token(run_id)
    return Outcome("pull_request", branch, f"{SAYS} as pull request {opened}, from branch {branch} into {base_ref}.",
                   url=opened)


__all__ = ["BRANCH_PREFIX", "DOWNLOADS", "DeliveryError", "HOSTS", "ON_BY_DEFAULT", "OUTCOME", "Outcome", "RECORD",
           "SAYS", "branch_name", "delivered_commit", "deliver", "description", "enabled", "explanation",
           "open_pull_request", "push", "remember"]
