"""A command's temporary directory is short enough for a tool's Unix socket.

Measured on one run: a TypeScript runner made its IPC pipe in the temporary
directory, which was the workspace's `.agent-home`; under the run's workspace
the pipe's path was 112 characters, past the 107 a Unix socket allows, and
every launch of the product failed with `listen EINVAL`. No acceptance test
could start it.
"""

from __future__ import annotations

import os
import socket

from app.tools.sandbox import _child_environment

#: A Unix socket's path limit (`sun_path` less its terminator).
UNIX_SOCKET_PATH_LIMIT = 107


def _deep(tmp_path, name: str):
    workspace = tmp_path / "workspaces" / "default" / f"workspace-run-{name}-6a43-4184-8647-5232dde412c4"
    workspace.mkdir(parents=True)
    return workspace


def test_a_tool_can_listen_on_a_socket_in_its_temporary_directory(tmp_path):
    workspace = _deep(tmp_path, "c2e62179")
    temporary = _child_environment(str(workspace), None)["TMPDIR"]
    pipe = os.path.join(temporary, "tsx-10001", "826.pipe")
    os.makedirs(os.path.dirname(pipe), exist_ok=True)

    assert len(pipe) <= UNIX_SOCKET_PATH_LIMIT
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(pipe)
        server.listen(1)


def test_each_workspace_has_its_own_and_only_its_owner_can_read_it(tmp_path):
    one = _child_environment(str(_deep(tmp_path, "aaaaaaaa")), None)["TMPDIR"]
    two = _child_environment(str(_deep(tmp_path, "bbbbbbbb")), None)["TMPDIR"]

    assert one != two
    assert os.path.isdir(one) and oct(os.stat(one).st_mode & 0o777) == "0o700"
    assert one == _child_environment(str(tmp_path / "workspaces" / "default" / "workspace-run-aaaaaaaa-6a43-4184-8647-5232dde412c4"), None)["TMPDIR"], "the same workspace, the same directory"
