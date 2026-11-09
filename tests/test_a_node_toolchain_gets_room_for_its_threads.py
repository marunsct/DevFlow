"""A pack whose tests run on Node gets a data limit its worker threads can start under.

Measured live: once the page built, Playwright's runner stopped at "Fatal process
out of memory: Failed to reserve virtual memory for CodeRange" in
`node::worker::Worker::Run` - every acceptance file, five seconds in all - and
the round recorded 13 criteria as not working. Under the sandbox's data limit
four Node worker threads would not start at 1 or 2 GB and ran at 3 GB: each
thread's V8 instance reserves a code range the limit counts. The Angular pack
had declared 4 GB for the same reason; no other pack had.
"""
from __future__ import annotations

from app.stacks import contract, pack_named
from app.tools import sandbox


def _workspace(tmp_path, pack_name):
    contract.write(tmp_path, pack_named(pack_name), "shop", "Shop")
    return tmp_path


def test_a_node_test_runner_is_given_room_for_its_threads(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "MEMORY_LIMIT", "1g")

    assert sandbox._process_memory(_workspace(tmp_path, "fullstack-react-fastapi")) >= 4 * 1024**3


def test_a_pack_that_declares_more_keeps_it(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "MEMORY_LIMIT", "1g")
    pack = pack_named("browser-angular")
    if pack is None:
        return
    assert sandbox._process_memory(_workspace(tmp_path, "browser-angular")) >= 4 * 1024**3


def test_a_toolchain_that_runs_no_node_keeps_the_configured_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "MEMORY_LIMIT", "1g")
    workspace = _workspace(tmp_path, "python-http-api")

    assert sandbox._process_memory(workspace) == 1024**3


def test_a_node_command_gets_room_in_a_project_no_pack_covers(tmp_path, monkeypatch):
    """Measured: a stack no pack covers (its setup replayed or written by an agent) has no pack to say its tests run on
    Node, so `npx vitest run` ran under the 1 GB limit and every worker thread died with "Failed to reserve virtual
    memory for CodeRange" (exit 133): the setup could not be proven and the locked suite could not run."""
    monkeypatch.setattr(sandbox, "MEMORY_LIMIT", "1g")

    assert sandbox._process_memory(tmp_path, ["npx", "vitest", "run"]) >= 4 * 1024**3
    assert sandbox._process_memory(tmp_path, ["/usr/bin/node", "--test"]) >= 4 * 1024**3


def test_a_command_that_starts_no_node_program_keeps_the_configured_limit_in_such_a_project(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "MEMORY_LIMIT", "1g")

    assert sandbox._process_memory(tmp_path, ["python3", "-m", "pytest"]) == 1024**3
    assert sandbox._process_memory(tmp_path) == 1024**3
