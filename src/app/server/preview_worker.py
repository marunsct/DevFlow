"""The worker's half of a product preview (plan WS.4): copy the product, start it in its own container, end it.

Only the worker reaches Docker, and its pool may be busy with runs for hours, so previews are not Celery tasks: a
daemon thread on the Celery parent takes the app's requests from a Redis list (`preview.REQUESTS_KEY`) and ends
previews nobody has used for a while. A second thread says every few seconds in Redis (`preview.WORKER_KEY`, lapsing
in seconds) that the worker serves previews and whether its commands run in containers of their own: the app refuses a start on that word,
since only the worker carries `SANDBOX_EXECUTION_MODE`.

The product is started as the delivered start starts it (`acceptance.start_output`): its own start command
(`command_for`), a fresh home, the plain PATH, a data directory of its own, the restored package cache where its
language keeps one, the sandbox's container flags (no capabilities, read-only root, memory, CPU and process caps,
the worker's unprivileged user) and the sandbox's environment for a command's container, which holds none of the
worker's secrets (`sandbox._container_environment`). It differs from the start probe in two ways only: it is not
ended by a time limit, and its network is the preview network, which the app is on and which has no way out
(compose `internal: true`): a product that fetches packages when it starts fails there and says so. The product is
given an inner port (`inner_port`, the public one + 1000) and a small Node forwarder (`preview_forwarder.js`) takes
the public port on every address, so a product that listens on 127.0.0.1 only is still reached from the app.

The container sees only a scratch copy, never the run's workspace: `accepted` is the last accepted sprint's commit,
`live` the workspace's files now; both get the installed folders (git-ignored, such as `node_modules` or `.venv`)
hard-linked from the workspace, as the start probe's copy does.
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import subprocess
import tarfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from app.server import preview

logger = logging.getLogger(__name__)

#: Top-level folders of a workspace the copy never takes: the history, the harness's records, the agent's home.
_NOT_COPIED = frozenset({".git", ".harness", ".agent-home"})
#: The harness's records the copy does take: what names the stack and its pinned runtimes.
_RECORDS_KEPT = (".harness/stack-pack.json", ".harness/runtimes.json")
#: How long the loop waits for a request before it looks for idle previews.
_WAIT_SECONDS = 5
#: Seconds one docker command may take.
_DOCKER_SECONDS = 60
#: The port forwarder the preview's container runs beside the product (`docker_command`), and its name in the copy.
_FORWARDER = Path(__file__).with_name("preview_forwarder.js")
_FORWARDER_NAME = "forward.js"
#: How often the worker says it serves previews (`keep_saying_it_serves`): well inside `preview.WORKER_SECONDS`.
_BEAT_SECONDS = 5


class CannotStart(Exception):
    """The product cannot be started for a preview, in a sentence a person can act on."""


def _git(root: Path, *args: str, text: bool = True) -> Any:
    from app.tools.version_control import git_safely

    done = subprocess.run([*git_safely(), "-C", str(root), *args], capture_output=True, text=text, timeout=60,
                          check=False)
    if done.returncode != 0:
        raise CannotStart(f"Reading the workspace's history failed: {str(done.stderr or '')[:200]}")
    return done.stdout


def _link(source: str, target: str) -> None:
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target, follow_symlinks=False)


def _kept(relative: str) -> bool:
    return bool(relative) and relative.split("/", 1)[0] not in _NOT_COPIED and ".." not in relative.split("/")


def _the_accepted_sprint(root: Path, scratch: Path, commit: str = "") -> None:
    """The sprint's files: the commit the app recorded at the start (plan UX.11, the one the status names), else the
    last accepted sprint's."""
    from app.tools.version_control import accepted_sprints

    sprints = accepted_sprints(root)
    if not sprints:
        raise CannotStart("No sprint has been accepted yet.")
    archive = _git(root, "archive", "--format=tar", commit or f"refs/tags/sprint-{sprints[-1]}", text=False)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members = [m for m in tar.getmembers() if _kept(m.name.rstrip("/"))]
        # Fresh files, never links to the workspace's: the product may write its own files.
        tar.extractall(scratch, members=members, filter="data")


