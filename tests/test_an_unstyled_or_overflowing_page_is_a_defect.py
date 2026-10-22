"""A page nothing styles, or one wider than the phone the brief asks for, is a UI/UX defect.

Nothing measured how a product looks: the acceptance suite, the milestone
review and the benchmark's hidden tests all check function. Over the last 26
stored products, 20 shipped the scaffold's stylesheet untouched by any stage.
Two checks a script can make without judging taste close that gap.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.analysis import interface_checks
from app.graph import acceptance_nodes
from app.stacks import contract, pack_named

PACK = "browser-javascript"


def _scaffolded(root: Path) -> Path:
    pack = pack_named(PACK)
    project = root / "notes"
    project.mkdir(parents=True)
    for relative, text in pack.files.items():
        if relative.endswith((".css", ".html")):
            target = project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text.replace("{{title}}", "Notes").replace("{{project}}", "notes"))
    contract.write(root, pack, "notes", "Notes")
    return project


class TestNobodyStyledIt:
    def test_the_scaffold_s_stylesheet_alone_is_unstyled(self, tmp_path) -> None:
        _scaffolded(tmp_path)

        assert interface_checks.nobody_styled_it(tmp_path) == "notes/styles.css"

    def test_changing_it_styles_the_page(self, tmp_path) -> None:
        project = _scaffolded(tmp_path)
        sheet = project / "styles.css"
        sheet.write_text(sheet.read_text() + "\nbutton { padding: 0.5rem 1rem; }\n")

        assert interface_checks.nobody_styled_it(tmp_path) == ""

    def test_a_stylesheet_of_its_own_styles_the_page(self, tmp_path) -> None:
        project = _scaffolded(tmp_path)
        (project / "src").mkdir()
        (project / "src" / "app.css").write_text("main { display: grid; }\n")

        assert interface_checks.nobody_styled_it(tmp_path) == ""

    def test_a_style_block_styles_the_page(self, tmp_path) -> None:
        project = _scaffolded(tmp_path)
        page = project / "index.html"
        page.write_text(page.read_text().replace("</head>", "<style>main { gap: 1rem; }</style></head>"))

        assert interface_checks.nobody_styled_it(tmp_path) == ""

    def test_what_the_tools_leave_is_not_the_product_s(self, tmp_path) -> None:
        project = _scaffolded(tmp_path)
        (project / "node_modules" / "lib").mkdir(parents=True)
        (project / "node_modules" / "lib" / "lib.css").write_text("x { y: z; }\n")

        assert interface_checks.nobody_styled_it(tmp_path) == "notes/styles.css"

    def test_a_workspace_no_pack_scaffolded_is_never_called_unstyled(self, tmp_path) -> None:
        assert interface_checks.nobody_styled_it(tmp_path) == ""


@pytest.mark.parametrize("brief, asks", [
    ("Responsive design for mobile and desktop", True),
    ("It must work on phones.", True),
    ("A command-line tool that counts words.", False),
])
def test_a_brief_that_asks_for_small_screens(brief, asks) -> None:
    assert interface_checks.asks_for_small_screens(brief) is asks


class TestTheDefects:
    @staticmethod
    def _measured(root: Path, *, shows: str = "- heading \"Notes\"", overflow: int = 0) -> None:
        path = root / suite.RESULT_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ran": True, "shows": shows, "phone_overflow": overflow}))

    @staticmethod
    def _state(root: Path, brief: str = "Responsive design for mobile and desktop") -> dict:
        return {"repository": SimpleNamespace(root_path=str(root)), "document": SimpleNamespace(text=brief)}

    def test_an_unstyled_page_goes_to_the_ui_ux_specialist(self, tmp_path) -> None:
        _scaffolded(tmp_path)
        self._measured(tmp_path)

        [defect] = acceptance_nodes.interface_defects(self._state(tmp_path))

        assert defect.owner == "ui_ux" and "not styled" in defect.description
        assert "interface design in the technical specification" in defect.expected_behavior

    def test_a_page_wider_than_a_phone_when_the_brief_asks_for_phones(self, tmp_path) -> None:
        project = _scaffolded(tmp_path)
        (project / "styles.css").write_text("main { width: 900px; }\n")
        self._measured(tmp_path, overflow=525)

        [defect] = acceptance_nodes.interface_defects(self._state(tmp_path))

        assert "525px wider" in defect.description and defect.owner == "ui_ux"

    def test_a_brief_that_never_mentions_phones_is_not_held_to_one(self, tmp_path) -> None:
        project = _scaffolded(tmp_path)
        (project / "styles.css").write_text("main { width: 900px; }\n")
        self._measured(tmp_path, overflow=525)

        assert acceptance_nodes.interface_defects(self._state(tmp_path, brief="A page for the office.")) == []

    def test_nothing_rendered_yet_is_nothing_to_style(self, tmp_path) -> None:
        _scaffolded(tmp_path)
        self._measured(tmp_path, shows="")

        assert acceptance_nodes.interface_defects(self._state(tmp_path)) == []

    def test_the_defects_name_no_product_and_no_control(self, tmp_path) -> None:
        _scaffolded(tmp_path)
        self._measured(tmp_path, overflow=40)
        text = " ".join(
            f"{d.description} {d.reproduction_steps} {d.expected_behavior} {d.actual_behavior}"
            for d in acceptance_nodes.interface_defects(self._state(tmp_path))
        ).lower()

        for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
            assert not re.search(rf"\b{word}\b", text), word


def test_the_page_probe_measures_a_phone_and_keeps_both_screenshots() -> None:
    from app.stacks.packs._javascript import page_check

    probe = page_check("/")

    assert "phoneOverflow" in probe and "width: 375" in probe
    assert "page-desktop.png" in probe and "page-phone.png" in probe


def test_the_acceptance_result_carries_the_overflow(tmp_path) -> None:
    report = tmp_path / "page-load.json"
    report.write_text(json.dumps({"problems": [], "shows": "x", "layout": {"phoneOverflow": 37}}))

    assert suite._read_phone_overflow(report) == 37
    assert suite._read_phone_overflow(None) == 0


class TestAnAccessibilityEngineChecksThePage:
    """axe-core, a test-only dependency of every page pack, run by the page probe.

    It catches what a script can: a control with no name, text too faint to
    read, structure announced wrongly. Proven on a real product: with its
    labels removed, the probe reported `label (critical): Form elements must
    have labels`.
    """

    @pytest.mark.parametrize("name", ["browser-javascript", "browser-react", "fullstack-node"])
    def test_every_page_pack_installs_it_for_tests_only(self, name) -> None:
        from app.stacks.packs._javascript import AXE_CORE

        manifest = json.loads(pack_named(name).files["package.json"].replace("{{project}}", "x"))

        assert manifest["devDependencies"]["axe-core"] == AXE_CORE
        assert "axe-core" not in (manifest.get("dependencies") or {})

    def test_the_probe_runs_it_and_keeps_only_what_is_serious(self) -> None:
        from app.stacks.packs._javascript import page_check

        probe = page_check("/")

        assert "axe-core/axe.min.js" in probe and "window.axe.run" in probe
        assert "'serious'" in probe and "'critical'" in probe

    def test_the_result_carries_what_it_found(self, tmp_path) -> None:
        report = tmp_path / "page-load.json"
        report.write_text(json.dumps({"layout": {"accessibility": [
            {"id": "label", "impact": "critical", "help": "Form elements must have labels",
             "count": 1, "where": ["#title-input"], "why": ["Form element does not have an implicit label"]},
        ]}}))

        assert suite._read_accessibility(report) == [{
            "id": "label", "impact": "critical", "help": "Form elements must have labels",
            "count": 1, "where": ["#title-input"], "why": ["Form element does not have an implicit label"],
        }]
        assert suite._read_accessibility(None) == []

    def test_what_it_found_goes_to_the_ui_ux_specialist(self, tmp_path) -> None:
        project = _scaffolded(tmp_path)
        (project / "styles.css").write_text("main { gap: 1rem; }\n")
        path = tmp_path / suite.RESULT_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ran": True, "shows": "- main", "accessibility": [
            {"id": "color-contrast", "impact": "serious", "help": "Elements must meet minimum color contrast ratio thresholds",
             "count": 3, "where": ["p.hint"]},
        ]}))

        [defect] = acceptance_nodes.interface_defects(
            {"repository": SimpleNamespace(root_path=str(tmp_path)), "document": SimpleNamespace(text="")}
        )

        assert defect.owner == "ui_ux" and "color-contrast" in defect.description
        assert "3 element(s), e.g. p.hint" in defect.actual_behavior


def test_a_contrast_finding_says_what_was_measured(tmp_path) -> None:
    """One run's fixers changed colours blind for three rounds: the defect named
    the rule and the elements, not the colours, the ratio or the ratio needed."""
    from app.stacks.packs._javascript import page_check

    assert "why: rule.nodes.slice(0, 3)" in page_check("/")
    project = _scaffolded(tmp_path)
    (project / "styles.css").write_text("main { gap: 1rem; }\n")
    path = tmp_path / suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    measured = ("Element has insufficient color contrast of 2.55 (foreground color: #ffffff, "
                "background color: #ffbf00). Expected contrast ratio of 4.5:1")
    path.write_text(json.dumps({"ran": True, "shows": "- main", "accessibility": [
        {"id": "color-contrast", "impact": "serious", "help": "Elements must meet minimum color contrast ratio thresholds",
         "count": 1, "where": ["#add"], "why": [measured]},
    ]}))

    [defect] = acceptance_nodes.interface_defects(
        {"repository": SimpleNamespace(root_path=str(tmp_path)), "document": SimpleNamespace(text="")}
    )

    assert f"#add: {measured}" in defect.actual_behavior
