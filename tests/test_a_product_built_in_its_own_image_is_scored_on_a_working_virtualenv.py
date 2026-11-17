"""A product whose virtualenv points at an interpreter the scorer does not have is scored on one rebuilt from its own
requirements (found on the first whole run in container mode).

Measured: a Python service built with each command in its own container passed its 14 locked tests there, then scored
0 of 9 hidden and 0 of 8 quality, every test failing "start.sh: exec: .venv/bin/python: not found" - the virtualenv
linked to the image's interpreter, which the scoring container lacks. The scorer reported a false acceptance and a
silent loss for a product it never started.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _score():
    spec = importlib.util.spec_from_file_location("bench_score_venv", ROOT / "scripts" / "bench" / "score.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _product(tmp_path, interpreter):
    product = tmp_path / "svc"
    (product / ".venv" / "bin").mkdir(parents=True)
    (product / ".venv" / "bin" / "python").symlink_to(interpreter)
    (product / "requirements.txt").write_text("")
    return product


def test_a_virtualenv_whose_interpreter_is_not_here_is_rebuilt(tmp_path):
    product = _product(tmp_path, "/nonexistent/python3")
    notes = []
    _score()._a_virtualenv_that_runs_here(product, notes)
    assert (product / ".venv" / "bin" / "python").resolve().exists()
    assert notes and "rebuilt" in notes[0]


def test_a_virtualenv_that_runs_is_left_as_it_is(tmp_path):
    product = _product(tmp_path, sys.executable)
    notes = []
    _score()._a_virtualenv_that_runs_here(product, notes)
    assert (product / ".venv" / "bin" / "python").readlink() == Path(sys.executable)
    assert notes == []


def _bundle(tmp_path, monkeypatch, check_code):
    score = _score()
    product = tmp_path / "svc"
    product.mkdir()
    (product / "Gemfile").write_text('source "https://rubygems.org"\n')
    ran = []

    def run(argv, cwd, env=None, timeout=900):  # the bundler is the edge
        ran.append(list(argv))
        return type("Done", (), {"returncode": check_code if argv[1] == "check" else 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(score, "_run", run)
    notes = []
    score._a_bundle_that_runs_here(product, notes)
    return ran, notes


def test_a_bundle_that_does_not_load_here_is_installed_again(tmp_path, monkeypatch):
    """Measured: gems built in the product's image for another platform were ignored as missing extensions."""
    ran, notes = _bundle(tmp_path, monkeypatch, check_code=1)

    assert ran == [["bundle", "check"], ["bundle", "install"]]
    assert notes and "installed again" in notes[0]


def test_a_bundle_that_loads_is_left_as_it_is(tmp_path, monkeypatch):
    ran, notes = _bundle(tmp_path, monkeypatch, check_code=0)

    assert ran == [["bundle", "check"]] and notes == []


def test_the_handoff_reads_the_product_s_own_comments_not_its_installed_gems(tmp_path):
    """Measured on three Ruby runs: a gem in `vendor/bundle` said "I think ..." and each run lost a handoff point."""
    product = tmp_path / "svc"
    (product / "vendor" / "bundle" / "gems" / "diff-lcs" / "lib").mkdir(parents=True)
    (product / "vendor" / "bundle" / "gems" / "diff-lcs" / "lib" / "lcs.rb").write_text("# I think what they used\n")
    (product / "app.rb").write_text("# Serves the notes.\nputs 1\n")

    assert _score().handoff(product)["handoff"]["no_thinking_aloud_in_comments"] is True

    (product / "app.rb").write_text("# Hmm, let me check this again\nputs 1\n")
    assert _score().handoff(product)["handoff"]["no_thinking_aloud_in_comments"] is False