def _the_workspace_now(root: Path, scratch: Path) -> None:
    listed = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    for relative in dict.fromkeys(part for part in listed.split("\0") if part):
        source = root / relative
        if not _kept(relative) or not (source.is_file() or source.is_symlink()):
            continue  # removed since it was committed, or not a file
        target = scratch / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)


def _the_installed_folders(root: Path, scratch: Path) -> None:
    """What the workspace's installs and builds made (git-ignored), hard-linked: a stranger installs before starting."""
    listed = _git(root, "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory")
    for relative in (part.rstrip("/") for part in listed.split("\0") if part):
        source, target = root / relative, scratch / relative
        if not _kept(relative) or target.exists() or source.is_symlink():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, symlinks=True, copy_function=_link)
        elif source.is_file():
            _link(str(source), str(target))


def copy_the_product(repo_root: str, source: str, scratch: Path, commit: str = "") -> None:
    """The scratch copy a preview starts from, laid out as the workspace is, so its paths mean what they meant."""
    root = Path(repo_root)
    if not (root / ".git").exists():
        raise CannotStart("This run's workspace keeps no history to copy the product from.")
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True)
    if source == "accepted":
        _the_accepted_sprint(root, scratch, commit)
    else:
        _the_workspace_now(root, scratch)
    _the_installed_folders(root, scratch)
    for record in _RECORDS_KEPT:
        if (root / record).is_file():
            (scratch / record).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / record, scratch / record)


def _the_restored_packages(repo_root: str, scratch: Path) -> dict[str, str]:
    """The start probe's restored package cache (`start_output._the_restored_packages`), hard-linked into the copy."""
    from app.acceptance.start_output import _the_restored_packages

    found = {}
    for variable, cache in _the_restored_packages(repo_root).items():
        relative = os.path.relpath(cache, repo_root)
        if not _kept_cache(relative):
            continue
        target = scratch / relative
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(cache, target, symlinks=True, copy_function=_link)
        found[variable] = str(target)
    return found


def _kept_cache(relative: str) -> bool:
    return relative.startswith(".agent-home/") and ".." not in relative.split("/")


def docker_command(state: dict[str, Any], argv: list[str], project: str, repo_root: str) -> list[str]:
    """`docker run -d` for the preview: the sandbox's container flags, on the preview network, in the scratch copy."""
    from app.acceptance.start_output import _data_variable
    from app.tools import sandbox

    scratch = Path(state["scratch"])
    output = scratch / preview.OUTPUT_DIR
    for folder in (output, output / "home", output / "data"):
        folder.mkdir(parents=True, exist_ok=True)
    stand_ins: list[str] = []
    environment, in_front = sandbox._container_environment(str(scratch), {
        "PORT": str(state["port"]), "HOST": "0.0.0.0",  # nosec B104 - the preview network only; nothing else is on it
        _data_variable(repo_root): str(output / "data"), "HOME": str(output / "home"),
        "PATH": os.environ.get("PATH", ""), **_the_restored_packages(repo_root, scratch),
    }, stand_ins)
    memory = f"{sandbox._process_memory(str(scratch), argv) // 1024**2}m"
    where = f"{sandbox.CONTAINER_WORKSPACE}/{project}".rstrip("/") if project else sandbox.CONTAINER_WORKSPACE
    logs = f"{sandbox.CONTAINER_WORKSPACE}/{preview.OUTPUT_DIR}"
    command = [
        sandbox._docker_binary(), "run", "-d", "--rm",
        "--name", str(state["host"]),
        "--label", "devflow.preview=1",
        "--network", preview.network(),
        "--memory", memory, "--memory-swap", memory,
        "--cpus", sandbox.CPU_LIMIT,
        "--pids-limit", sandbox.PIDS_LIMIT,
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",  # nosec B108 - a tmpfs inside the container
        *sandbox._workspace_mount(str(scratch)),
        "-w", where,
        "-u", f"{os.getuid()}:{os.getgid()}",
    ]
    for key, value in environment.items():
        command += ["--env", f"{key}={value}"]
    command.append(sandbox._image_for(os.path.basename(argv[0]), str(scratch)))
    # A product that listens on 127.0.0.1 only is reached through the forwarder: it gets the inner port, and the
    # forwarder takes the public one on every address. Both are children of the one shell, so they end with the
    # container. An image without Node starts the product on the public port itself, and says so.
    shutil.copyfile(_FORWARDER, output / _FORWARDER_NAME)
    port, inner, log = int(state["port"]), inner_port(int(state["port"])), f"{logs}/{preview.OUTPUT_FILE}"
    script = (
        "if command -v node >/dev/null 2>&1; then "
        f"node {logs}/{_FORWARDER_NAME} {port} {inner} >>{log} 2>&1 & PORT={inner}; export PORT; "
        f"else echo 'preview: this image has no Node to forward port {port}; the product must listen on HOST "
        f"itself' >>{log}; : >{logs}/{preview.UNFORWARDED_FILE}; fi; "
        # What the product writes and how it ended land in the copy, where the app reads them: the container is
        # removed when it exits.
        f'"$@" >>{log} 2>&1; echo $? >{logs}/{preview.EXIT_FILE}'
    )
    command += ["/bin/sh", "-c", script, "sh", *sandbox._with_the_path_in_front(argv, in_front)]
    return command


