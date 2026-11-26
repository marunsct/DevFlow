"""The product preview's proxy (plan WS.4; UX.9 and UX.10): a page's requests and its WebSocket upgrades, relayed to
the preview's own host and port under one link check (`preview.opening_problem`).

A page or a stylesheet is read whole (at most `preview.MOST_RESPONSE_BYTES`) so its paths from the root can be pointed
under the link; everything else is relayed as it arrives, so an event stream or a long download reaches the browser
before the product has finished it. A WebSocket upgrade is relayed both ways, with the subprotocol the product chose
(a development server's hot reload names one). Every relayed chunk or message counts as use for the idle clock, at
most once every few seconds. On a separate preview origin the product's cookies pass both ways
(`preview.passed_cookies`); on the app's own host none ever does.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

from fastapi import Request, WebSocket
from fastapi.responses import Response, StreamingResponse

from app.server import preview

logger = logging.getLogger(__name__)

#: Seconds between two writes of a preview's last use while a stream or a socket is busy.
_TOUCH_SECONDS = 5.0


class _UseClock:
    """Says a preview is in use, at most every `_TOUCH_SECONDS`, from a relay that may pass many chunks a second."""

    def __init__(self, state: dict[str, Any]) -> None:
        self.state: dict[str, Any] = state
        self.last: float | None = None

    async def tick(self) -> None:
        if self.last is not None and time.monotonic() - self.last < _TOUCH_SECONDS:
            return
        # The first tick is the request's own (held by `touch` to one write every few seconds, as before); a later
        # one is a stream or a socket still busy, so it is written.
        state = self.state if self.last is None else {**self.state, "last_used": 0}
        self.last = time.monotonic()
        try:
            await asyncio.to_thread(preview.touch, state)
        except Exception:  # noqa: BLE001 - Redis away for a moment: the next chunk says it again
            logger.debug("Could not record a preview's use", exc_info=True)


def _plain(text: str, status: int, **headers: str) -> Response:
    return Response(text, status_code=status, media_type="text/plain", headers=headers or None)


async def serve(run_id: str, token: str, path: str, request: Request) -> Response:
    """One request of the page, answered by the product."""
    import httpx

    state = await asyncio.to_thread(preview.read, run_id)
    problem = preview.opening_problem(state, run_id, token, request.headers.get("host", ""))
    if problem:
        return _plain(problem, 403, **{"cache-control": "no-store"})
    assert state is not None
    if request.method == "OPTIONS" and "access-control-request-method" in request.headers:
        return Response(status_code=204, headers=preview.preflight_headers())
    if state.get("state") != "ready":
        return _plain("The preview is still starting.", 503, **{"retry-after": "2"})
    body = await request.body()
    if len(body) > preview.MOST_REQUEST_BYTES:
        return _plain("The request is too large for a preview.", 413)
    prefix = preview.app_prefix(run_id, token)
    target = preview.upstream_url(str(state["host"]), int(state["port"]), path, request.url.query)
    # No read limit on the client: a stream may be quiet for a while. The answer's head, and a page read whole, are
    # each held to `REQUEST_TIMEOUT` below.
    client = httpx.AsyncClient(timeout=httpx.Timeout(preview.REQUEST_TIMEOUT, read=None), follow_redirects=False,
                               trust_env=False)
    try:
        outgoing = client.build_request(request.method, target, content=body or None,
                                        headers=preview.forwarded_request_headers(request.headers, run_id))
        upstream = await asyncio.wait_for(client.send(outgoing, stream=True), preview.REQUEST_TIMEOUT)
    except (httpx.HTTPError, asyncio.TimeoutError) as error:
        await client.aclose()
        return _plain(f"The product did not answer: {type(error).__name__}.", 502)
    clock = _UseClock(state)
    await clock.tick()
    headers = preview.response_headers(upstream, prefix)
    cookies = preview.passed_cookies(upstream, run_id)
    if preview.is_streamed(headers.get("content-type", "")):
        response: Response = StreamingResponse(_relayed(upstream, client, clock), status_code=upstream.status_code,
                                               headers=headers)
    else:
        try:
            content = await asyncio.wait_for(_whole(upstream), preview.REQUEST_TIMEOUT)
        except (httpx.HTTPError, asyncio.TimeoutError) as error:
            return _plain(f"The product did not answer: {type(error).__name__}.", 502)
        finally:
            await upstream.aclose()
            await client.aclose()
        if content is None:
            return _plain("The product's answer is too large for a preview.", 502)
        content = preview.rewritten(content, headers.get("content-type", ""), prefix,
                                    pointing=preview.is_for_pointing(token))
        response = Response(content=content, status_code=upstream.status_code, headers=headers)
    for cookie in cookies:
        response.headers.append("set-cookie", cookie)
    return response


async def _whole(upstream: Any) -> bytes | None:
    """The answer read whole, or None past `MOST_RESPONSE_BYTES`."""
    content = b""
    async for chunk in upstream.aiter_bytes():
        content += chunk
        if len(content) > preview.MOST_RESPONSE_BYTES:
            return None
    return content


async def _relayed(upstream: Any, client: Any, clock: _UseClock) -> AsyncIterator[bytes]:
    """The answer chunk by chunk as the product sends it; the product's connection is closed however it ends."""
    import httpx

    try:
        async for chunk in upstream.aiter_bytes():
            await clock.tick()
            yield chunk
    except httpx.HTTPError:
        logger.debug("A preview's stream ended early", exc_info=True)
    finally:
        await upstream.aclose()
        await client.aclose()


