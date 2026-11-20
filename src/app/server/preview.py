"""Try it: a preview of the product a person can use while the run builds it (plan WS.4, behind `PRODUCT_PREVIEW`).

`POST /runs/{id}/preview` asks the worker to start the product the way its user would - the delivered start
(`acceptance.start_output.command_for`), from a scratch copy of the last accepted sprint (`accepted`, the default) or
of the workspace now (`live`, "being built") - in a container of its own on the preview network, on a port from a
fixed range (`preview_worker`). One preview per run; it lives until a person stops it or no request reaches it for
`PRODUCT_PREVIEW_IDLE_MINUTES`.

The app reaches the product on the preview network and serves it at
`/api/runs/{id}/preview/app/{token}/...`. The token is short-lived and signed with the app's secret, bound to the run,
to this one preview and to its expiry; it is carried in the path, so a page's relative links keep it and nothing
needs a cookie (a sandboxed frame sends none). No header of the browser's reaches the product but a short list of
content headers: never its cookies or its credentials. A preview served from the app's own host is sandboxed by its
response's Content-Security-Policy as well as by the frame, so the product's script never runs with the app's origin
(where the person's sign-in is kept), however the page is opened. `PRODUCT_PREVIEW_ORIGIN` names a separate origin
for previews; the proxy then answers only requests made to it.

State lives in Redis, shared by the app and the worker; the worker alone starts and stops containers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import socket
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: The states a preview passes through. `starting` and `ready` hold a container.
ACTIVE = frozenset({"starting", "ready"})
#: Where the app keeps each run's preview, and where it asks the worker to act.
STATE_KEY = "devflow:preview:run:{run_id}"
REQUESTS_KEY = "devflow:preview:requests"
LOCK_KEY = "devflow:preview:lock:{run_id}"
#: Where the worker's preview loop says, on every pass, that it serves previews and how it runs commands: only the
#: worker carries `SANDBOX_EXECUTION_MODE`, so the app reads it here, never from its own environment.
WORKER_KEY = "devflow:preview:worker"
#: How long one such word lasts: a few of the loop's passes, so a stopped worker is seen within seconds.
WORKER_SECONDS = 20
#: How long a preview's record outlives its last change: a stopped one says why for a day.
STATE_TTL_SECONDS = 24 * 3600
#: Where the product's output and its exit code land, inside the scratch copy (written by the container's wrapper).
OUTPUT_DIR = ".preview"
OUTPUT_FILE = "output.log"
EXIT_FILE = "exit-code"
#: Left there when the product's image has no Node to run the port forwarder (`preview_worker.docker_command`): the
#: product is then reached on its own port only, as it binds it.
UNFORWARDED_FILE = "not-forwarded"
#: Characters of the product's output shown when it fails.
MOST_OUTPUT = 2_000
#: The path the proxy serves a preview at, below the app's `/api/runs/{id}`.
APP_PATH = "preview/app"
#: Product kinds that have a page to show; a service gets the request console instead.
_KINDS_WITH_A_PAGE = frozenset({"browser_app", "fullstack"})


class _ProductPreview:
    """`PRODUCT_PREVIEW` as the switch registry reads one: off in code like every switch."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = (
        "A person can start the product from the run page and use it while the run builds it: the last accepted "
        "sprint or the workspace now, started as its user would in a container of its own, shown through the app "
        "behind a short-lived signed link, and stopped when idle. It adds a long-lived service per preview."
    )

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on("PRODUCT_PREVIEW", _ProductPreview.ON_BY_DEFAULT)


preview_switch = _ProductPreview()


