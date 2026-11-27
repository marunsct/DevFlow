"""Model servers for the diagnosis tests: each answers the diagnosis's own requests as a model would.

`StageChecks` answers the deep diagnosis's checks (`app.models.deep_diagnosis.CHECKS`), passing or failing each try as
its `plan` says - a function of the guidance lines the request carries and the try's number - or raising what the
plan raises (a server error). `ToolChecks` answers the tool and reasoning diagnosis's requests (`diagnostics`) the way
a model that does as asked would. Both are thread-safe: the diagnosis asks side by side.
"""
from __future__ import annotations

import json
import threading
from collections import defaultdict
from types import SimpleNamespace
from typing import Any, Callable


def completion(content: str = "", calls: list | None = None, finish: str = "stop", reasoning: str = "",
               tokens: int = 10) -> dict:
    message: dict[str, Any] = {"content": content, "tool_calls": calls}
    if reasoning:
        message["reasoning_content"] = reasoning
    return {"choices": [{"finish_reason": finish, "message": message}], "usage": {"completion_tokens": tokens}}


def call(name: str, arguments: dict) -> list[dict]:
    return [{"id": "c9", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]


def model(server: Any, name: str = "a-model.gguf", base: str = "http://model-server:2001/v1") -> SimpleNamespace:
    return SimpleNamespace(model_name=name, openai_api_base=base,
                           root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)))


def _text(message: dict) -> str:
    content = message.get("content")
    return content if isinstance(content, str) else json.dumps(content)


def check_of(payload: dict) -> str:
    """Which deep-diagnosis check a request is, by what it asks."""
    messages = payload["messages"]
    last = messages[-1]
    users = [_text(m) for m in messages if m.get("role") == "user"]
    asked = users[-1] if users else ""
    names = [t["function"]["name"] for t in payload.get("tools") or []]
    if "Plan two sprints" in asked:
        return "a plan answered in its schema"
    if "Plan the sprints and give your plan" in asked:
        return "an answer within a stage's reply"
    if asked == "Give your answer now.":
        return "the answer as a call, not as text"
    if "List 40 different test case titles" in asked:
        return "a long list without repeating itself"
    if "Do what your role does about it." in asked:
        return "a role kept"
    if last.get("role") == "tool" and "is not permitted here" in _text(last):
        return "a refusal heeded"
    if last.get("role") == "tool" and "SpecialistOutput" in names and "5 passed" in _text(last):
        return "stopping when its tests pass"
    if "Write the acceptance test for creating an item" in asked:
        return "a role kept while building"
    if "Create the file orders-svc/notes.txt" in asked:
        return "exact argument names"
    if "List the files in orders-svc" in asked:
        return "one program a command"
    if "Read the project's app.py" in asked:
        return "paths as given"
    if "What does handler_7 return?" in "".join(users):
        return "the rule repeated at the end" if asked.startswith("Answer every request") else \
            "a rule kept after a long request"
    raise AssertionError(f"not a deep-diagnosis request: {asked[:80]!r}")


