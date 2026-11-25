"""How a page is styled is checked by a script at each sprint's checks, as defects for its interface's builder (PQ.5).

Read in eight stored products behind green suites: a dark scheme whose title was 1.09:1 on its background, controls
styled by classes no element carries, the pack's token stylesheet never loaded, `outline: none` with nothing in its
place. The page check measured some of it for a reviewer and the quality score read the rest; nothing made it work.
An unloaded token stylesheet and unreadable body text hold the sprint; the rest is one bundled defect that gets one fix.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.analysis import interface_style_checks
from app.graph import acceptance_nodes
from app.sprint import Defect, start_remediation
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ROOT = Path(__file__).resolve().parents[1]
PLAYWRIGHT = ROOT / "scripts" / "ui" / "node_modules" / "playwright-core"
CHROMES = sorted(Path(os.path.expanduser("~/.cache/ms-playwright")).glob(
    "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))

TOKENS = ["--color-bg", "--color-text", "--color-primary"]


def _pair(text: str, background: str, ratio: float, below: float, example: str = 'h1 "Notes"') -> dict:
    return {"text": text, "background": background, "ratio": ratio, "count": 1, "below": below, "example": example}


def _a_page(root: Path, *, files: dict[str, str] | None = None, declared: list[str] | None = TOKENS,
            light: list[dict] = (), dark: list[dict] = (), focus: list[dict] = (), accessibility: list[dict] = ()) -> Path:
    """A scaffolded page product, its files as given, and the page check's report of its last suite run."""
    pack = pack_named("browser-javascript")
    project = root / "notes"
    project.mkdir(parents=True)
    written = {"index.html": pack.files["index.html"].replace("{{title}}", "Notes"), "styles.css": pack.files["styles.css"],
               **(files or {})}
    for relative, text in written.items():
        (project / relative).parent.mkdir(parents=True, exist_ok=True)
        (project / relative).write_text(text)
    contract.write(root, pack, "notes", "Notes")
    facts = {"desktop": {"width": 1280, "colours": list(light), **({"declared": declared} if declared is not None else {})},
             "dark": {"width": 1280, "colours": list(dark)}, "focus": list(focus)}
    (project / "test-results").mkdir(exist_ok=True)
    (project / "test-results" / "page-load.json").write_text(json.dumps(
        {"problems": [], "shows": '- heading "Notes"', "layout": {}, "facts": facts}))
    saved = root / suite.RESULT_FILE
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text(json.dumps({"ran": True, "shows": '- heading "Notes"', "accessibility": list(accessibility)}))
    return project


def _raised(root: Path) -> list:
    return acceptance_nodes.interface_defects({"repository": SimpleNamespace(root_path=str(root))})


def _the(raised: list, opening: str):
    return next((d for d in raised if d.description.startswith(opening)), None)


class TestTheTokenStylesheet:
    def test_a_page_that_does_not_load_it_holds_the_sprint(self, tmp_path):
        _a_page(tmp_path, declared=["--brand"])

        found = _the(_raised(tmp_path), interface_style_checks.TOKENS_NOT_LOADED)

        assert found is not None and found.severity == "major" and found.owner == "ui_ux"
        assert found.affected_files == ["notes/styles.css"]
        assert "--color-text" in found.actual_behavior

    def test_a_page_whose_tokens_are_declared_is_not_told(self, tmp_path):
        _a_page(tmp_path)

        assert _the(_raised(tmp_path), interface_style_checks.TOKENS_NOT_LOADED) is None

    def test_without_the_measurement_the_page_s_code_naming_it_counts(self, tmp_path):
        """An older page check did not list the declared properties: the page's own link to the stylesheet decides."""
        _a_page(tmp_path, declared=None)
        assert _the(_raised(tmp_path), interface_style_checks.TOKENS_NOT_LOADED) is None

        page = tmp_path / "notes" / "index.html"
        page.write_text(page.read_text().replace('<link rel="stylesheet" href="styles.css">', ""))
        assert _the(_raised(tmp_path), interface_style_checks.TOKENS_NOT_LOADED) is not None