class PreviewRefused(Exception):
    """A request the preview cannot honour, with the HTTP status that says why."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


# --- settings -------------------------------------------------------------------------------------------------------


def _int_setting(name: str, default: int) -> int:
    try:
        return max(1, int(str(os.environ.get(name) or default).strip()))
    except ValueError:
        return default


def idle_seconds() -> int:
    return 60 * _int_setting("PRODUCT_PREVIEW_IDLE_MINUTES", 15)


def token_seconds() -> int:
    return 60 * _int_setting("PRODUCT_PREVIEW_TOKEN_MINUTES", 30)


def start_seconds() -> int:
    return _int_setting("PRODUCT_PREVIEW_START_SECONDS", 240)


def network() -> str:
    """The container network previews run on: one the app is on and nothing else of the harness is."""
    return str(os.environ.get("PRODUCT_PREVIEW_NETWORK") or "").strip()


def ports() -> range:
    """The fixed range a preview's port comes from; its size is also the most previews at once."""
    raw = str(os.environ.get("PRODUCT_PREVIEW_PORTS") or "42000-42019").strip()
    try:
        low, _, high = raw.partition("-")
        first, last = int(low), int(high or low)
        if 1024 <= first <= last <= 65535:
            return range(first, last + 1)
    except ValueError:
        pass
    return range(42000, 42020)


def separate_origin() -> str:
    """The origin previews are served from when the deployment has one (`https://preview.example.com`); "" for the
    app's own host under its distinct path."""
    return str(os.environ.get("PRODUCT_PREVIEW_ORIGIN") or "").strip().rstrip("/")


# --- the signed link ------------------------------------------------------------------------------------------------


def _signing_key() -> bytes:
    from app.server.auth import SECRET_KEY

    # Derived, so a preview token is never a valid signature of anything else the app signs.
    return hmac.new(str(SECRET_KEY).encode(), b"product-preview-token", hashlib.sha256).digest()


#: The last part of a link signed for pointing at the page (plan WS.5): its pages carry the picker script.
POINTING = "pick"


