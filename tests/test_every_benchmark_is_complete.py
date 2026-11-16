"""Every benchmark has a brief with an Interface section, hidden tests, a reference and its kind.

A benchmark missing one of these cannot score a run honestly: no reference
means the hidden tests were never proven right (benchmarks/README.md).
A sibling that reuses another's hidden tests keeps them byte-identical.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "benchmarks"
BENCHES = sorted(p for p in ROOT.iterdir() if p.is_dir())


@pytest.mark.parametrize("bench", BENCHES, ids=lambda p: p.name)
def test_the_benchmark_has_every_part(bench: Path) -> None:
    assert "## Interface" in (bench / "brief.md").read_text()
    assert any((bench / "hidden").iterdir())
    spec = json.loads((bench / "bench.json").read_text())
    assert spec["kind"]
    # A language-sweep benchmark (LR.43) reuses another's tests, proven fair on that one's references; its own hidden
    # tests must be that benchmark's, unchanged.
    source = ROOT / spec["tests_from"] if spec.get("tests_from") else bench
    assert any((source / "reference").iterdir())
    if source is not bench:
        for test in (source / "hidden").glob("*.py"):
            assert (bench / "hidden" / test.name).read_bytes() == test.read_bytes()


def test_the_python_sibling_holds_the_same_hidden_tests() -> None:
    for name in ("bookmarks.spec.mjs",):
        assert (ROOT / "fullstack-bookmarks-py" / "hidden" / name).read_bytes() == (
            ROOT / "fullstack-bookmarks" / "hidden" / name
        ).read_bytes()