def inner_port(port: int) -> int:
    """The port the product itself is given inside its container: the public port + 1000 (below it near the top of
    the range). The container has its own network, so it never meets another preview's."""
    return port + 1000 if port + 1000 <= 65535 else port - 1000


def _docker(*args: str) -> subprocess.CompletedProcess:
    from app.tools.sandbox import _docker_binary

    return subprocess.run([_docker_binary(), *args], capture_output=True, text=True, errors="replace", timeout=_DOCKER_SECONDS,
                          check=False)


def _still_wanted(state: dict[str, Any], client: Any) -> bool:
    now = preview.read(state["run_id"], client)
    return bool(now and now.get("instance") == state.get("instance") and now.get("state") in preview.ACTIVE)


def start(request: dict[str, Any], client: Any = None,
          run: Callable[[list[str]], subprocess.CompletedProcess] | None = None) -> None:
    """Copy the product and start its container, or record why it could not be. Never raises."""
    client = client or preview._redis()
    state = preview.read(str(request.get("run_id") or ""), client)
    if not state or state.get("instance") != request.get("instance") or state.get("state") != "starting":
        return  # stopped, or replaced, before the worker reached it
    repo_root = str(state.get("repo_root") or "")
    try:
        copy_the_product(repo_root, str(state.get("source")), Path(state["scratch"]), str(state.get("commit") or ""))
        from app.acceptance.start_output import command_for

        found = command_for(state["scratch"])
        if found is None:
            raise CannotStart("The product says of no way to start it (no start script, start command or entry file).")
        argv, project = found
        command = docker_command(state, argv, project, repo_root)
        done = (run or (lambda c: subprocess.run(c, capture_output=True, text=True, errors="replace", timeout=_DOCKER_SECONDS,
                                                 check=False)))(command)
        if done.returncode != 0:
            raise CannotStart(f"The container did not start: {str(done.stderr or '').strip()[-500:]}")
    except Exception as error:  # noqa: BLE001 - said on the run page, never a dead worker thread
        reason = str(error) if isinstance(error, CannotStart) else "The preview could not be prepared."
        if not isinstance(error, CannotStart):
            logger.warning("A preview could not be prepared", exc_info=True)
        preview.stop(state["run_id"], reason, client=client, state=state, as_state="failed")
        return
    if not _still_wanted(state, client):
        stop({"run_id": state["run_id"], "instance": state["instance"]}, client, state=state)
        return
    preview.write({**(preview.read(state["run_id"], client) or state), "running": True,
                   "command": " ".join(argv)}, client)


def stop(request: dict[str, Any], client: Any = None, state: dict[str, Any] | None = None,
         run: Callable[..., subprocess.CompletedProcess] | None = None) -> None:
    """End a preview's container and remove its copy. Never raises."""
    run_id, instance = str(request.get("run_id") or ""), str(request.get("instance") or "")
    if not run_id or not instance:
        return
    try:
        (run or _docker)("kill", preview.container_name(run_id, instance))
    except Exception:  # noqa: BLE001 - it has stopped already, or Docker is gone with it
        logger.debug("Could not end a preview's container", exc_info=True)
    scratch = preview.scratch_for(run_id, instance)
    if scratch.parent.name == ".previews":
        shutil.rmtree(scratch, ignore_errors=True)


