"""Two specialists cannot run commands in one workspace at the same time.

Parallel execution mode fans a milestone's specialists out to run together, and
they share one workspace. Every tool in `app.tools` was written under the
assumption that one stage runs at a time, because until that mode existed it was
true.

Measured on run-5696a52d, the first parallel run, from its own transcript:

    04:54:23 specialist_ui_ux_0     | install | npm install | wd=simple-to-do-list-app
    04:54:23 specialist_ui_ux_1     | install | npm install | wd=simple-to-do-list-app
    04:54:23 specialist_backend_2   | install | npm install | wd=simple-to-do-list-app

    npm error code ENOTEMPTY
    npm error syscall rmdir
    npm error path simple-to-do-list-app/node_modules/playwright-core/lib/vit...

and then, a minute later, two `npm test` in the same directory at 04:55:29,
where a Playwright `webServer` binds one port and the runner writes one
`test-results/`.

Nothing is wrong with any of those commands. The fault is two of them at once in
one directory, so no allowlist and no category can address it.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from app.tools import sandbox


class TestOneCommandAtATime:
    def test_two_commands_in_one_workspace_do_not_overlap(self, tmp_path, monkeypatch):
        """The property that stops npm tearing at its own tree.

        Asserted on overlap rather than on order: which specialist goes first is
        not something this should decide, and a test that pinned it would fail
        for the wrong reason.
        """
        overlaps: list[str] = []
        running: list[str] = []
        guard = threading.Lock()

        def fake_run(command, repo_root, role_name="general", category="default",
                     extra_env=None, working_directory=None):
            name = " ".join(map(str, command))
            with guard:
                if running:
                    overlaps.append(f"{name} overlapped {running[0]}")
                running.append(name)
            time.sleep(0.05)
            with guard:
                running.remove(name)
            return {"stdout": "", "stderr": "", "returncode": "0"}

        monkeypatch.setattr(sandbox.SandboxExecutor, "_run", staticmethod(fake_run))

        def issue(index: int) -> None:
            sandbox.SandboxExecutor.execute(
                ["npm", "install"], str(tmp_path), role_name=f"role_{index}",
                category="install",
            )

        threads = [threading.Thread(target=issue, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not overlaps, overlaps

    def test_separate_workspaces_are_not_serialised_against_each_other(
        self, tmp_path, monkeypatch
    ):
        """The lock is per workspace, not global.

        Two runs execute in two workspaces and have no shared state to corrupt.
        A global lock would make every run wait on every other run's test suite.
        """
        first = tmp_path / "one"
        second = tmp_path / "two"
        first.mkdir()
        second.mkdir()

        started = threading.Event()
        both_inside = threading.Event()

        def fake_run(command, repo_root, role_name="general", category="default",
                     extra_env=None, working_directory=None):
            if str(repo_root) == str(first):
                started.set()
                # Only passes if the other workspace can enter while this one holds.
                both_inside.wait(timeout=2)
            else:
                started.wait(timeout=2)
                both_inside.set()
            return {"stdout": "", "stderr": "", "returncode": "0"}

        monkeypatch.setattr(sandbox.SandboxExecutor, "_run", staticmethod(fake_run))

        threads = [
            threading.Thread(target=lambda root=root: sandbox.SandboxExecutor.execute(
                ["npm", "install"], str(root), category="install"))
            for root in (first, second)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert both_inside.is_set(), "one workspace's command blocked another workspace's"

    def test_a_refusal_releases_the_lock(self, tmp_path, monkeypatch):
        """`execute` returns early in several places, and each must release it.

        A refusal that returned while holding the lock would deadlock every other
        worker in the fan-out - a worse failure than the corruption this fixes,
        and a silent one. The body is a separate method for this reason: the lock
        is taken in one place and released by leaving the `with`.
        """
        monkeypatch.setattr(sandbox, "execution_enabled", lambda: True)
        monkeypatch.setattr(sandbox.SandboxExecutor, "_run", staticmethod(
            lambda *args, **kwargs: {"stdout": "", "stderr": "", "returncode": "0"}))

        # A command no role may run: validation refuses it before execution.
        with pytest.raises(sandbox.CommandNotAllowed):
            sandbox.validate_command(["definitely_not_a_program"], "testing", str(tmp_path))

        # The lock must still be free afterwards, and a later command must pass.
        result = sandbox.SandboxExecutor.execute(["npm", "install"], str(tmp_path), category="install")

        assert result.get("returncode") == "0"
        assert not sandbox._the_lock_for(str(tmp_path)).locked()

    def test_the_same_workspace_spelled_differently_is_one_lock(self, tmp_path):
        """`/w`, `/w/` and a symlink to it are one directory and one lock."""
        target = tmp_path / "workspace"
        target.mkdir()
        link = tmp_path / "link"
        link.symlink_to(target)

        assert sandbox._the_lock_for(str(target)) is sandbox._the_lock_for(str(target) + "/")
        assert sandbox._the_lock_for(str(link)) is sandbox._the_lock_for(str(target))


class TestSerialisingTurnsTheCollisionIntoSavedWork:
    def test_the_second_identical_install_sees_the_first_one_s_result(
        self, tmp_path, monkeypatch
    ):
        """Why the lock covers the checks and not only the execution.

        `succeeded_this_way_before` reads the ledger. Three installs that all
        check before any of them finishes all see an empty ledger, so all three
        run - serially, which is safe, but pointlessly. Holding the lock across
        the checks means the second one reads the first one's entry, and the
        existing withholding logic applies to it: the collision becomes work not
        done.
        """
        runs: list[Any] = []

        def fake_run(command, repo_root, role_name="general", category="default",
                     extra_env=None, working_directory=None):
            runs.append(list(command))
            return {"stdout": "added 12 packages", "stderr": "", "returncode": "0"}

        monkeypatch.setattr(sandbox.SandboxExecutor, "_run", staticmethod(fake_run))

        for _ in range(sandbox.SUCCESSES_BEFORE_WITHHOLDING + 2):
            sandbox.SandboxExecutor.execute(
                ["npm", "install"], str(tmp_path), role_name="testing", category="install"
            )

        assert len(runs) <= sandbox.SUCCESSES_BEFORE_WITHHOLDING, (
            f"identical install ran {len(runs)} times with nothing written between"
        )
