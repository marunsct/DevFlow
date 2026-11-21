"""A library's contract lines are calls, so the unread-lines finding is not raised for one.

Measured on one library run: ten lines written `AC-1 command textkit.slugify('Hello, World!') -> 'hello-world'` were
reported as following none of the contract's forms (a request, a page control, a command line), the escalation left the
major finding open, and no rewrite the finding asks for exists for a library.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import workflow
from app.switches import is_on


def _state(kind: str):
    spec = SimpleNamespace(interface_contract=["AC-1 command textkit.slugify('Hello, World!') -> 'hello-world'",
                                               "AC-2 command textkit.word_count('a b c') -> 3"])
    stack = SimpleNamespace(language="Python", framework="", frontend_framework="", database="",
                            testing_framework="pytest", additional_tools=[], product_kind=kind)
    # The key the workflow's state really carries: the selector's output, holding the stack.
    return {"technical_specification": spec, "stack_selection": SimpleNamespace(technology_stack=stack),
            "architecture_revision_count": 0}


def test_a_library_raises_no_finding(monkeypatch):
    monkeypatch.setenv("CONTRACT_UNREAD_LINES_AT_REVIEW", "on")

    assert workflow._contract_lines_nothing_can_read(_state("library")) is None


def test_a_service_with_the_same_lines_still_raises_it(monkeypatch):
    monkeypatch.setenv("CONTRACT_UNREAD_LINES_AT_REVIEW", "on")

    found = workflow._contract_lines_nothing_can_read(_state("http_api"))

    assert found is not None and "follow none of its forms" in found.description
