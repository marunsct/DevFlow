"""The nightly pack check runs to the end (harness review HR2.SS.5).

It stopped at one pack on two nights (a read-only tree its rmtree could not remove), and on 11-08 a deploy that
recreated the live worker killed it mid-way with no summary: it ran inside that worker.
"""
from __future__ import annotations

import importlib.util
import os
import stat
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("verify_packs_under_test", ROOT / "scripts" / "loop" / "verify_packs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_read_only_file_left_by_the_last_check_does_not_stop_it(tmp_path) -> None:
    verify = _module()
    left = tmp_path / "go-gin-api" / "pkg" / "mod"
    left.mkdir(parents=True)
    (left / "file.go").write_text("package x\n")
    os.chmod(left / "file.go", stat.S_IRUSR)
    os.chmod(left, stat.S_IRUSR | stat.S_IXUSR)

    verify.clear(tmp_path / "go-gin-api")

    assert (tmp_path / "go-gin-api").is_dir() and not any((tmp_path / "go-gin-api").iterdir())


def test_one_pack_that_raises_does_not_stop_the_others(tmp_path, monkeypatch, capsys) -> None:
    verify = _module()
    monkeypatch.setattr(verify, "base", tmp_path)
    good = types.SimpleNamespace(language="python")

    def pack_named(name):
        if name == "broken":
            raise RuntimeError("no such toolchain")
        return good

    monkeypatch.setitem(sys.modules, "app.stacks", types.SimpleNamespace(pack_named=pack_named))
    monkeypatch.setitem(sys.modules, "app.stacks.scaffold", types.SimpleNamespace(
        scaffold=lambda *a, **k: types.SimpleNamespace(ok=True, problem="", steps=[])))
    monkeypatch.setitem(sys.modules, "app.tools.sandbox", types.SimpleNamespace(
        STACK_MARKER=".stack", _toolchain_keys=lambda *a: {"python"}))

    assert verify.check(["broken", "fine"]) == ["broken"]
    out = capsys.readouterr().out
    assert "=== broken: ok=False" in out and "=== fine: ok=True" in out


def test_the_nightly_runs_the_check_in_its_own_container() -> None:
    text = (ROOT / "scripts" / "loop" / "loop.sh").read_text()
    nightly = text[text.index("\nnightly)"):text.index("\n  ;;", text.index("\nnightly)"))]
    assert 'docker compose run --rm -T --no-deps worker python - < "$HERE/verify_packs.py"' in nightly
    assert "in_worker verify_packs.py" not in nightly