async def relay_socket(websocket: WebSocket, run_id: str, token: str, path: str) -> None:
    """A WebSocket upgrade of the page, relayed to the product both ways; refused (closed before it is accepted, which
    the browser sees as a 403) when the link does not open a ready preview."""
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed, WebSocketException

    state = await asyncio.to_thread(preview.read, run_id)
    problem = preview.opening_problem(state, run_id, token, websocket.headers.get("host", ""))
    if problem or (state or {}).get("state") != "ready":
        await websocket.close(code=1008)
        return
    assert state is not None
    target = preview.socket_url(str(state["host"]), int(state["port"]), path, websocket.url.query)
    sent = {k: v for k, v in websocket.headers.items() if k.lower() in preview.FORWARDED_SOCKET_HEADERS}
    sent.update({k: v for k, v in preview.forwarded_request_headers(websocket.headers, run_id).items()
                 if k.lower() == "cookie"})
    wanted = [p for p in websocket.scope.get("subprotocols") or [] if p]
    try:
        upstream = await connect(target, subprotocols=wanted or None, additional_headers=sent,  # type: ignore[arg-type]
                                 open_timeout=preview.REQUEST_TIMEOUT, max_size=preview.MOST_RESPONSE_BYTES,
                                 proxy=None)
    except (OSError, WebSocketException, asyncio.TimeoutError):
        await websocket.close(code=1011)
        return
    clock = _UseClock(state)
    await websocket.accept(subprotocol=upstream.subprotocol)

    async def to_the_product() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            await clock.tick()
            await upstream.send(message["text"] if message.get("text") is not None else message.get("bytes") or b"")

    async def to_the_page() -> None:
        async for message in upstream:
            await clock.tick()
            if isinstance(message, str):
                await websocket.send_text(message)
            else:
                await websocket.send_bytes(message)

    both = [asyncio.create_task(to_the_product()), asyncio.create_task(to_the_page())]
    try:
        await asyncio.wait(both, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for relay in both:
            relay.cancel()
        await asyncio.gather(*both, return_exceptions=True)
        code = upstream.close_code or 1000
        try:
            await upstream.close()
        except (ConnectionClosed, OSError):
            pass
        try:
            await websocket.close(code=code if code in (1000, 1001) or 3000 <= code < 5000 else 1000)
        except RuntimeError:  # the page closed it first
            pass


__all__ = ["relay_socket", "serve"]
