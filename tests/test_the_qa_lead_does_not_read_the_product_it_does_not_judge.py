"""The QA lead reads the suite, the criteria and the documents, never the product's own code (LF.1531).

Measured on a medium run: reviewing a suite written before its sprint was built, the QA lead read the product and
sent the suite back four times for what the code did - "models.py has version = Column(Integer, default=0)" - though
its prompt says never to open the product's files. The run then waited for a person.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from langchain_core.messages import ToolMessage

from app.agents import reads_of_the_product

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
PRODUCT = "task-management-dashboard/task_management_dashboard/models.py"


def _read(middleware, path: str) -> str:
    call = SimpleNamespace(tool_call={"name": "read_file", "id": "r1", "args": {"file_path": path}})
    return str(middleware.wrap_tool_call(call, lambda request: ToolMessage(content="read", tool_call_id="r1")).content)


def test_the_product_s_code_is_not_read():
    said = _read(reads_of_the_product.build_middleware(), PRODUCT)

    assert said.startswith("Not read:") and PRODUCT in said


def test_the_suite_the_criteria_and_the_documents_still_read():
    middleware = reads_of_the_product.build_middleware()
    for path in ("task-management-dashboard/acceptance/tasks.spec.js", "docs/acceptance_criteria.md",
                 "docs/technical_specification.md", "task-management-dashboard/playwright.config.js"):
        assert _read(middleware, path) == "read", path


def test_the_qa_lead_is_built_not_to_read_the_product(monkeypatch):
    from app.agents import acceptance_reviewer

    built = {}
    monkeypatch.setattr(acceptance_reviewer, "create_role_agent", lambda **kwargs: built.update(kwargs))
    acceptance_reviewer.create_acceptance_reviewer_agent(model=None)

    assert built["reads_the_product"] is False


def test_the_refusal_uses_none_of_the_product_words():
    assert not BANNED.search(reads_of_the_product.REFUSED.format(path="app/models.py"))
