"""Fast delivery drafts the product's files first and its unit tests after, each test shown the code it tests.

Drafted in one batch, a unit test was written before the code it tests and guessed its signatures, messages
and storage set-up from the specification: over 18 release-candidate runs, 25 of 31 fixes of failing unit tests
were left open and 7 runs shipped with their own unit tests failing.
"""
import types
from pathlib import Path

from app.graph import drafting

PRODUCT = "notes_api/store.py"
TEST = "tests/test_store.py"


def test_tests_wait_for_the_code_and_are_shown_it(tmp_path, monkeypatch):
    order, shown = [], {}

    def fake_draft(model, root, path, task, specification, stack, diagnostics=None, code_under_test=()):
        order.append(path)
        shown[path] = list(code_under_test)
        return "def save(data_dir, note):\n    return note\n" if path == PRODUCT else "def test_save():\n    assert True\n"

    monkeypatch.setattr(drafting, "_draft_one", fake_draft)
    monkeypatch.setattr(drafting, "_promised_but_not_written", lambda task, written, root: [])
    written = {}
    tasks = [
        types.SimpleNamespace(files=[TEST], task_description="tests", interfaces=[]),
        types.SimpleNamespace(files=[PRODUCT], task_description="store", interfaces=[]),
    ]

    drafting.draft_work_orders(
        tasks, types.SimpleNamespace(), types.SimpleNamespace(), str(tmp_path), object(),
        write=lambda root, path, content: written.__setitem__(path, content), workers=4,
    )

    assert order == [PRODUCT, TEST]
    assert shown[TEST] == [PRODUCT]


def test_a_test_request_is_shown_the_code_it_tests(tmp_path, monkeypatch):
    (tmp_path / "notes_api").mkdir()
    (tmp_path / PRODUCT).write_text("def save(data_dir, note):\n    raise ValueError('Title is required')\n")
    monkeypatch.setattr("app.agents.specialists.specification_for_the_work_order", lambda spec, task: "")
    monkeypatch.setattr("app.agents.shared_facts.the_facts_section", lambda root, built=False: "")
    task = types.SimpleNamespace(files=[TEST], task_description="tests", interfaces=[], acceptance_criteria=[])

    request = drafting.draft_request(tmp_path, TEST, task, None, types.SimpleNamespace(), code_under_test=[PRODUCT])

    assert "Title is required" in request
    assert "already written" in request