class TestContrast:
    def test_dark_scheme_body_text_under_aa_holds_the_sprint_and_names_where_it_is_styled(self, tmp_path):
        """The measured product: a title hard-coded `#1a1a1a`, 1.09:1 on the dark background."""
        _a_page(tmp_path, files={"app.css": ".title { color: #1a1a1a; }\n"},
                dark=[_pair("#1a1a1a", "#0d1117", 1.09, 4.5, 'span.title "Buy milk"')])

        found = _the(_raised(tmp_path), interface_style_checks.TEXT_UNREADABLE)

        assert found is not None and found.severity == "major"
        assert "#1a1a1a on #0d1117 in the dark scheme is 1.09:1, needs 4.5:1" in found.actual_behavior
        assert "notes/app.css" in found.affected_files

    def test_large_text_under_three_to_one_is_a_styling_fault_only(self, tmp_path):
        _a_page(tmp_path, dark=[_pair("#555555", "#0d1117", 2.4, 3, 'h1 "Notes"')])

        raised = _raised(tmp_path)

        assert _the(raised, interface_style_checks.TEXT_UNREADABLE) is None
        bundled = _the(raised, interface_style_checks.STYLING_FAULTS)
        assert bundled is not None and bundled.severity == "minor" and "2.4:1, needs 3:1" in bundled.actual_behavior

    def test_the_light_scheme_is_left_to_the_accessibility_check_when_it_reports_contrast(self, tmp_path):
        _a_page(tmp_path, light=[_pair("#aaaaaa", "#ffffff", 2.32, 4.5)],
                accessibility=[{"id": "color-contrast", "impact": "serious", "help": "h", "count": 1, "where": ["p"]}])
        assert _the(_raised(tmp_path), interface_style_checks.TEXT_UNREADABLE) is None

    def test_the_light_scheme_is_checked_when_the_accessibility_check_did_not_run(self, tmp_path):
        _a_page(tmp_path, light=[_pair("#aaaaaa", "#ffffff", 2.32, 4.5)])
        assert _the(_raised(tmp_path), interface_style_checks.TEXT_UNREADABLE) is not None


class TestTheBundledStylingFaults:
    PAGE = """<!doctype html><html><head><link rel="stylesheet" href="styles.css"><link rel="stylesheet" href="app.css">
</head><body><main><button id="all">All</button><ul id="list"></ul></main><script src="app.js"></script></body></html>"""
    SCRIPT = "document.querySelector('#all').classList.toggle('active', true);\n"
    STYLES = (".add-button { color: var(--color-text); }\n"
              "#list { border: 1px solid #cccccc; }\n"
              "input:focus { outline: none; }\n")

    def test_each_fault_is_named_with_its_file_and_line_in_one_minor_defect(self, tmp_path):
        """The measured product: `.add-button` styled, no element carrying it; the chosen filter given `active`,
        which nothing styled; a raw colour beside the tokens; the focus outline taken away."""
        _a_page(tmp_path, files={"index.html": self.PAGE, "app.js": self.SCRIPT, "app.css": self.STYLES},
                focus=[{"control": 'input "Title"', "seen": False}])

        raised = _raised(tmp_path)
        bundled = [d for d in raised if d.description.startswith(interface_style_checks.STYLING_FAULTS)]

        assert len(bundled) == 1 and bundled[0].severity == "minor"
        said = bundled[0].actual_behavior
        assert "notes/app.css:1 .add-button" in said
        assert "notes/app.js:1: sets `active`; no stylesheet styles `.active`" in said
        assert "notes/app.css:2" in said and "#cccccc" in said
        assert "notes/app.css:3 input:focus" in said and 'input "Title"' in said
        assert set(bundled[0].affected_files) == {"notes/app.css", "notes/app.js"}

    def test_a_state_class_that_is_styled_is_not_named(self, tmp_path):
        _a_page(tmp_path, files={"index.html": self.PAGE, "app.js": self.SCRIPT,
                                 "app.css": "#all.active { color: var(--color-primary); } #list { gap: 1rem; }\n"})

        assert _the(_raised(tmp_path), interface_style_checks.STYLING_FAULTS) is None

    def test_each_check_s_evidence_is_bounded(self, tmp_path):
        many = "".join(f".unused-{n} {{ color: var(--color-text); }}\n" for n in range(20))
        _a_page(tmp_path, files={"app.css": many, "index.html": self.PAGE})

        said = _the(_raised(tmp_path), interface_style_checks.STYLING_FAULTS).actual_behavior

        assert said.count(".unused-") == interface_style_checks.MOST_EVIDENCE * 2  # the name, and the rule quoted
        assert "... and 14 more" in said

    def test_what_the_defects_say_uses_none_of_the_banned_words(self, tmp_path):
        _a_page(tmp_path, files={"index.html": self.PAGE.replace("<button", "<a").replace("</button>", "</a>"),
                                 "app.css": self.STYLES}, declared=["--brand"],
                dark=[_pair("#1a1a1a", "#0d1117", 1.09, 4.5, 'span.title "Milk"')])

        raised = [d for d in _raised(tmp_path) if d.description.startswith(
            (interface_style_checks.TOKENS_NOT_LOADED, interface_style_checks.TEXT_UNREADABLE,
             interface_style_checks.STYLING_FAULTS))]

        assert len(raised) == 3
        for defect in raised:
            for text in (defect.description, defect.expected_behavior, defect.reproduction_steps):
                assert not BANNED.search(text), text