def end_the_idle(client: Any = None, now: float | None = None) -> list[str]:
    """Stop every preview no request reached for the idle time, and every one that never answered; their run ids."""
    client = client or preview._redis()
    ended = []
    for state in preview.all_states(client):
        if state.get("state") in preview.ACTIVE:
            after = preview.observe(state["run_id"], client=client, now=now, judge_the_start=False)
            if after and after.get("state") not in preview.ACTIVE:
                ended.append(state["run_id"])
    return ended


def end_the_orphans(client: Any = None, run: Callable[..., subprocess.CompletedProcess] | None = None) -> list[str]:
    """End the preview containers no starting or ready preview holds (a worker restart lost track of them). Only while
    previews are on: otherwise nothing here calls Docker."""
    if not preview.preview_switch.enabled():
        return []
    try:
        client = client or preview._redis()
        held = {str(s.get("host")) for s in preview.all_states(client) if s.get("state") in preview.ACTIVE}
        listed = (run or _docker)("ps", "--filter", "label=devflow.preview=1", "--format", "{{.Names}}")
        ended = [name for name in str(listed.stdout or "").split() if name.startswith("devflow-preview-")
                 and name not in held]
        for name in ended:
            (run or _docker)("kill", name)
        return ended
    except Exception:  # noqa: BLE001 - the idle sweep and a person's stop still end the held ones
        logger.debug("Could not look for orphaned previews", exc_info=True)
        return []


def handle(raw: str, client: Any = None) -> None:
    try:
        request = json.loads(raw)
    except ValueError:
        return
    if not isinstance(request, dict):
        return
    if request.get("action") == "start":
        start(request, client)
    elif request.get("action") == "stop":
        stop(request, client)


def say_it_serves(client: Any = None) -> None:
    """Tell the app this worker serves previews and whether its commands run in containers of their own: the app
    cannot know, since only the worker carries `SANDBOX_EXECUTION_MODE`."""
    from app.tools.sandbox import product_code_runs_in_its_own_container

    preview.say_the_worker_serves(product_code_runs_in_its_own_container(), client)


def serve_for_ever(stop_when: Callable[[], bool] = lambda: False) -> None:
    """Take the app's preview requests and end idle previews, for the worker's life. Never raises."""
    last_sweep = 0.0
    while not stop_when():
        try:
            client = preview._redis()
            found = client.brpop(preview.REQUESTS_KEY, timeout=_WAIT_SECONDS)
            if found:
                handle(found[1], client)
            if time.monotonic() - last_sweep >= 30:
                last_sweep = time.monotonic()
                end_the_idle(client)
        except Exception:  # noqa: BLE001 - Redis away for a moment: try again shortly
            logger.debug("The preview loop could not read its requests", exc_info=True)
            time.sleep(_WAIT_SECONDS)


def keep_saying_it_serves(stop_when: Callable[[], bool] = lambda: False) -> None:
    """Say it serves every `_BEAT_SECONDS`, for the worker's life, on a thread of its own: the loop may spend a minute
    on one start, and the word must mean the worker is alive, not that the loop is idle. Never raises."""
    while not stop_when():
        try:
            say_it_serves()
        except Exception:  # noqa: BLE001 - Redis away for a moment: the app refuses starts until it is back
            logger.debug("Could not say the worker serves previews", exc_info=True)
        time.sleep(_BEAT_SECONDS)


def serve_in_the_background(stop_when: Callable[[], bool] = lambda: False) -> threading.Thread:
    """The preview loop and its heartbeat, as daemon threads that end with the worker; the loop's thread."""
    threading.Thread(target=keep_saying_it_serves, args=(stop_when,), name="product-previews-heartbeat",
                     daemon=True).start()
    thread = threading.Thread(target=serve_for_ever, args=(stop_when,), name="product-previews", daemon=True)
    thread.start()
    return thread


__all__ = ["CannotStart", "copy_the_product", "docker_command", "end_the_idle", "handle", "inner_port",
           "keep_saying_it_serves", "say_it_serves", "serve_for_ever", "serve_in_the_background", "start", "stop"]
