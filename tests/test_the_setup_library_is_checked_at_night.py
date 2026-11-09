"""Each proven-setup library entry is replayed on an empty project at night; one that no longer proves is set aside
(scaffolding plan SF.0b), and the check writes nothing back."""
from __future__ import annotations

import json

from app.stacks import custom_setup


def test_a_failing_entry_is_set_aside_and_a_passing_one_kept(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    for name in ("good", "bad"):
        (library / f"{name}.json").write_text(json.dumps(
            {"declaration": json.dumps({"kind": "http_api"}), "files": {"pytest.ini": "[pytest]\n"}}))
    monkeypatch.setattr(custom_setup, "library_directory", lambda: library)
    seen = []

    def prove(root, project, stack, *, run=None, keep=True, **_):
        seen.append((stack.product_kind, keep, (root / project / "pytest.ini").is_file()))
        return custom_setup.ScaffoldResult(ok="good" in str(root), pack="", project=project, problem="smoke failed")

    monkeypatch.setattr(custom_setup, "prove", prove)
    results = custom_setup.check_the_library(tmp_path / "scratch")
    assert sorted((name, ok) for name, ok, _ in results) == [("bad.json", False), ("good.json", True)]
    assert (library / "good.json").is_file() and (library / "failed" / "bad.json").is_file()
    assert seen and all(kind == "http_api" and keep is False and written for kind, keep, written in seen)


def test_a_proof_that_keeps_nothing_writes_no_library_entry():
    import inspect

    source = inspect.getsource(custom_setup.prove)
    assert source.index("if not keep:") < source.index("remember(stack, replayable)")