_PASS: dict[str, Callable[[], dict]] = {
    "a plan answered in its schema": lambda: completion(calls=call(
        "SprintPlanOutput", {"sprints": [{"goal": "Sign up and sign in", "user_value": "a person has an account"}]})),
    "an answer within a stage's reply": lambda: completion(calls=call(
        "SprintPlanOutput", {"sprints": [{"goal": "Sign up and sign in", "user_value": "a person has an account"}]})),
    "the answer as a call, not as text": lambda: completion(calls=call("SpecialistOutput", {"changed_files": []})),
    "a long list without repeating itself": lambda: completion("\n".join(f"case {n}" for n in range(40))),
    "a role kept": lambda: completion("The fault is in app/routes.py, which another role builds."),
    "a refusal heeded": lambda: completion(calls=call(
        "edit_artifact", {"relative_path": "orders-svc/app.py", "find": "200", "replace": "201"})),
    "stopping when its tests pass": lambda: completion(calls=call("SpecialistOutput", {"changed_files": []})),
    "a role kept while building": lambda: completion(calls=call(
        "write_artifact", {"relative_path": "orders-svc/acceptance/test_items.py", "content": "def test(): ..."})),
    "exact argument names": lambda: completion(calls=call(
        "write_artifact", {"relative_path": "orders-svc/notes.txt", "content": "hello"})),
    "one program a command": lambda: completion(calls=call("run_terminal_command", {"command": ["ls", "orders-svc"]})),
    "paths as given": lambda: completion(calls=call("read_file", {"file_path": "orders-svc/app.py"})),
    "a rule kept after a long request": lambda: completion(calls=call("give_answer", {"value": "{'value': 7}, 200"})),
    "the rule repeated at the end": lambda: completion(calls=call("give_answer", {"value": "{'value': 7}, 200"})),
}
#: Failing replies, in the shapes the kept diagnoses recorded.
_FAIL: dict[str, Callable[[], dict]] = {
    "a plan answered in its schema": lambda: completion(calls=call("SprintPlanOutput", {"sprints": "two sprints"})),
    "an answer within a stage's reply": lambda: completion("thinking " * 50, finish="length"),
    "the answer as a call, not as text": lambda: completion(calls=call("run_terminal_command", {"command": ["pytest"]})),
    "a long list without repeating itself": lambda: completion("case - " * 2_000, finish="length"),
    "a role kept": lambda: completion(calls=call("write_artifact", {"relative_path": "app/routes.py", "content": "201"})),
    "a refusal heeded": lambda: completion(calls=call("run_terminal_command", {"command": ["cat", "orders-svc/app.py"]})),
    "stopping when its tests pass": lambda: completion(calls=call("run_terminal_command", {"command": ["pytest"]})),
    "a role kept while building": lambda: completion(calls=call(
        "write_artifact", {"relative_path": "tasks_api/models.py", "content": "class Item: ..."})),
    "exact argument names": lambda: completion("I would create the file."),
    "one program a command": lambda: completion(calls=call(
        "run_terminal_command", {"command": ["ls orders-svc && head -n 20 orders-svc/app.py"]})),
    "paths as given": lambda: completion(calls=call("read_file", {"file_path": "/workspace/app.py"})),
    "a rule kept after a long request": lambda: completion("It returns {'value': 7}, 200."),
    "the rule repeated at the end": lambda: completion("It returns {'value': 7}, 200."),
}


class StageChecks:
    """Answers the deep diagnosis. `plan[check](system, n)` -> True (pass), False (fail), or an exception to raise;
    a check not in the plan passes. `n` counts that check's tries under that system message from 0."""

    def __init__(self, plan: dict[str, Callable[[str, int], Any]] | None = None):
        self.plan = plan or {}
        self.asked: list[str] = []
        self._tries: dict[tuple[str, str], int] = defaultdict(int)
        self._lock = threading.Lock()

    def create(self, **payload: Any) -> dict:
        name = check_of(payload)
        system = _text(payload["messages"][0])
        with self._lock:
            n = self._tries[(name, system)]
            self._tries[(name, system)] += 1
            self.asked.append(name)
        outcome = self.plan.get(name, lambda _system, _n: True)(system, n)
        if isinstance(outcome, BaseException):
            raise outcome
        return (_PASS if outcome else _FAIL)[name]()


def told(system: str, guide_id: str) -> bool:
    """Whether a request's system message carries the guide's line."""
    from app.models.guidance import BY_ID

    return BY_ID[guide_id].line in system


class Everything:
    """The deep diagnosis's requests to `stage` (a `StageChecks`), every other request to `tools` (a `ToolChecks`)."""

    def __init__(self, stage: Any = None, tools: Any = None):
        self.stage, self.tools = stage or StageChecks(), tools or ToolChecks()

    def create(self, **payload: Any) -> dict:
        try:
            check_of(payload)
        except (AssertionError, KeyError, IndexError):
            return self.tools.create(**payload)
        return self.stage.create(**payload)


