"""A UI/UX specialist whose model cannot read images is given the rendered page as measured text facts (plan SP.4).

It was shown the page only as screenshots, and only when its model reads images; on a build model that does not, it
had no view of the page at all. Measured on one medium run: low-contrast text, a layout wider than a phone and fields
with no label passed it. The page check every browser suite run starts with now also measures, at a desktop's width
and a phone's, each text colour on its background with its contrast ratio, what sticks out past the viewport, the
stylesheet rules that match no element, the focus outline taken away and the fields with no label; the specialist's
request carries them when its model cannot see.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.stacks import contract, pack_named
from test_graph_routing import agents  # noqa: F401 - `agents` is a fixture

ROOT = Path(__file__).resolve().parents[1]
PLAYWRIGHT = ROOT / "scripts" / "ui" / "node_modules" / "playwright-core"
CHROMES = sorted(Path(os.path.expanduser("~/.cache/ms-playwright")).glob(
    "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")

REPORT = {
    "problems": [],
    "shows": '- heading "Notes" [level=1]\n- textbox "Title"\n- textbox',
    "layout": {"phoneOverflow": 525, "overlaps": [], "smallTargets": []},
    "facts": {
        "desktop": {
            "width": 1280, "pageWider": 0, "overflowing": [], "rules": 12, "unmatched": 2,
            "unmatchedExamples": [".note-list", ".note-item"], "outlineRemoved": ["input:focus"],
            "unlabelled": ['input "body" has only its placeholder "Write here"'],
            "colours": [
                {"text": "#aaaaaa", "background": "#ffffff", "ratio": 2.32, "count": 3, "below": 4.5,
                 "example": 'p.hint "Faint help text"'},
                {"text": "#111111", "background": "#ffffff", "ratio": 18.88, "count": 9, "below": 0,
                 "example": 'h1 "Notes"'},
            ],
        },
        "phone": {"width": 375, "pageWider": 525, "overflowing": ['div.wide "Wide row" reaches 900px'],
                  "colours": [], "shows": '- heading "Notes" [level=1]'},
        "focus": [{"control": 'input "Title"', "seen": False}],
    },
}


def _a_page_product(root: Path, report: dict | None = REPORT) -> None:
    contract.write(root, pack_named("browser-javascript"), "notes", "Notes")
    if report is not None:
        folder = root / "notes" / "test-results"
        folder.mkdir(parents=True)
        (folder / "page-load.json").write_text(json.dumps(report))


class TestTheFacts:
    def test_each_measured_fact_reaches_the_section(self, tmp_path) -> None:
        from app.agents.page_facts import section

        _a_page_product(tmp_path)

        text = section(tmp_path, ["Below 600px the form sits above the list."])

        assert "#aaaaaa on #ffffff: 2.32:1" in text and "BELOW WCAG AA (needs 4.5:1)" in text
        assert "#111111 on #ffffff: 18.88:1" in text and "18.88:1 (9 element(s)) -" not in text
        assert "scrolls sideways by 525px" in text and 'div.wide "Wide row" reaches 900px' in text
        assert "2 of 12" in text and ".note-list" in text
        assert "input:focus" in text and 'with no outline or ring when focused: input "Title"' in text
        assert 'input "body" has only its placeholder "Write here"' in text
        assert 'textbox "Title"' in text
        assert "Below 600px the form sits above the list." in text

    def test_the_section_is_bounded(self, tmp_path) -> None:
        from app.agents.page_facts import MOST_CHARACTERS, section

        _a_page_product(tmp_path, {**REPORT, "shows": "- paragraph: long words\n" * 2_000})

        text = section(tmp_path)

        assert 0 < len(text) <= MOST_CHARACTERS and "BELOW WCAG AA" in text

    @pytest.mark.parametrize("report", [None, {"problems": ["the page did not load: net::ERR_CONNECTION_REFUSED"],
                                               "shows": "", "layout": {}, "facts": {}}])
    def test_a_page_that_never_started_gives_no_section(self, tmp_path, report) -> None:
        from app.agents.page_facts import with_the_page_facts

        _a_page_product(tmp_path, report)
        request = {"messages": [{"role": "user", "content": "Check the advice."}]}

        assert with_the_page_facts(request, tmp_path) is request

    def test_its_words_name_no_product_and_no_control(self, tmp_path) -> None:
        from app.agents.page_facts import section

        _a_page_product(tmp_path)
        text = section(tmp_path).lower()
        for data in ('input "title"', 'input "body"', "write here", 'div.wide "wide row"', 'p.hint "faint help text"',
                     'h1 "notes"', 'heading "notes"', 'textbox "title"', "input:focus"):
            text = text.replace(data, "")

        for word in BANNED:
            assert not re.search(rf"\b{word}\b", text), word


class TestThroughTheGraph:
    def test_a_specialist_that_cannot_see_is_given_the_facts(self, agents, monkeypatch, tmp_path) -> None:
        from test_graph_routing import _approved_review, _document, _graph, _repository, _script_through_sprint, _spec
        from test_graph_routing import responds_with
        from test_the_specialists_advise_before_the_specification import TestThroughTheGraph as Consulting

        import app.models.vision
        from app.agents.advice_review import AdviceReview
        from app.agents.specialist_advice import SpecialistAdvice
        from app.graph import workflow as workflow_module
        from app.graph.workflow import start_workflow

        monkeypatch.setattr(app.models.vision, "the_reviewer_reads_images", lambda: False)
        Consulting._consulting(monkeypatch, agents, ["ui_ux"], reviewing=True)
        Consulting._script_the_stack(agents)
        monkeypatch.setattr(workflow_module, "create_advice_reviewer_agent",
                            lambda role, *args, **kwargs: agents.agent(f"advice_reviewer_{role}"))
        agents.script("advisor_ui_ux", [responds_with(SpecialistAdvice(recommendations=["Keep text at AA contrast."]))])
        agents.script("principal_architect", [responds_with(_spec(
            interface_design=["Below 600px the form sits above the list."],
            specialist_advice_decisions=["UX-1: adopted - interface_design"],
        ))])
        agents.script("architecture_review", [responds_with(_approved_review())])
        agents.script("advice_reviewer_ui_ux", [responds_with(AdviceReview())])
        _script_through_sprint(agents)
        repository = _repository(tmp_path)
        # The report alone, at the workspace's root as a product with no pack keeps it: a pack's contract would start
        # the pack's own installs and commands in this run.
        (tmp_path / "test-results").mkdir()
        (tmp_path / "test-results" / "page-load.json").write_text(json.dumps(REPORT))

        start_workflow(_graph(), _document(), repository, "run-page-facts")

        asked = agents.last_request_text("advice_reviewer_ui_ux")
        assert "#aaaaaa on #ffffff: 2.32:1" in asked and "BELOW WCAG AA" in asked


def _in_a_browser(tmp_path: Path, page: str, width: int, script: str) -> dict:
    (tmp_path / "page.html").write_text(page)
    runner = tmp_path / "measure.mjs"
    runner.write_text(
        f"import {{ chromium }} from {json.dumps(str(PLAYWRIGHT / 'index.mjs'))};\n"
        f"const browser = await chromium.launch({{ executablePath: {json.dumps(str(CHROMES[-1]))} }});\n"
        f"const page = await browser.newPage({{ viewport: {{ width: {width}, height: 740 }} }});\n"
        f"await page.goto('file://' + {json.dumps(str(tmp_path / 'page.html'))});\n"
        + script
        + "await browser.close();\n"
    )
    done = subprocess.run(["node", str(runner)], capture_output=True, text=True, timeout=90)
    return json.loads(done.stdout.strip().splitlines()[-1])


PAGE = """<!doctype html><html><head><style>
body { margin: 0; background: #ffffff; color: #111111; font-family: sans-serif; font-size: 16px; }
.hint { color: #aaaaaa; }
.wide { width: 900px; height: 20px; }
.never-used { color: #ff0000; }
input:focus { outline: none; }
</style></head><body>
<h1>Notes</h1>
<p class="hint">Faint help text</p>
<div class="wide">Wide row</div>
<label for="title">Title</label><input id="title" name="title">
<input name="body" placeholder="Write here">
</body></html>"""


@pytest.mark.skipif(not (PLAYWRIGHT.is_dir() and CHROMES and shutil.which("node")),
                    reason="needs node, playwright-core and a headless Chromium")
class TestInABrowser:
    def test_the_page_check_measures_the_facts(self, tmp_path) -> None:
        from app.stacks.packs._javascript import PAGE_FACTS

        found = _in_a_browser(tmp_path, PAGE, 375, f"console.log(JSON.stringify(await page.evaluate({PAGE_FACTS})));\n")

        faint = [pair for pair in found["colours"] if pair["text"] == "#aaaaaa"]
        assert faint and faint[0]["background"] == "#ffffff" and faint[0]["ratio"] == 2.32 and faint[0]["below"] == 4.5
        assert [pair["below"] for pair in found["colours"] if pair["text"] == "#111111"] == [0]
        assert found["overflowing"] == ['div.wide "Wide row" reaches 900px'] and found["pageWider"] == 525
        assert found["unmatchedExamples"] == [".never-used"]
        assert found["outlineRemoved"] == ["input:focus"]
        assert found["unlabelled"] == ['input "body" has only its placeholder "Write here"']

    def test_the_tab_key_finds_a_focus_that_cannot_be_seen(self, tmp_path) -> None:
        from app.stacks.packs._javascript import FOCUSED

        found = _in_a_browser(tmp_path, PAGE, 1280,
                              f"await page.keyboard.press('Tab');\nconsole.log(JSON.stringify(await page.evaluate({FOCUSED})));\n")

        assert found == {"control": 'input "title"', "seen": False}
