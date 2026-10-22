"""The specification is written down to the detail a faster model builds from without guessing.

On the owner's two tiers a frontier model writes the specification and a
faster local one builds from it. The specification now carries every file,
function contract, data shape, error, build step, test and setting; the
document renders them, the technical lead copies from them, and each work
order is handed the entries about its own files and names.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from app.agents import principal_architect
from app.agents.principal_architect import TechnicalSpecificationOutput
from app.agents.specialists import build_specialist_task_request, specification_for_the_work_order

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
DETAIL = ("file_plan", "function_contracts", "data_contracts", "error_catalogue",
          "implementation_order", "test_cases", "configuration")


def _spec() -> TechnicalSpecificationOutput:
    return TechnicalSpecificationOutput(
        product_scope="Notes.",
        file_plan=["notes/store.py - keeps notes; exports add_note(title: str) -> Note", "notes/page.html - the page"],
        function_contracts=["notes/store.py add_note(title: str) -> Note: rejects an empty title with ValueError('title is required')"],
        data_contracts=["Note: {id: int, title: str (1-80 chars)}; example {\"id\": 1, \"title\": \"Milk\"}"],
        error_catalogue=["Empty title: add_note raises ValueError('title is required'); nothing is stored"],
        implementation_order=["1. notes/store.py: add_note; check: pytest tests/test_store.py"],
        test_cases=["AC-1 test_ac1_adds_a_note: add_note('Milk') returns id 1"],
        configuration=["DATA_DIR - where notes are kept; default ./data"],
    )


def test_the_schema_carries_every_detail_section():
    assert set(DETAIL) <= set(TechnicalSpecificationOutput.model_fields)


def test_the_architect_is_asked_for_the_smallest_detail_and_the_prompt_names_no_product():
    prompt = principal_architect._SYSTEM_PROMPT
    assert "smallest detail" in prompt and "must not have to guess" in prompt
    for field in DETAIL:
        assert f"`{field}`" in prompt
        assert not BANNED.search(TechnicalSpecificationOutput.model_fields[field].description)
    rule = prompt[prompt.index("- Write the specification down to the smallest detail"):prompt.index("{SCOPE")] if "{SCOPE" in prompt else prompt
    assert not BANNED.search(rule.split("Constraints:")[0][-900:])


def test_the_document_renders_the_detail():
    from app.agents.specification_document import _SECTIONS

    headings = dict(_SECTIONS)
    for field in DETAIL:
        assert field in headings


def test_a_work_order_is_handed_the_entries_about_its_files_and_names():
    order = SimpleNamespace(files=["notes/store.py"], interfaces=["add_note(title: str) -> Note"])

    detail = specification_for_the_work_order(_spec(), order)

    assert "build exactly to it" in detail
    assert "rejects an empty title with ValueError('title is required')" in detail
    assert "1. notes/store.py: add_note" in detail
    assert "notes/page.html" not in detail, "only this work order's entries"
    assert not BANNED.search(detail.split("\n", 2)[1])


def test_a_work_order_with_nothing_in_the_specification_gets_only_the_api():
    # Every work order is handed the product's API (`app.acceptance.api_reference`);
    # one whose files the specification never names gets no file entries besides.
    given = specification_for_the_work_order(_spec(), SimpleNamespace(files=["other/x.go"], interfaces=[]))
    assert "The specification for your files" not in given
    assert specification_for_the_work_order(None, SimpleNamespace(files=["a.py"], interfaces=[])) == ""


def test_the_builder_s_request_carries_it(tmp_path):
    request = build_specialist_task_request(
        "Build the store", ["works"], str(tmp_path), specification_detail="--- The specification for your files: X ---\n",
    )

    assert "--- The specification for your files: X ---" in request["messages"][0]["content"]


def test_the_technical_lead_copies_from_the_detail():
    from app.agents.technical_lead import _the_contracts

    contracts = _the_contracts(_spec())
    assert "Function contracts:" in contracts and "ValueError('title is required')" in contracts
