"""Does streaming work through the agent path with today's libraries? (Initiative T, a timeboxed spike)

The models module records why streaming is off: with `streaming=True`,
langchain routed a bound model through the non-streaming `_generate`, which was
handed an `openai.Stream` it could not read ("Expected a dict or
openai.BaseModel, got Stream"), and that killed a run on its first call. It
passed with a bare model and failed through `langchain.agents` - so this
reproduces it through `create_agent`, against a local fake OpenAI-compatible
server that streams a tool call and then an answer. No model server is used.

    python scripts/loop/streaming_spike.py            # on the host
    docker compose exec -T worker python - < scripts/loop/streaming_spike.py   # in the worker image

Prints the library versions and PASS or FAIL with the error. Exit 0 on PASS.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version


def _chunks(body: dict) -> list[dict]:
    """The stream the fake server sends: a tool call first, then a plain answer."""
    said_tool = any(m.get("role") == "tool" for m in body.get("messages", []))
    base = {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "fake"}
    if not said_tool:
        return [
            {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "tool_calls": [
                {"index": 0, "id": "call_1", "type": "function", "function": {"name": "echo", "arguments": ""}}]}}]},
            {**base, "choices": [{"index": 0, "delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": "{\"text\": \"hi\"}"}}]}}]},
            {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
        ]
    return [
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": "done: hi"}}]},
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}},
    ]


class _Fake(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if not body.get("stream"):
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "this spike only answers streamed requests"}')
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in _chunks(body):
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


def spike(harness_model: bool = False) -> tuple[bool, str]:
    """(passed, what happened), with langchain's own ChatOpenAI or the harness's subclass of it."""
    from langchain.agents import create_agent
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI

    if harness_model:
        from app.models import CompatibleChatOpenAI as ChatOpenAI  # noqa: N814 - the class under test

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        @tool
        def echo(text: str) -> str:
            """Repeat the text."""
            return text

        model = ChatOpenAI(model="fake", api_key="none", streaming=True,
                           base_url=f"http://127.0.0.1:{server.server_address[1]}/v1", max_retries=0, timeout=20)
        agent = create_agent(model=model, tools=[echo], system_prompt="Use echo, then answer.")
        result = agent.invoke({"messages": [{"role": "user", "content": "say hi"}]})
        last = result["messages"][-1]
        called = any(getattr(m, "type", "") == "tool" for m in result["messages"])
        ok = called and "done: hi" in str(getattr(last, "content", ""))
        return ok, f"tool called: {called}; final answer: {str(getattr(last, 'content', ''))[:80]!r}"
    except Exception as error:  # noqa: BLE001 - the spike reports what broke
        return False, f"{type(error).__name__}: {str(error)[:300]}"
    finally:
        server.shutdown()


if __name__ == "__main__" or __name__ == "<stdin>":
    versions = {name: version(name) for name in ("langchain", "langchain-core", "langchain-openai", "langgraph", "openai")}
    print("versions:", ", ".join(f"{k} {v}" for k, v in versions.items()))
    results = []
    for label, harness in (("langchain ChatOpenAI", False), ("harness CompatibleChatOpenAI", True)):
        passed, said = spike(harness)
        results.append(passed)
        print(("PASS" if passed else "FAIL") + f" streaming through create_agent, {label}: " + said)
    sys.exit(0 if all(results) else 1)
