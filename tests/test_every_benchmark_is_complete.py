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
    assert any((bench / "reference").iterdir())
    assert json.loads((bench / "bench.json").read_text())["kind"]


def test_the_python_sibling_holds_the_same_hidden_tests() -> None:
    for name in ("bookmarks.spec.mjs",):
        assert (ROOT / "fullstack-bookmarks-py" / "hidden" / name).read_bytes() == (
            ROOT / "fullstack-bookmarks" / "hidden" / name
        ).read_bytes()
