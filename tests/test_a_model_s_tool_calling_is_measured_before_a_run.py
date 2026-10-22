"""A model's tool calling is measured before a run: being served is not being fit.

A 1-bit build model passed the readiness check and then called tools that
did not exist and repeated one query 27 times.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from app.models import fitness


class _Model:
    def __init__(self, answer):
        self.answer = answer

    def bind_tools(self, tools):
        assert {t["function"]["name"] for t in tools} >= {"read_file", "ls", "grep"}
        return self

    def invoke(self, messages):
        return self.answer(str(messages[-1].content))


def _right(request):
    meant = {"Read": ("read_file", {"file_path": "docs/plan.md"}),
             "List": ("ls", {"path": "src"}),
             "Find": ("grep", {"pattern": "createStore"}),
             "Write": ("write_file", {"file_path": "notes/hi.txt", "content": "hello"}),
             "Run": ("run_terminal_command", {"command": ["npm", "test"], "working_directory": "app"})}
    name, args = meant[request.split()[0]]
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "c"}])


def test_a_model_that_calls_the_right_tools_is_fit():
    result = fitness.probe(_Model(_right))
    assert (result.passed, result.verdict) == (5, "fit")


def test_a_model_that_invents_names_and_shell_strings_is_not():
    def wrong(request):
        if request.startswith("Read"):
            return AIMessage(content="", tool_calls=[{"name": "Read", "args": {"file_path": "docs/plan.md"}, "id": "c"}])
        if request.startswith("Run"):
            return AIMessage(content="", tool_calls=[{"name": "run_terminal_command", "args": {"command": "cd app && npm test"}, "id": "c"}])
        if request.startswith("Find"):
            return AIMessage(content="I would search for it.")
        return _right(request)

    result = fitness.probe(_Model(wrong))
    assert (result.passed, result.verdict) == (2, "unfit")
    assert any("Read(" in miss for miss in result.misses) and any("no tool call" in miss for miss in result.misses)
    assert "quantisation" in result.advice()
