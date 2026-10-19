"""A tool a model calls by a name it learned elsewhere is taken as the offered one it means (Initiative M.5).

Across the stored runs `edit_file` with `path`, `context` and `replacement` was
refused 209 times in four runs as "not a valid tool". Family-typical names are
data in the model registry now, applied only when the tool they mean is offered
and is given everything it requires.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.models import tool_arguments

EDIT = {"type": "function", "function": {"name": "edit_artifact", "parameters": {
    "type": "object", "properties": {"relative_path": {"type": "string"}, "find": {"type": "string"}, "replace": {"type": "string"}},
    "required": ["relative_path", "find", "replace"]}}}
READ = {"type": "function", "function": {"name": "read_file", "parameters": {
    "type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}}}


def _result(call):
    return SimpleNamespace(generations=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call], invalid_tool_calls=[]))])


def test_edit_file_is_taken_as_the_offered_edit(monkeypatch):
    call = {"name": "edit_file", "args": {"path": "app/main.py", "context": "x = 1", "replacement": "x = 2"}, "id": "c1"}
    result = _result(call)

    tool_arguments.decode_structured_arguments(result, [EDIT, READ])

    assert call["name"] == "edit_artifact"
    assert call["args"] == {"relative_path": "app/main.py", "find": "x = 1", "replace": "x = 2"}


def test_it_is_not_taken_when_the_tool_meant_is_not_offered_or_not_fully_given():
    absent = {"name": "edit_file", "args": {"path": "a", "context": "x", "replacement": "y"}, "id": "c2"}
    tool_arguments.decode_structured_arguments(_result(absent), [READ])
    assert absent["name"] == "edit_file"

    partial = {"name": "edit_file", "args": {"context": "x", "replacement": "y"}, "id": "c3"}
    tool_arguments.decode_structured_arguments(_result(partial), [EDIT])
    assert partial["name"] == "edit_file"


def test_a_failed_fitness_probe_names_the_server_setting_the_family_needs():
    from app.models.fitness import Fitness

    said = Fitness(passed=2, total=5).advice("unsloth/Qwen3.6-35B-A3B-MTP-GGUF")

    assert "hermes" in said and "--jinja" in said and "--tool-call-parser" in said
    assert Fitness(passed=5, total=5).advice("unsloth/Qwen3.6-35B-A3B-MTP-GGUF") == "fit for every stage"
    assert "--jinja" not in Fitness(passed=2, total=5).advice("some-unknown-model")
