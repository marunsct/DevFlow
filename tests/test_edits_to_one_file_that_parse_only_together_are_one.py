"""A reply's edits to one file that parse only together become one edit; anything else goes as it was sent.

Measured over 80 runs: 18 had replies whose several edits to one file each left it unparseable alone, and every one
was refused (54 edits in 23 bursts; 8 in one reply). The combined edit still passes the parse check like any other.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage

from app.agents import edits_together as et

SOURCE = "def fetch(url):\n    return url\n\n\nresult = fetch('x')\n"


def _reply(*edits):
    return AIMessage(content="", tool_calls=[
        {"name": "edit_artifact", "id": f"c{i}", "args": {"relative_path": "app/m.py", "find": f, "replace": r}}
        for i, (f, r) in enumerate(edits)
    ] + [{"name": "read_file", "id": "r", "args": {"file_path": "app/other.py"}}])


def _root(tmp_path, text=SOURCE):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "m.py").write_text(text)
    return tmp_path


def test_edits_that_parse_only_together_become_one(tmp_path):
    # Opening a block in one edit and closing it in the next: neither parses alone.
    reply = _reply(("def fetch(url):\n    return url\n", "def fetch(url):\n    try:\n        return url\n"),
                   ("\n\nresult", "    except ValueError:\n        return None\n\n\nresult"))
    merged = et.together(reply, _root(tmp_path))
    assert merged is not None
    edits = [c for c in merged.tool_calls if c["name"] == "edit_artifact"]
    assert len(edits) == 1 and edits[0]["id"] == "c0"
    assert edits[0]["args"]["find"] == SOURCE
    compile(edits[0]["args"]["replace"], "m.py", "exec")
    assert "except ValueError" in edits[0]["args"]["replace"]
    assert [c["name"] for c in merged.tool_calls] == ["edit_artifact", "read_file"], "other calls are kept"


def test_edits_that_each_parse_alone_go_as_sent(tmp_path):
    reply = _reply(("return url", "return url.strip()"), ("fetch('x')", "fetch('y')"))
    assert et.together(reply, _root(tmp_path)) is None


def test_edits_that_do_not_parse_together_are_left_to_be_refused(tmp_path):
    reply = _reply(("def fetch(url):\n    return url\n", "def fetch(url):\n    try:\n        return url\n"),
                   ("fetch('x')", "fetch('y'"))
    assert et.together(reply, _root(tmp_path)) is None


def test_a_file_already_broken_is_not_touched(tmp_path):
    reply = _reply(("return url", "return url +"), ("fetch('x')", "fetch("))
    assert et.together(reply, _root(tmp_path, "def fetch(url:\n    return url\n")) is None


def test_every_role_agent_has_it():
    import inspect

    from app.agents import role_agent

    assert "build_edits_together_middleware(resolved_repo_root)" in inspect.getsource(role_agent)


# Measured on one run: an intake reply ran to its output cap as 1,316 tool calls, 1,314 of them `read_file("/")`, each
# run and answered, and the next request carried every answer.
def test_a_call_repeated_within_one_reply_is_run_once(tmp_path):
    reply = AIMessage(content="", id="m1", tool_calls=[
        {"name": "read_file", "id": f"r{i}", "args": {"file_path": "/"}} for i in range(50)
    ] + [{"name": "ls", "id": "l", "args": {"path": "/"}}, {"name": "read_file", "id": "r-x", "args": {"file_path": "/a"}}])
    once = et.one_of_each(reply)
    assert [c["id"] for c in once.tool_calls] == ["r0", "l", "r-x"]
    assert et.one_of_each(once) is None, "nothing repeats: the reply goes as sent"


def test_the_middleware_runs_it_before_combining_edits(tmp_path):
    middleware = et.build_edits_together_middleware(_root(tmp_path))
    reply = AIMessage(content="", id="m2", tool_calls=[
        {"name": "read_file", "id": f"r{i}", "args": {"file_path": "app/m.py"}} for i in range(3)])
    update = middleware.after_model({"messages": [reply]})
    assert [c["id"] for c in update["messages"][0].tool_calls] == ["r0"]