def _signature(run_id: str, instance: str, expires: int, mode: str = "") -> str:
    signed = f"{run_id}\n{instance}\n{expires}" + (f"\n{mode}" if mode else "")
    digest = hmac.new(_signing_key(), signed.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def token_for(run_id: str, instance: str, expires: int, *, pointing: bool = False) -> str:
    """A token for one run's one preview until `expires` (seconds since the epoch): path-safe characters only.
    `pointing` signs it for pointing at the page: the mode is signed with the rest, so a page cannot add it."""
    mode = POINTING if pointing else ""
    token = f"{int(expires)}.{instance}.{_signature(run_id, instance, int(expires), mode)}"
    return f"{token}.{mode}" if mode else token


def is_for_pointing(token: str) -> bool:
    """Whether a token (already checked by `token_problem`) was signed for pointing at the page."""
    parts = str(token or "").split(".")
    return len(parts) == 4 and parts[3] == POINTING


def token_problem(token: str, run_id: str, instance: str, now: float | None = None) -> str:
    """Why `token` does not open this run's current preview, or "" when it does."""
    parts = str(token or "").split(".")
    if len(parts) not in (3, 4) or not parts[0].isdigit() or (len(parts) == 4 and parts[3] != POINTING):
        return "not a preview link"
    expires, made_for, signature = int(parts[0]), parts[1], parts[2]
    mode = parts[3] if len(parts) == 4 else ""
    if not hmac.compare_digest(signature, _signature(run_id, made_for, expires, mode)):
        return "not a preview link of this run"
    if not instance or not hmac.compare_digest(made_for, instance):
        return "a link to a preview that was stopped"
    if expires <= (time.time() if now is None else now):
        return "an expired preview link"
    return ""


def app_prefix(run_id: str, token: str) -> str:
    return f"/api/runs/{run_id}/{APP_PATH}/{token}"


# --- the shared record ----------------------------------------------------------------------------------------------


def _redis() -> Any:
    from app.server.redis_client import get_redis_client

    return get_redis_client()


def read(run_id: str, client: Any = None) -> dict[str, Any] | None:
    raw = (client or _redis()).get(STATE_KEY.format(run_id=run_id))
    if not raw:
        return None
    try:
        found = json.loads(raw)
    except ValueError:
        return None
    return found if isinstance(found, dict) else None


def write(state: dict[str, Any], client: Any = None) -> None:
    (client or _redis()).set(STATE_KEY.format(run_id=state["run_id"]), json.dumps(state), ex=STATE_TTL_SECONDS)


def ask_the_worker(request: dict[str, Any], client: Any = None) -> None:
    (client or _redis()).lpush(REQUESTS_KEY, json.dumps(request))


def all_states(client: Any = None) -> list[dict[str, Any]]:
    client = client or _redis()
    found = []
    for key in client.scan_iter(match=STATE_KEY.format(run_id="*")):
        raw = client.get(key)
        try:
            state = json.loads(raw) if raw else None
        except ValueError:
            state = None
        if isinstance(state, dict):
            found.append(state)
    return found


def say_the_worker_serves(contained: bool, client: Any = None) -> None:
    """The worker's word that its preview loop is alive, and whether product commands run in a container of their own
    there; it lapses after `WORKER_SECONDS` unless said again."""
    (client or _redis()).set(WORKER_KEY, json.dumps({"contained": bool(contained), "at": time.time()}),
                             ex=WORKER_SECONDS)


def the_worker_serving(client: Any = None) -> dict[str, Any] | None:
    """What the worker's preview loop last said, while it lasts; None when no worker is serving previews."""
    raw = (client or _redis()).get(WORKER_KEY)
    try:
        found = json.loads(raw) if raw else None
    except ValueError:
        return None
    return found if isinstance(found, dict) else None


def _a_free_port(client: Any) -> int | None:
    taken = {int(s.get("port") or 0) for s in all_states(client) if s.get("state") in ACTIVE}
    return next((port for port in ports() if port not in taken), None)


def container_name(run_id: str, instance: str) -> str:
    """The preview's container, unique to this preview: a stop meant for an older one cannot reach a newer one."""
    return f"devflow-preview-{hashlib.sha256(run_id.encode()).hexdigest()[:12]}-{instance[:8]}"


def scratch_for(run_id: str, instance: str) -> Path:
    """Where the product is copied to be started: beside the workspaces, never inside the run's own."""
    from app.server.workspaces import workspace_root

    return workspace_root() / ".previews" / f"{hashlib.sha256(run_id.encode()).hexdigest()[:12]}-{instance}"


# --- what the app asks and sees -------------------------------------------------------------------------------------


def _the_kind_has_a_page(repo_root: str) -> bool | None:
    try:
        from app.stacks import contract

        found = contract.the_pack(repo_root)
    except Exception:  # noqa: BLE001 - unknown: the page and the console are both offered
        return None
    if not found:
        return None
    return found[0].kind in _KINDS_WITH_A_PAGE


def start(run_id: str, repo_root: str, source: str, *, client: Any = None, now: float | None = None) -> dict[str, Any]:
    """Record a starting preview and ask the worker for it; `PreviewRefused` when it cannot be had."""
    if not preview_switch.enabled():
        raise PreviewRefused(403, "Previews are off on this deployment (switch PRODUCT_PREVIEW).")
    if not network():
        raise PreviewRefused(409, "No preview network is configured (PRODUCT_PREVIEW_NETWORK).")
    if source not in ("accepted", "live"):
        raise PreviewRefused(422, "The source is `accepted` or `live`.")
    client = client or _redis()
    # The worker's word, not this process's environment: the worker alone runs commands and carries their setting.
    worker = the_worker_serving(client)
    if worker is None:
        raise PreviewRefused(503, "No worker is serving previews right now; try again once the worker is running.")
    if not worker.get("contained"):
        raise PreviewRefused(409, "A preview runs the product in a container of its own, and this deployment's worker "
                                  "runs commands in itself (SANDBOX_EXECUTION_MODE is not container).")
    label = "being built"
    if source == "accepted":
        from app.tools.version_control import accepted_sprints

        sprints = accepted_sprints(repo_root)
        if not sprints:
            raise PreviewRefused(409, "No sprint has been accepted yet; preview the workspace as it is being built.")
        label = f"sprint {sprints[-1]}"
    now = time.time() if now is None else now
    lock = LOCK_KEY.format(run_id=run_id)
    if not client.set(lock, "1", nx=True, ex=10):
        raise PreviewRefused(409, "This run's preview is being started or stopped; try again in a moment.")
    try:
        current = read(run_id, client)
        if current and current.get("state") in ACTIVE:
            raise PreviewRefused(409, "This run already has a preview; stop it before starting another.")
        port = _a_free_port(client)
        if port is None:
            raise PreviewRefused(503, "Every preview port is in use; stop another preview first.")
        instance = secrets.token_hex(8)
        state = {
            "run_id": run_id, "instance": instance, "state": "starting", "source": source, "label": label,
            "port": port, "host": container_name(run_id, instance), "scratch": str(scratch_for(run_id, instance)),
            "repo_root": str(repo_root), "started_at": now, "last_used": now, "reason": "", "error": "",
            "has_page": _the_kind_has_a_page(repo_root), "command": "",
        }
        write(state, client)
        ask_the_worker({"action": "start", "run_id": run_id, "instance": instance}, client)
        return state
    finally:
        client.delete(lock)


def stop(run_id: str, reason: str, *, client: Any = None, state: dict[str, Any] | None = None,
         as_state: str = "stopped", error: str = "") -> dict[str, Any] | None:
    """Mark the run's preview stopped (or failed) and ask the worker to end its container. None when there is none."""
    client = client or _redis()
    state = state or read(run_id, client)
    if state is None:
        return None
    if state.get("state") in ACTIVE:
        state = {**state, "state": as_state, "reason": reason, "error": error or state.get("error") or ""}
        write(state, client)
    ask_the_worker({"action": "stop", "run_id": run_id, "instance": state.get("instance") or ""}, client)
    return state


def touch(state: dict[str, Any], *, client: Any = None, now: float | None = None) -> None:
    """A request reached the preview: its idle time starts again (written at most every few seconds)."""
    now = time.time() if now is None else now
    if now - float(state.get("last_used") or 0) < 5:
        return
    # Read again: a stop between the request's start and now must not be undone by this write.
    current = read(str(state["run_id"]), client)
    if current and current.get("instance") == state.get("instance") and current.get("state") in ACTIVE:
        write({**current, "last_used": now}, client)


def _answers(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=0.5):
            return True
    except OSError:
        return False


def what_it_wrote(scratch: str) -> tuple[str | None, str]:
    """(its exit code, or None while it runs; the product's own error lines and the end of what it wrote)."""
    from app.acceptance.what_went_wrong import shown

    folder = Path(scratch) / OUTPUT_DIR
    try:
        wrote = (folder / OUTPUT_FILE).read_text(encoding="utf-8", errors="replace")[-200_000:]
    except OSError:
        wrote = ""
    try:
        code: str | None = (folder / EXIT_FILE).read_text(encoding="utf-8").strip() or "?"
    except OSError:
        code = None
    return code, shown(wrote, MOST_OUTPUT)


def observe(run_id: str, *, client: Any = None, now: float | None = None,
            answers: Callable[[str, int], bool] | None = None, judge_the_start: bool = True) -> dict[str, Any] | None:
    """The preview's state as it is now: a starting product that answers is ready; one that exited, never answered in
    time or sat idle is ended, with what it wrote when it failed. Only the app can reach the product, so only the app
    judges its start (`judge_the_start`); the worker's sweep ends the exited and the idle."""
    client = client or _redis()
    now = time.time() if now is None else now
    state = read(run_id, client)
    if state is None or state.get("state") not in ACTIVE:
        return state
    code, wrote = what_it_wrote(str(state.get("scratch") or ""))
    if code is not None:
        return stop(run_id, f"the product stopped by itself with exit code {code}", client=client, state=state,
                    as_state="failed", error=wrote)
    if now - float(state.get("last_used") or 0) > idle_seconds():
        return stop(run_id, f"no request reached it for {idle_seconds() // 60} minutes", client=client, state=state)
    if state.get("state") == "starting" and judge_the_start:
        if state.get("running") and (answers or _answers)(str(state.get("host")), int(state.get("port") or 0)):
            state = {**state, "state": "ready", "ready_at": now}
            write(state, client)
        elif now - float(state.get("started_at") or now) > start_seconds():
            unforwarded = (Path(str(state.get("scratch") or "")) / OUTPUT_DIR / UNFORWARDED_FILE).exists()
            return stop(run_id, f"it did not answer on port {state.get('port')} within {start_seconds()} seconds; a "
                                "preview's product listens on the HOST and PORT it is given"
                                + ("; its image has no Node to forward the port, so it must listen on HOST itself"
                                   if unforwarded else ""),
                        client=client, state=state, as_state="failed", error=wrote)
    return state


def public(state: dict[str, Any] | None, run_id: str, *, now: float | None = None) -> dict[str, Any]:
    """What the run page is told: never the container's name or the scratch path; a fresh link once it is ready."""
    enabled = preview_switch.enabled()
    if state is None:
        return {"enabled": enabled, "state": "off" if not enabled else "none", "idle_minutes": idle_seconds() // 60}
    now = time.time() if now is None else now
    shown = {
        "enabled": enabled, "state": state.get("state"), "source": state.get("source"), "label": state.get("label"),
        "started_at": state.get("started_at"), "reason": state.get("reason") or None,
        "error": state.get("error") or None, "has_page": state.get("has_page"), "command": state.get("command") or None,
        "idle_minutes": idle_seconds() // 60, "separate_origin": bool(separate_origin()),
    }
    if state.get("state") == "ready":
        expires = int(now) + token_seconds()
        shown["url"] = f"{separate_origin()}{app_prefix(run_id, token_for(run_id, str(state['instance']), expires))}/"
        if enabled:
            pointing = token_for(run_id, str(state["instance"]), expires, pointing=True)
            shown["pick_url"] = f"{separate_origin()}{app_prefix(run_id, pointing)}/"
        shown["expires_at"] = expires
    return shown


# --- the proxy ------------------------------------------------------------------------------------------------------

#: The browser's headers the product is given: what a page's request means, never who is asking or their cookies.
FORWARDED_REQUEST_HEADERS = frozenset({
    "accept", "accept-language", "content-type", "if-none-match", "if-modified-since", "range", "user-agent",
})
#: The product's headers the browser is given; everything else (its cookies included) stays behind.
FORWARDED_RESPONSE_HEADERS = frozenset({
    "content-type", "cache-control", "etag", "last-modified", "content-disposition", "content-language", "expires",
    "location", "content-range", "accept-ranges",
})
#: Bytes of one request body, and of one response, at most.
MOST_REQUEST_BYTES = 2 * 1024 * 1024
MOST_RESPONSE_BYTES = 20 * 1024 * 1024
#: Seconds one proxied request may take.
REQUEST_TIMEOUT = 30.0

_ROOTED_ATTRIBUTE = re.compile(r"""(\s(?:src|href|action|poster|formaction)\s*=\s*["'])/(?![/\\])""", re.I)
_ROOTED_CSS_URL = re.compile(r"""(url\(\s*["']?)/(?![/\\])""", re.I)
_HEAD = re.compile(r"<head[^>]*>", re.I)


def upstream_url(host: str, port: int, path: str, query: str) -> Any:
    """The product's URL for a proxied path: always the preview's own host and port, whatever the path says."""
    import httpx
    from urllib.parse import quote

    clean = "/" + quote(str(path or "").lstrip("/"), safe="/:@!$&'()*+,;=-._~%")
    # No query, no `?`: an empty one was sent as `/styles.css?`, which a product matching its paths exactly misses.
    extra = {"query": query.encode()} if query else {}
    return httpx.URL(scheme="http", host=host, port=int(port), path=clean, **extra)


def forwarded_request_headers(headers: Any) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key.lower() in FORWARDED_REQUEST_HEADERS}


def _rooted_paths_script(prefix: str) -> str:
    """A page's own requests to a path from the root reach the preview, not the app (`fetch('/api/items')`)."""
    return (
        "<script>(function(){var p=" + json.dumps(prefix) + ";function f(u){return typeof u==='string'&&u[0]==='/'"
        "&&u[1]!=='/'&&u.indexOf(p)!==0?p+u:u}var F=window.fetch;if(F){window.fetch=function(i,o){return F.call(this,"
        "typeof i==='string'?f(i):i,o)}}var O=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open=function(m,u)"
        "{arguments[1]=f(u);return O.apply(this,arguments)}})();</script>"
    )


#: Added to a preview's pages only while a person points at the page (plan WS.5, a link signed for pointing): what
#: it does and sends is said in the file it is shipped as.
PICKER_SCRIPT = "<script>" + (Path(__file__).with_name("preview_picker.js")).read_text(encoding="utf-8") + "</script>"


def rewritten(body: bytes, content_type: str, prefix: str, *, pointing: bool = False) -> bytes:
    """A page's and a stylesheet's paths from the root, pointed under the preview's prefix; a page opened by a link
    signed for pointing (and only a page) also carries `PICKER_SCRIPT`."""
    kind = content_type.split(";")[0].strip().lower()
    if kind not in ("text/html", "text/css"):
        return body
    text = body.decode("utf-8", errors="replace")
    text = _ROOTED_CSS_URL.sub(lambda m: m.group(1) + prefix + "/", text)
    if kind == "text/html":
        text = _ROOTED_ATTRIBUTE.sub(lambda m: m.group(1) + prefix + "/", text)
        script = _rooted_paths_script(prefix) + (PICKER_SCRIPT if pointing and preview_switch.enabled() else "")
        head = _HEAD.search(text)
        text = text[:head.end()] + script + text[head.end():] if head else script + text
    return text.encode("utf-8")


def response_headers(upstream: Any, prefix: str) -> dict[str, str]:
    """The product's headers the browser gets, and the ones that keep its page apart from the app."""
    headers: dict[str, str] = {}
    for key, value in upstream.headers.items():
        name = key.lower()
        if name not in FORWARDED_RESPONSE_HEADERS:
            continue
        if name == "location" and value.startswith("/") and not value.startswith("//"):
            value = prefix + value
        headers[name] = value
    sandbox = "sandbox allow-scripts allow-forms allow-popups allow-modals allow-downloads"
    if separate_origin():
        # Its own origin: the page may keep its own storage there, and the app on another origin frames it.
        headers["content-security-policy"] = f"{sandbox} allow-same-origin; frame-ancestors *"
    else:
        # The app's own host: an opaque origin always, so the product's script cannot read the app's storage even
        # when the page is opened outside the frame.
        headers["content-security-policy"] = f"{sandbox}; frame-ancestors 'self'"
        headers["x-frame-options"] = "SAMEORIGIN"
    headers["referrer-policy"] = "no-referrer"
    headers["x-content-type-options"] = "nosniff"
    # The page's origin is opaque, so its own requests here are cross-origin: readable by it, with no credentials.
    headers["access-control-allow-origin"] = "*"
    headers["cross-origin-resource-policy"] = "cross-origin"
    return headers


def preflight_headers() -> dict[str, str]:
    return {
        "access-control-allow-origin": "*",
        "access-control-allow-methods": "GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS",
        "access-control-allow-headers": "content-type, accept, accept-language",
        "access-control-max-age": "600",
    }


__all__ = [
    "ACTIVE", "PICKER_SCRIPT", "PreviewRefused", "app_prefix", "container_name", "forwarded_request_headers",
    "is_for_pointing", "observe",
    "preview_switch", "public", "read", "rewritten", "response_headers", "say_the_worker_serves", "scratch_for",
    "start", "stop", "the_worker_serving", "token_for", "token_problem", "touch", "upstream_url", "what_it_wrote",
]
