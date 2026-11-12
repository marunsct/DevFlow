"""A page that never draws records the way the brief shows them has work left, whatever a lenient suite says.

Measured on one run: the brief said each bookmark is an item of a list, the page drew plain containers, the suite
found them by a class, and the finding that said so was still open when the suite locked at its round cap. The sprint
was closed with no new work, the release said every criterion passed, and 5 of 8 hidden tests failed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.graph import acceptance_nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
BRIEF = "Each bookmark is an item of a list showing its title as a link.\n"
DIVS = "const item = document.createElement('div');\nitem.className = 'bm-item';\nlist.appendChild(item);\n"


def _product(root: Path, script: str, page: str = "<div id='bookmark-list'></div>") -> Path:
    project = root / "app"
    (project / "acceptance").mkdir(parents=True)
    (project / "acceptance" / "run.json").write_text(json.dumps({"command": ["run"], "report": "r.xml"}))
    (project / "acceptance" / "ui.spec.js").write_text("const li = '<li>';\n")  # the suite's own text is not the page
    (project / "index.html").write_text(f"<html><body>{page}<script src='app.js'></script></body></html>")
    (project / "app.js").write_text(script)
    (root / ".project-directory").write_text("app\n")
    return project


def test_a_page_of_plain_containers_is_named(tmp_path):
    _product(tmp_path, DIVS)
    [found] = suite.records_the_page_never_makes(tmp_path, BRIEF)
    assert "item of a list" in found and "`listitem`" in found
    assert not BANNED.search(found)


@pytest.mark.parametrize("script,page", [
    ("const item = document.createElement('li');\n", "<ul id='list'></ul>"),
    (DIVS, "<ul><li>first</li></ul>"),
    ("return <li key={b.id}>{b.title}</li>;\n", "<div id='root'></div>"),
    ("el.innerHTML = '<div role=\"listitem\">';\n", "<div></div>"),
])
def test_a_page_that_makes_list_items_is_left_alone(tmp_path, script, page):
    _product(tmp_path, script, page)
    assert suite.records_the_page_never_makes(tmp_path, BRIEF) == []


def test_a_brief_that_names_no_kind_or_a_product_with_no_page_says_nothing(tmp_path):
    project = _product(tmp_path, DIVS)
    assert suite.records_the_page_never_makes(tmp_path, "Bookmarks are saved and listed.") == []
    (project / "index.html").unlink()
    assert suite.records_the_page_never_makes(tmp_path, BRIEF) == []


def _state(root: Path) -> dict:
    return {"repository": SimpleNamespace(root_path=str(root)), "document": SimpleNamespace(text=BRIEF)}


def test_a_round_raises_it_and_does_not_raise_it_twice(tmp_path, monkeypatch):
    _product(tmp_path, DIVS)
    monkeypatch.setattr(acceptance_nodes, "_root", lambda state: tmp_path)
    monkeypatch.setattr(acceptance_nodes, "_owner_for", lambda state, text: "ui_ux")
    [defect] = acceptance_nodes._records_the_page_never_makes(_state(tmp_path), [])
    assert defect.description.startswith(acceptance_nodes.RECORDS_NOT_AS_THE_BRIEF_SHOWS)
    assert defect.severity == "blocking" and not BANNED.search(defect.description)
    assert acceptance_nodes._records_the_page_never_makes(_state(tmp_path), [defect]) == []


def test_the_sprint_is_not_closed_as_already_done(tmp_path, monkeypatch):
    _product(tmp_path, DIVS)
    monkeypatch.setattr(acceptance_nodes, "_root", lambda state: tmp_path)
    monkeypatch.setattr(suite, "is_locked", lambda root: True)
    monkeypatch.setattr(acceptance_nodes, "criteria_due", lambda state: ["AC-1"])
    monkeypatch.setattr(suite, "deferred", lambda root: {})
    ran = []
    monkeypatch.setattr(suite, "run", lambda root: ran.append(root) or SimpleNamespace(ran=True, runtime_problems=[]))
    state = {**_state(tmp_path), "sprint_plan": SimpleNamespace(sprints=[SimpleNamespace(criteria=["AC-1"])]),
             "current_sprint_index": 0}
    assert acceptance_nodes.sprint_already_done(state) == ""
    assert ran == [], "decided before measuring anything"


@pytest.mark.parametrize("script", [
    "const item = document.createElement('div');\nitem.setAttribute('role', 'listitem');\n",
    "const item = document.createElement('div');\nitem.role = 'listitem';\n",
    "h('div', { role: 'listitem' }, title);\n",
])
def test_a_role_given_from_a_script_is_a_list_item(tmp_path, script):
    """Measured on one run: the page set each record's role with `setAttribute`; the check saw no list item and a
    right page's sprint was planned again three times."""
    _product(tmp_path, script)
    assert suite.records_the_page_never_makes(tmp_path, BRIEF) == []
