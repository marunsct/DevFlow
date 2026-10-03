"""Stack packs: choosing one, scaffolding it, and keeping its contract.

The scaffolds themselves were proven in the worker image (install, one unit
and one acceptance smoke test each, through the commands the harness uses);
these tests hold the parts that need no toolchain.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import junit
from app.stacks import KINDS, aligned_stack, choose_pack, pack_named, product_kind, supported_stacks_note
from app.stacks import contract
from app.stacks.packs import ALL_PACKS
from app.stacks.scaffold import scaffold


def _stack(**fields):
    base = dict(language="", framework="", frontend_framework="", database="", testing_framework="", product_kind="")
    base.update(fields)
    return SimpleNamespace(**base)


@pytest.mark.parametrize(
    "stack, text, expected",
    [
        (_stack(language="JavaScript", framework="None", frontend_framework="Vanilla JS"), "", "browser-javascript"),
        (_stack(language="HTML/CSS/JavaScript", framework="none"), "A single-page web app", "browser-javascript"),
        (_stack(language="TypeScript", framework="React", frontend_framework="React"), "", "browser-react"),
        (_stack(language="JavaScript", framework="Express"), "A REST API for notes", "node-http-api"),
        (_stack(language="JavaScript", framework="Express", frontend_framework="Vanilla JS"), "", "fullstack-node"),
        (_stack(language="Python", framework="FastAPI"), "", "python-http-api"),
        (_stack(language="Python", framework="None"), "A command-line tool run from the terminal", "python-cli"),
        (_stack(language="Python", framework="argparse"), "", "python-cli"),
        (_stack(language="Python", framework="None"), "A library other programs import", "python-library"),
        (_stack(language="Python", framework="None", product_kind="library"), "a web page", "python-library"),
    ],
)
def test_the_pack_fits_the_stack(stack, text, expected) -> None:
    pack = choose_pack(stack, text)
    assert pack is not None and pack.name == expected


@pytest.mark.parametrize(
    "stack, text",
    [
        (_stack(language="Go", framework="Gin"), "A REST API"),  # no Go pack
        (_stack(language="Python", framework="Django"), "A REST API"),  # no Django pack
        (_stack(language="JavaScript", framework="Vue", frontend_framework="Vue"), ""),
        (_stack(language="Python", framework="None"), ""),  # nothing says what kind
    ],
)
def test_no_pack_is_forced_on_a_stack_none_fits(stack, text) -> None:
    assert choose_pack(stack, text) is None


def test_every_pack_is_complete_and_named_once() -> None:
    names = [pack.name for pack in ALL_PACKS]
    assert len(names) == len(set(names))
    for pack in ALL_PACKS:
        assert pack.kind in KINDS
        assert pack_named(pack.name) is pack
        rendered = pack.render("demo-app", "Demo App")
        assert not any("{{" in path or "{{" in body for path, body in rendered.items()), pack.name
        assert all(name in rendered for name in pack.kept_files), pack.name
        smoke = pack.rendered_smoke_files("demo-app", "Demo App")
        assert any(path.startswith(pack.unit_dir + "/") for path in smoke), pack.name
        assert any(path.startswith(pack.acceptance_dir + "/") for path in smoke), pack.name
        assert pack.acceptance_report and pack.unit_report
        assert "{{" not in pack.filled(pack.guide + pack.acceptance_guide, "demo-app")
        # How a test names its criterion is part of every pack's acceptance guide.
        assert "AC-3" in pack.acceptance_guide or "ac3" in pack.acceptance_guide


def test_the_stack_is_aligned_with_the_pack() -> None:
    from app.agents.tools_models import TechnologyStack

    stack = TechnologyStack(
        language="JavaScript", framework="none", database="localStorage", testing_framework="Jest"
    )
    pack = choose_pack(stack, "a web page")
    aligned = aligned_stack(stack, pack)
    assert aligned.testing_framework == pack.stack["testing_framework"]
    assert aligned.database == "localStorage"
    assert aligned.product_kind == "browser_app"


def test_the_stack_selector_is_told_which_stacks_scaffold() -> None:
    note = supported_stacks_note()
    assert all(pack.title in note for pack in ALL_PACKS)
    assert all(kind in note for kind in KINDS)


def test_product_kind_reads_the_frameworks_before_the_brief() -> None:
    assert product_kind(_stack(framework="FastAPI"), "a web page") == "fullstack"
    assert product_kind(_stack(framework="FastAPI"), "") == "http_api"
    assert product_kind(_stack(framework="click"), "") == "cli"
    assert product_kind(_stack(), "") == ""


def _fake_runner(root: Path, pack, outcomes: dict[str, int] | None = None):
    """Runs nothing; writes the report each test command would have written."""
    outcomes = outcomes or {}
    calls = []

    def run(argv, category, working_directory):
        calls.append((tuple(argv), category))
        code = outcomes.get(category, 0)
        if category == "test":
            commands = pack.commands(working_directory)
            report = pack.unit_report if list(argv) == commands["unit_test"] else pack.acceptance_report
            target = root / working_directory / report
            target.parent.mkdir(parents=True, exist_ok=True)
            failure = "<failure message='no'/>" if code else ""
            target.write_text(f"<testsuites><testsuite><testcase name='smoke'>{failure}</testcase></testsuite></testsuites>")
        return {"returncode": str(code), "stdout": "", "stderr": ""}

    return run, calls


def test_a_scaffold_whose_smoke_tests_pass_is_kept(tmp_path) -> None:
    pack = pack_named("browser-javascript")
    run, calls = _fake_runner(tmp_path, pack)

    result = scaffold(tmp_path, pack, "demo-app", "Demo App", run=run)

    assert result.ok, result.problem
    assert [category for _, category in calls] == ["install", "test", "test"]
    project = tmp_path / "demo-app"
    assert (project / "playwright.config.js").is_file()
    # The smoke tests and their reports are gone: they assert nothing about the product.
    assert not (project / "tests" / "scaffold-smoke.test.js").exists()
    assert not (project / "acceptance" / "scaffold-smoke.spec.js").exists()
    assert not (project / pack.acceptance_report).exists()
    assert contract.read(tmp_path)["pack"] == "browser-javascript"


def test_a_scaffold_whose_smoke_test_fails_is_not_kept(tmp_path) -> None:
    pack = pack_named("python-http-api")
    run, _ = _fake_runner(tmp_path, pack, {"test": 1})

    result = scaffold(tmp_path, pack, "demo-app", "Demo App", run=run)

    assert not result.ok
    assert "unit smoke test did not pass" in result.problem
    assert contract.read(tmp_path) is None


def test_a_failed_install_is_tried_twice_then_reported(tmp_path) -> None:
    pack = pack_named("node-http-api")
    run, calls = _fake_runner(tmp_path, pack, {"install": 1})

    result = scaffold(tmp_path, pack, "demo-app", "Demo App", run=run)

    assert not result.ok and "npm install" in result.problem
    assert [category for _, category in calls] == ["install", "install"]


def test_a_seeded_project_is_built_on_as_it_is(tmp_path) -> None:
    pack = pack_named("browser-javascript")
    (tmp_path / "demo-app").mkdir()
    (tmp_path / "demo-app" / "package.json").write_text("{}")
    run, calls = _fake_runner(tmp_path, pack)

    result = scaffold(tmp_path, pack, "demo-app", "Demo App", run=run)

    assert not result.ok and "already has a project manifest" in result.problem
    assert calls == []


def test_the_contract_puts_back_runner_configuration_and_scripts(tmp_path) -> None:
    pack = pack_named("browser-javascript")
    run, _ = _fake_runner(tmp_path, pack)
    scaffold(tmp_path, pack, "demo-app", "Demo App", run=run)
    project = tmp_path / "demo-app"
    (project / "playwright.config.js").write_text("export default {};\n")
    manifest = json.loads((project / "package.json").read_text())
    manifest["scripts"]["test"] = "jest"
    manifest["dependencies"] = {"marked": "^12.0.0"}
    (project / "package.json").write_text(json.dumps(manifest))

    repairs = contract.enforce(tmp_path)

    assert len(repairs) == 2
    assert (project / "playwright.config.js").read_text() == pack.render("demo-app", "Demo App")["playwright.config.js"]
    after = json.loads((project / "package.json").read_text())
    assert after["scripts"]["test"] == pack.kept_scripts["test"]
    # Everything else in the manifest is the product's, and stays.
    assert after["dependencies"] == {"marked": "^12.0.0"}
    assert contract.enforce(tmp_path) == []


def test_the_contract_is_described_to_every_stage(tmp_path) -> None:
    pack = pack_named("python-cli")
    run, _ = _fake_runner(tmp_path, pack)
    scaffold(tmp_path, pack, "word-count", "Word Count", run=run)

    text = contract.describe(tmp_path)

    assert "word-count/acceptance/" in text and "locked" in text
    assert "word_count" in text and "{{" not in text
    assert contract.describe(tmp_path / "elsewhere") == ""


def test_junit_reports_from_each_runner_are_read() -> None:
    playwright = (
        "<testsuites><testsuite name='todo.spec.js'>"
        "<testcase name='[AC-1] adds an item' classname='todo.spec.js' time='0.5'></testcase>"
        "<testcase name='[AC-2][AC-3] edits it' classname='todo.spec.js'><failure message='expected 1'>stack</failure></testcase>"
        "<testcase name='skipped one' classname='todo.spec.js'><skipped/></testcase>"
        "</testsuite></testsuites>"
    )
    report = junit.parse(playwright)
    assert report.found and (report.passed, report.failed, report.skipped) == (1, 1, 1)
    assert report.tests[1].tags == ("AC-2", "AC-3")
    assert "expected 1" in report.tests[1].message

    pytest_report = junit.parse(
        "<testsuites><testsuite><testcase classname='acceptance.test_notes' name='test_ac4_note_survives_restart'>"
        "<error message='boom'/></testcase></testsuite></testsuites>"
    )
    assert pytest_report.tests[0].tags == ("AC-4",) and pytest_report.failed == 1

    assert not junit.parse("not xml").found
    assert not junit.read("/nonexistent/report.xml").found


def test_the_module_a_brief_names_is_the_package_scaffolded(tmp_path) -> None:
    from app.stacks import stated_module

    assert stated_module("Run as `python -m wordstats <file>` from the project") == "wordstats"
    assert stated_module("A Python package named `textkit`, used as `import textkit`.") == "textkit"
    assert stated_module("A web page with a Title field.") is None

    pack = pack_named("python-cli")
    run, _ = _fake_runner(tmp_path, pack)
    assert scaffold(tmp_path, pack, "word-statistics-tool", "Word Statistics", run=run, package="wordstats").ok
    project = tmp_path / "word-statistics-tool"
    assert (project / "wordstats" / "__main__.py").is_file()
    assert "-m\", \"wordstats\"" in (project / "acceptance" / "conftest.py").read_text()
    assert contract.read(tmp_path)["package"] == "wordstats"
    assert "wordstats" in contract.describe(tmp_path)


def test_a_service_pack_says_how_to_start_it() -> None:
    for name in ("node-http-api", "fullstack-node", "python-http-api"):
        rendered = pack_named(name).render("notes", "Notes")
        assert rendered["start.sh"].startswith("#!/bin/sh"), name


def test_a_red_suite_fails_fast_and_never_on_a_fixed_port() -> None:
    """One run's suite, written before the product as it should be, took 249
    seconds to fail: every missing control waited out Playwright's 30-second
    default. Another run's leftover server held the one port the suite used."""
    for pack in ALL_PACKS:
        config = pack.render("demo", "Demo").get("playwright.config.js")
        if config is None:
            continue
        assert "actionTimeout: 3_000" in config, pack.name
        assert "timeout: 15_000" in config, pack.name
        assert "process.env.ACCEPTANCE_PORT ||" in config and "Math.random()" in config, pack.name


def test_every_harness_test_command_gets_a_free_port(monkeypatch, tmp_path) -> None:
    from app.stacks import scaffold as scaffolding

    seen = []
    monkeypatch.setattr(
        "app.tools.sandbox.SandboxExecutor.execute",
        lambda argv, **kwargs: seen.append(kwargs.get("extra_env")) or {"returncode": "0"},
    )
    run = scaffolding.sandbox_runner(tmp_path)
    run(["npm", "run", "test:acceptance"], "test", "app")
    run(["npm", "install"], "install", "app")
    assert int(seen[0]["ACCEPTANCE_PORT"]) > 0
    assert seen[1] is None


def test_the_contract_says_the_kept_files_are_not_the_product(tmp_path) -> None:
    pack = pack_named("browser-javascript")
    run, _ = _fake_runner(tmp_path, pack)
    scaffold(tmp_path, pack, "demo-app", "Demo App", run=run)
    text = contract.describe(tmp_path)
    assert "test setup, not the product" in text and "test them" in text
