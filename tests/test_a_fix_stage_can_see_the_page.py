"""A stage can see the running page as a test sees it.

A stage fixing a page had only the failing test's message: what was not found,
never what was there. `look_at_page` starts the product exactly as the suite
does (the project's own Playwright configuration and server command), opens one
path in a real browser and returns the accessibility tree - the roles and names
tests find controls by - with the page's errors and failed requests. Verified
in the worker image on a scaffolded React page, at desktop and phone sizes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.stacks import contract, pack_named
from app.tools import page_view

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _scaffolded(root: Path, pack: str = "browser-react", installed: bool = True) -> Path:
    project = root / "notes"
    for name, text in pack_named(pack).render("notes", "Notes").items():
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).write_text(text)
    if installed:
        (project / "node_modules" / "@playwright" / "test").mkdir(parents=True)
    contract.write(root, pack_named(pack), "notes", "Notes")
    return project


def _browser(project: Path, seen: dict, captured: list):
    """Stands in for `npx playwright test`: records the overlay, writes what the page showed."""
    def run(argv, category, where):
        overlay = project / page_view.OVERLAY_DIR
        captured.append({
            "argv": list(argv), "category": category, "where": where,
            "config": (overlay / "playwright.config.mjs").read_text(),
            "asked": json.loads((overlay / "look.json").read_text()),
        })
        (overlay / "seen.json").write_text(json.dumps(seen))
        return {"returncode": "0"}

    return run


def test_it_starts_the_product_as_the_suite_does_and_says_what_is_on_the_page(tmp_path):
    project = _scaffolded(tmp_path)
    captured: list = []
    seen = {
        "status": 200, "title": "Notes", "tree": '- main:\n  - heading "Notes" [level=1]',
        "errors": ["TypeError: x is undefined", "TypeError: x is undefined"],
        "failed": ["404 GET http://127.0.0.1:1/api/notes"], "wider_than_the_screen": True,
    }

    found = page_view.look(tmp_path, "settings", "phone", run=_browser(project, seen, captured))

    assert captured[0]["argv"] == ["npx", "playwright", "test", "--config", "test-results/page-view/playwright.config.mjs"]
    assert captured[0]["where"] == "notes" and captured[0]["category"] == "test"
    assert "import base from '../../playwright.config.js'" in captured[0]["config"]
    assert "reporter: [['list']]" in captured[0]["config"], "never the suite's JUnit report"
    assert captured[0]["asked"] == {"path": "/settings", "width": 390, "height": 844}
    assert found["accessibility_tree"] == seen["tree"]
    assert found["page_errors"] == ["TypeError: x is undefined"]
    assert found["failed_requests"] == ["404 GET http://127.0.0.1:1/api/notes"]
    assert found["wider_than_the_screen"] is True
    assert not (project / page_view.OVERLAY_DIR).exists(), "nothing is left in the project"


def test_a_page_that_never_opened_says_how_the_browser_run_ended(tmp_path):
    _scaffolded(tmp_path)

    found = page_view.look(tmp_path, run=lambda *a: {"returncode": "1", "stdout": "Error: webServer exited early"})

    assert "webServer exited early" in found["error"]


@pytest.mark.parametrize("path", ["http://example.com/", "/../../etc/passwd"])
def test_only_a_path_on_the_product_s_own_server_is_opened(tmp_path, path):
    _scaffolded(tmp_path)

    assert "path on the product's own server" in page_view.look(tmp_path, path, run=lambda *a: {})["error"]


def test_only_a_product_with_a_page_the_suite_opens_gets_it(tmp_path):
    assert page_view.page_view_tools(str(tmp_path)) == []

    _scaffolded(tmp_path, installed=False)
    assert page_view.page_view_tools(str(tmp_path)) == [], "nothing installed to open it with"

    (tmp_path / "notes" / "node_modules" / "@playwright" / "test").mkdir(parents=True)
    assert [t.name for t in page_view.page_view_tools(str(tmp_path))] == ["look_at_page"]


def test_a_service_with_no_page_does_not_get_it(tmp_path):
    _scaffolded(tmp_path, "node-http-api")

    assert page_view.page_view_tools(str(tmp_path)) == []


def test_it_can_be_switched_off(tmp_path, monkeypatch):
    _scaffolded(tmp_path)
    monkeypatch.setenv("PAGE_VIEW_ENABLED", "false")

    assert page_view.page_view_tools(str(tmp_path)) == []


def test_a_fix_stage_on_a_page_is_told_to_look_first(tmp_path):
    from app.agents.specialists import LOOK_BEFORE_CHANGING_THE_PAGE, build_defect_fix_request

    def brief(root):
        return build_defect_fix_request("AC-2 fails", "run it", "saved", "not saved", [], False, str(root))["messages"][0]["content"]

    assert LOOK_BEFORE_CHANGING_THE_PAGE not in brief(tmp_path)
    _scaffolded(tmp_path)
    assert LOOK_BEFORE_CHANGING_THE_PAGE in brief(tmp_path)
    assert not BANNED.search(LOOK_BEFORE_CHANGING_THE_PAGE)
    assert not BANNED.search(page_view.build_page_view_tool(str(tmp_path)).description)


def test_specialists_on_a_page_product_are_given_it(tmp_path):
    from app.agents.specialists import create_specialist_agent
    from app.models import CompatibleChatOpenAI

    _scaffolded(tmp_path)
    model = CompatibleChatOpenAI(model="Qwen3.5-9B-GGUF", api_key="unused", base_url="http://localhost:9/v1")

    agent = create_specialist_agent("ui_ux", model=model, repo_root=tmp_path)

    assert "look_at_page" in agent.nodes["tools"].bound._tools_by_name
