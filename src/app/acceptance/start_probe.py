"""When the product does not start for the suite, the harness starts it the same way and says what it saw (behind `START_PROBE`).

Measured on a small-model run: the suite's web server timed out for 40 minutes and three sprint attempts; the defect said
only "Timed out waiting 60000ms from config.webServer", because Playwright does not pass on the service's output or the
answer its readiness request got. Started by hand the way the suite starts it - the project's `start.sh`, a free `PORT`
and a fresh, empty `DATA_DIR` - the service listened and answered `/health` with 503: its health check required the data
folder to exist. Here the harness does that: it runs the start command the suite's configuration names, with the same
environment, polls the readiness URL for a few seconds, and reports what the service printed and what the URL answered.
Nothing of the model's runs; the product's own processes are stopped after. In container mode the start, the requests
and the route listing all run in a command's own container through the sandbox (deep review 2026-11-18, item E1a).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False

#: How long the probe waits for the readiness URL to answer.
WAIT_SECONDS = 12.0
#: How much of the service's output goes with the defect.
MOST_OUTPUT = 1_200

_READY_URL = re.compile(r"url:\s*`http://127\.0\.0\.1:\$\{port\}([^`]*)`")


def enabled() -> bool:
    return is_on("START_PROBE", ON_BY_DEFAULT)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _ready_path(project: Path) -> str | None:
    try:
        text = (project / "playwright.config.js").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    found = _READY_URL.search(text)
    return (found.group(1) or "/") if found else None


def _probe_here(project: Path, env: dict, ready: str) -> tuple[str, str]:
    """(how the readiness path answered, what the service printed), the service started as a child of this process."""
    log = tempfile.NamedTemporaryFile(prefix="start-probe-", suffix=".log", delete=False)
    child = subprocess.Popen(  # noqa: S603 - the project's own start script, as the suite runs it
        ["sh", "start.sh"], cwd=project, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    status = ""
    started = time.monotonic()
    try:
        while time.monotonic() - started < WAIT_SECONDS:
            if child.poll() is not None:
                status = f"the service exited with code {child.returncode} before answering"
                break
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{env['PORT']}{ready}", timeout=2) as answer:
                    status = f"`GET {ready}` answered {answer.status}"
                    break
            except urllib.error.HTTPError as answer:
                status = f"`GET {ready}` answered {answer.code}"
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.3)
        else:
            status = f"`GET {ready}` got no answer in {WAIT_SECONDS:.0f} seconds"
    finally:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except OSError:
            pass
        child.wait(timeout=5)
        log.close()
    output = Path(log.name).read_text(encoding="utf-8", errors="replace").strip()
    Path(log.name).unlink(missing_ok=True)
    return status, output


#: Where the container probe's runner is copied for a command's container to see it, from the workspace root.
_RUNNER_IN_THE_WORKSPACE = ".harness/start_probe.cjs"


def _probe_in_its_container(repo_root: Path, project: Path, env: dict, ready: str) -> tuple[str, str]:
    """`_probe_here` through the sandbox: in container mode none of the product's code runs in the worker (E1a).

    The service and the requests to it share the command's own container (`start_probe.cjs`); its time limit is the
    `start` category's. ("", "") when the sandbox did not run it.
    """
    from app.tools.sandbox import SandboxExecutor

    runner = repo_root / _RUNNER_IN_THE_WORKSPACE
    runner.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).with_name("start_probe.cjs"), runner)
    try:
        outcome = SandboxExecutor.execute(
            ["node", os.path.relpath(runner, project), ready, f"{WAIT_SECONDS:.0f}", str(MOST_OUTPUT)],
            repo_root=str(repo_root), role_name="testing_specialist", category="start",
            extra_env=env, working_directory=project.relative_to(repo_root).as_posix() or None, for_the_harness=True,
        ) or {}
    finally:
        runner.unlink(missing_ok=True)
    try:
        said = json.loads(str(outcome.get("stdout") or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return "", ""
    if not isinstance(said, dict):
        return "", ""
    if "answered" in said:
        status = f"`GET {ready}` answered {said['answered']}"
    elif "exited" in said:
        status = f"the service exited with code {said['exited']} before answering"
    else:
        status = f"`GET {ready}` got no answer in {WAIT_SECONDS:.0f} seconds"
    return status, str(said.get("output") or "").strip()


def what_the_start_shows(repo_root: str | Path) -> str:
    """A paragraph for the start defect: what the service printed and how its readiness URL answered; "" when off or unknown."""
    if not enabled():
        return ""
    try:
        from app.stacks import contract
        from app.tools.sandbox import product_code_runs_in_its_own_container, product_environment

        record = contract.read(repo_root) or {}
        project = Path(repo_root) / str(record.get("project") or "")
        start = project / "start.sh"
        ready = _ready_path(project)
        if not start.is_file() or ready is None:
            return ""
        port = _free_port()
        contained = product_code_runs_in_its_own_container()
        if contained:
            # A folder that does not exist yet, in the command's own container: the suite hands the service one.
            env = {"PORT": str(port), "HOST": "127.0.0.1", "DATA_DIR": f"/tmp/start-probe-{uuid.uuid4().hex[:12]}"}
            status, output = _probe_in_its_container(Path(repo_root), project, env, ready)
            if not status:
                return ""
        else:
            data = tempfile.mkdtemp(prefix="start-probe-")
            os.rmdir(data)  # the suite hands the service a folder that does not exist yet
            # The suite's own start, not the worker's: none of the worker's secrets reach the product.
            env = product_environment(str(repo_root), {"PORT": str(port), "HOST": "127.0.0.1", "DATA_DIR": data})
            status, output = _probe_here(project, env, ready)
        shown = output[-MOST_OUTPUT:] if output else "(nothing)"
        hint = ""
        if re.search(r"answered [45]\d\d", status):
            hint = (f" The suite waits for `{ready}` to answer with success before any test runs; a service that "
                    f"answers {status.rsplit(' ', 1)[-1]} there is never considered started. The suite starts it with "
                    "`DATA_DIR` set to a folder that does not exist yet: the service creates what it needs there at "
                    "start, and its readiness answer does not depend on data being present.")
        if re.search(r"answered 404", status):
            hint += _the_routes_it_serves(repo_root, project, env, contained=contained)
        return (f"\n\nStarted the way the suite starts it (`sh start.sh`, `PORT` set, `DATA_DIR` a fresh folder), "
                f"{status}. It printed:\n{shown}{hint}")
    except Exception:  # noqa: BLE001 - the defect goes out as it was
        logger.debug("Could not probe the product's start", exc_info=True)
        return ""


def _the_routes_it_serves(repo_root: str | Path, project: Path, env: dict, *, contained: bool = False) -> str:
    """" The application ... serves these routes: ..." from the pack's own listing; "" when it has none. Never raises.

    Measured on one run: a router whose route was `/health`, mounted with `app.route('/health', healthRouter)`,
    served `/health/health`; the defect said the readiness route was not served, never which routes were, and the
    product did not start through two rounds of fixes. The listing imports the product's application, so in container
    mode it runs through the sandbox like the start (E1a).
    """
    try:
        from app.stacks import contract

        found = contract.the_pack(repo_root)
        command = tuple(getattr(found[0], "list_routes", ()) or ()) if found else ()
        if not command:
            return ""
        if contained:
            from app.tools.sandbox import SandboxExecutor

            outcome = SandboxExecutor.execute(
                list(command), repo_root=str(repo_root), role_name="testing_specialist", category="start",
                extra_env=env, working_directory=project.relative_to(Path(repo_root)).as_posix() or None,
                for_the_harness=True,
            ) or {}
            printed = str(outcome.get("stdout") or "")
        else:
            printed = subprocess.run(  # noqa: S603 - the pack's own listing, in the project
                list(command), cwd=project, env=env, capture_output=True, text=True, timeout=20,
            ).stdout
        routes = [line.strip() for line in printed.splitlines() if line.strip()][:40]
        if not routes:
            return ""
        return (" The application the start command runs has these as the routes it serves: "
                + ", ".join(f"`{route}`" for route in routes)
                + ". A route of a router mounted under a path is served at that path followed by its own.")
    except Exception:  # noqa: BLE001 - the probe's report stands without it
        return ""


__all__ = ["ON_BY_DEFAULT", "enabled", "what_the_start_shows"]
