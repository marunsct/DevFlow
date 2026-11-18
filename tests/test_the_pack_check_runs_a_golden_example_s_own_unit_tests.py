"""The pack check writes a pack's golden example over the proven scaffold and runs its unit tests.

Deep review 2026-11-18, item E4: the golden example is shown to every stage as code that compiles on the pinned
versions; a version bump that breaks it must fail the pack check rather than teach every run a wrong API.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

from app.stacks.packs.rust_axum_api import PACK as RUST
from app.stacks.packs.node_http_api import PACK as NODE
from app.stacks.scaffold import prove_the_golden_example

PASSED = '<testsuite name="items" tests="2" failures="0"><testcase name="a"/><testcase name="b"/></testsuite>'


class Sandbox:
    """The sandbox runs the pack's unit command; this one records it and leaves the report it is given."""

    def __init__(self, root, report: str | None, returncode: int) -> None:
        self.root, self.report, self.returncode, self.calls = root, report, returncode, []

    def __call__(self, argv, category, project):
        self.calls.append((list(argv), category, project))
        if self.report is not None:
            target = self.root / project / RUST.unit_report
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.report)
        return {"returncode": str(self.returncode), "stdout": "", "stderr": "error[E0412]: cannot find type `Foo`"}


def test_the_example_is_written_over_the_project_and_its_unit_command_run(tmp_path):
    sandbox = Sandbox(tmp_path, PASSED, 0)

    ok, problem = prove_the_golden_example(tmp_path, RUST, "demo-app", "Demo App", run=sandbox, package="demo_app")

    assert (ok, problem) == (True, "")
    assert "demo_app::app()" in (tmp_path / "demo-app" / "tests" / "items.rs").read_text()
    assert ".with_state(state)" in (tmp_path / "demo-app" / "src" / "lib.rs").read_text()
    assert sandbox.calls == [(list(RUST.commands("demo-app", "demo_app")["unit_test"]), "test", "demo-app")]


def test_an_example_that_does_not_compile_fails_the_check_with_the_compiler_s_words(tmp_path):
    ok, problem = prove_the_golden_example(tmp_path, RUST, "demo-app", "Demo App", run=Sandbox(tmp_path, None, 101),
                                           package="demo_app")

    assert not ok
    assert "cannot find type `Foo`" in problem and "exit 101" in problem


def test_a_pack_with_no_example_passes_without_running_anything(tmp_path):
    sandbox = Sandbox(tmp_path, None, 1)

    assert prove_the_golden_example(tmp_path, NODE, "demo-app", "Demo App", run=sandbox) == (True, "")
    assert sandbox.calls == []


def test_the_nightly_check_fails_a_pack_whose_example_does_not_pass(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location(
        "verify_packs_golden", Path(__file__).resolve().parents[1] / "scripts" / "loop" / "verify_packs.py")
    verify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify)
    monkeypatch.setattr(verify, "base", tmp_path)
    packs = {"with-example": types.SimpleNamespace(language="rust", golden_example={"src/lib.rs": "x"}),
             "without": types.SimpleNamespace(language="python", golden_example={})}
    # The scaffold and the example's run are the sandbox's; their answers are the input here.
    monkeypatch.setitem(sys.modules, "app.stacks", types.SimpleNamespace(pack_named=packs.get))
    monkeypatch.setitem(sys.modules, "app.stacks.scaffold", types.SimpleNamespace(
        scaffold=lambda *a, **k: types.SimpleNamespace(ok=True, problem="", steps=[]),
        prove_the_golden_example=lambda *a, **k: (False, "error[E0425]: cannot find value `x`")))
    monkeypatch.setitem(sys.modules, "app.tools.sandbox", types.SimpleNamespace(
        STACK_MARKER=".stack", _toolchain_keys=lambda *a: {"rust"}))

    assert verify.check(["with-example", "without"]) == ["with-example"]
    assert "=== with-example golden example: ok=False" in capsys.readouterr().out