class Balanced:
    """`server`'s answers from `servers` model servers of `slots` slots each behind a balancer that keeps a session on
    the server its first request went to and sends a new session to the least busy one (the first on a tie). Each
    request holds its slot `seconds`; every reply says the server generated at `rate` tokens a second (llama.cpp's
    `timings`)."""

    def __init__(self, server: Any, servers: int = 2, slots: int = 1, seconds: float = 0.03, rate: float = 60.0,
                 header: str = "X-Olla-Session-ID"):
        self.server, self.seconds, self.rate, self.header = server, seconds, rate, header
        self.load = [0] * servers
        self.where: dict[str, int] = {}
        self.slots = [threading.Semaphore(slots) for _ in range(servers)]
        self._lock = threading.Lock()

    def create(self, **payload: Any) -> dict:
        import time

        session = (payload.get("extra_headers") or {}).get(self.header)
        with self._lock:
            if session in self.where:
                chosen = self.where[session]
            else:
                chosen = min(range(len(self.load)), key=lambda n: (self.load[n], n))
                if session:
                    self.where[session] = chosen
            self.load[chosen] += 1
        try:
            with self.slots[chosen]:
                time.sleep(self.seconds)
            reply = self.server.create(**payload)
        finally:
            with self._lock:
                self.load[chosen] -= 1
        return {**reply, "timings": {"predicted_per_second": self.rate, "prompt_ms": 50.0}}


class Overlapping:
    """`server` answering after `hold` seconds a request, counting how many requests it held at once at most and the
    session header each carried."""

    def __init__(self, server: Any, hold: float = 0.03, header: str = "X-Olla-Session-ID"):
        self.server, self.hold, self.header = server, hold, header
        self.now = self.most = 0
        self.sessions: list[str | None] = []
        self._lock = threading.Lock()

    def create(self, **payload: Any) -> dict:
        import time

        with self._lock:
            self.now += 1
            self.most = max(self.most, self.now)
            self.sessions.append((payload.get("extra_headers") or {}).get(self.header))
        try:
            time.sleep(self.hold)
            return self.server.create(**payload)
        finally:
            with self._lock:
                self.now -= 1


class ToolChecks:
    """Answers the tool and reasoning diagnosis as a model that does as asked; `fail(payload)` may return an
    exception to raise for a request instead."""

    def __init__(self, fail: Callable[[dict], BaseException | None] | None = None):
        self.fail = fail or (lambda payload: None)
        self.sent: list[dict] = []
        self._lock = threading.Lock()

    def create(self, **payload: Any) -> dict:
        with self._lock:
            self.sent.append(payload)
        error = self.fail(payload)
        if error is not None:
            raise error
        tools = [t["function"]["name"] for t in payload.get("tools") or []]
        asked = _text(payload["messages"][-1])
        choice = payload.get("tool_choice")
        if isinstance(choice, dict):
            named = choice["function"]["name"]
            if named == "read_file":
                return completion(calls=call("read_file", {"file_path": "app/main.py"}))
            if named == "get_weather":
                return completion(calls=call("get_weather", {"city": "Paris"}))
        if "SpecialistOutput" in tools:
            return completion(calls=call("SpecialistOutput", {"changed_files": ["app/routes.py"]}))
        if "Paris and in Tokyo" in asked:
            return completion(calls=call("get_weather", {"city": "Paris"}) + call("get_weather", {"city": "Tokyo"}))
        if "write_artifact" in tools and len(tools) == 2:
            return completion(calls=call("write_artifact", {"relative_path": "notes.txt", "content": "This is a final."}))
        if "glob" in tools:
            return completion(calls=call("read_file", {"file_path": "app/main.py"}))
        if tools:
            return completion(calls=call(tools[0], {"city": "Paris"}))
        if "release code" in asked:
            return completion("K7-QX-42")
        if "digits of every whole number" in asked:
            return completion("330", reasoning="x" * 400, tokens=110)
        return completion("18", reasoning="x" * 400, tokens=110)