class TestNotHoldingTheSprint:
    @staticmethod
    def _cycle(tries: int):
        defect = Defect(description=f"{interface_style_checks.STYLING_FAULTS} raw colours.", severity="minor",
                        reproduction_steps="r", expected_behavior="e", actual_behavior="a", owner="ui_ux",
                        source="page check", fix_attempts=tries)
        cycle = start_remediation("goal", max_attempts=3)
        return cycle.model_copy(update={"defects": [defect]}), defect

    def test_raised_again_after_its_one_fix_it_is_a_recorded_risk(self):
        cycle, defect = self._cycle(tries=1)

        after, measured = interface_style_checks.set_aside_after_one_try(cycle, [defect])

        assert after.defects[0].status == "accepted_risk"
        assert after.defects[0].accepted_risk_reason == interface_style_checks.SET_ASIDE
        assert measured == []

    def test_before_its_fix_it_is_left_open(self):
        cycle, defect = self._cycle(tries=0)

        after, measured = interface_style_checks.set_aside_after_one_try(cycle, [defect])

        assert after.defects[0].status == "open" and measured == [defect]

    def test_a_gating_finding_is_never_set_aside(self):
        cycle, defect = self._cycle(tries=3)
        gating = defect.model_copy(update={"description": f"{interface_style_checks.TEXT_UNREADABLE} x"})
        cycle = cycle.model_copy(update={"defects": [gating]})

        after, measured = interface_style_checks.set_aside_after_one_try(cycle, [gating])

        assert after.defects[0].status == "open" and measured == [gating]

    def test_through_the_test_round_it_is_recorded_rather_than_sent_to_a_second_fixer(self, tmp_path):
        from workflow_nodes import a_test_round, reported

        cycle, defect = self._cycle(tries=1)
        again = [reported(defect.description, owner="ui_ux", severity="minor", actual_behavior="still raw")]

        update, _ = a_test_round(tmp_path, state={"remediation": cycle},
                                 patches={"app.graph.acceptance_nodes.interface_defects": lambda state: again})

        assert [d.status for d in update["remediation"].defects] == ["accepted_risk"]
        assert update["remediation"].defects[0].accepted_risk_reason == interface_style_checks.SET_ASIDE


@pytest.mark.skipif(not (PLAYWRIGHT.is_dir() and CHROMES and shutil.which("node")),
                    reason="needs node, playwright-core and a headless Chromium")
def test_the_page_check_measures_the_dark_scheme_and_the_declared_tokens(tmp_path):
    """The page check reads the same facts in the dark scheme, and lists the custom properties the page declares."""
    from app.stacks.packs import _javascript

    script = _javascript.page_check("/")
    assert "emulateMedia({ colorScheme: 'dark' })" in script and "facts.dark = await page.evaluate(" in script
    (tmp_path / "page.html").write_text(
        "<!doctype html><html><head><style>:root { --color-text: #111; } body { background: #fff; color: #111 }"
        " @media (prefers-color-scheme: dark) { body { background: #0d1117 } } p { color: #1a1a1a }</style></head>"
        "<body><p>Notes</p></body></html>")
    runner = tmp_path / "measure.mjs"
    runner.write_text(
        f"import {{ chromium }} from {json.dumps(str(PLAYWRIGHT / 'index.mjs'))};\n"
        f"const browser = await chromium.launch({{ executablePath: {json.dumps(str(CHROMES[-1]))} }});\n"
        "const page = await browser.newPage();\n"
        f"await page.goto('file://' + {json.dumps(str(tmp_path / 'page.html'))});\n"
        "await page.emulateMedia({ colorScheme: 'dark' });\n"
        f"console.log(JSON.stringify(await page.evaluate({_javascript.PAGE_FACTS})));\nawait browser.close();\n")
    done = subprocess.run(["node", str(runner)], capture_output=True, text=True, timeout=90)
    found = json.loads(done.stdout.strip().splitlines()[-1])

    assert "--color-text" in found["declared"]
    title = [pair for pair in found["colours"] if pair["text"] == "#1a1a1a"]
    assert title and title[0]["background"] == "#0d1117" and title[0]["below"] == 4.5
