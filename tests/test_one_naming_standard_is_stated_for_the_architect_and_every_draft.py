"""One naming standard per language, in the specification's request and in every draft's, and an empty names section is asked for again.

Measured over one night with a small model: files importing names their modules did not define (`create_access_token`
for `create_token`, `createApp` for `app`), and a specification whose Function Contracts section was "Not specified".
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.graph import drafting, specification_parts
from app.stacks import naming

BANNED = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("NAMING_STANDARD", "on")


def _stack(language, framework=""):
    return SimpleNamespace(language=language, framework=framework, frontend_framework="", testing_framework="")


def test_a_language_gets_its_own_conventions_and_the_one_name_rule():
    text = naming.standard_for(_stack("Python", "FastAPI"))
    assert "snake_case" in text and "PascalCase" in text and naming.ONE_NAME in text

    ts = naming.standard_for(_stack("TypeScript", "Hono"))
    assert "camelCase" in ts and "snake_case" not in ts.split("One concept")[0]


def test_an_unknown_language_or_the_switch_off_gives_nothing(monkeypatch):
    assert naming.standard_for(_stack("Brainfuck")) == ""
    monkeypatch.setenv("NAMING_STANDARD", "off")
    assert naming.standard_for(_stack("Python", "FastAPI")) == ""


def test_the_rule_uses_none_of_the_banned_words():
    assert not BANNED.search(naming.ONE_NAME)
    assert not any(BANNED.search(rule) for rule in naming.CONVENTIONS.values())


def test_a_draft_is_asked_in_the_standard(tmp_path):
    task = SimpleNamespace(files=["src/app.ts"], interfaces=[], task_description="build the app", acceptance_criteria=[])
    spec = SimpleNamespace(file_plan=["src/app.ts - the app"], function_contracts=[], data_contracts=[])
    monkey_request = drafting.draft_request

    request = monkey_request(Path(tmp_path), "src/app.ts", task, spec, _stack("TypeScript", "Hono"))

    assert "--- Naming ---" in request and "camelCase" in request


def _a_spec_where_the_first_reply_lacks_function_contracts(monkeypatch):
    import json

    from pydantic import BaseModel

    class Spec(BaseModel):
        file_plan: list[str] = []
        function_contracts: list[str] = []
        domain_model: list[str] = []

    class _Model:
        def __init__(self):
            self.asked = []

        def invoke(self, messages, **kwargs):
            wanted = messages[-1].content.split("Its keys are exactly:")[-1]
            names = [n for n in ("function_contracts", "domain_model") if n in wanted]
            self.asked.append(names)
            body = {n: ["x"] for n in names}
            if len(self.asked) == 1:
                body.pop("function_contracts", None)
            return SimpleNamespace(content=json.dumps(body))

    monkeypatch.setattr(specification_parts, "PARTS", (("domain_model", "function_contracts"),))
    monkeypatch.setattr("app.agents.thinking.without_reasoning", lambda model: model)
    return Spec, _Model()


def test_an_empty_names_section_is_asked_for_again(monkeypatch):
    Spec, model = _a_spec_where_the_first_reply_lacks_function_contracts(monkeypatch)

    written = specification_parts.with_the_parts_written(Spec(), model, "")

    assert written.function_contracts == ["x"] and written.domain_model == ["x"]
    assert model.asked == [["function_contracts", "domain_model"], ["function_contracts"]]


def test_with_the_switch_off_it_is_asked_once(monkeypatch):
    monkeypatch.setenv("NAMING_STANDARD", "off")
    Spec, model = _a_spec_where_the_first_reply_lacks_function_contracts(monkeypatch)

    written = specification_parts.with_the_parts_written(Spec(), model, "")

    assert written.function_contracts == [] and len(model.asked) == 1


def test_only_the_sections_that_fix_names_are_asked_for_again():
    assert {"function_contracts", "error_catalogue", "implementation_order"} == set(specification_parts.NAMING_SECTIONS)
    assert "domain_model" not in specification_parts.NAMING_SECTIONS


def test_the_architect_s_request_carries_the_standard():
    source = (Path(__file__).resolve().parent.parent / "src" / "app" / "graph" / "workflow.py").read_text()
    assert "naming = standard_for(" in source
