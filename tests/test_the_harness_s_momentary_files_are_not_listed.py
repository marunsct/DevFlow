"""The harness's momentary files are never listed to a stage.

The parse probe is written beside a file so its imports resolve, and removed a
moment later. In parallel mode another stage's listing can catch it: one run's
workspace digest listed `src/main.d7cebffc.tmp.js (2 lines)`, and a stage spent
a call trying to read it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tools.repository import is_harness_momentary, list_repository_files


@pytest.mark.parametrize("name", ["main.d7cebffc.tmp.js", "store.0a1b2c3d.tmp.mjs", "..project-memory.json.k3j2x9.tmp"])
def test_the_harness_s_momentary_files_are_named(name) -> None:
    assert is_harness_momentary(name)


@pytest.mark.parametrize("name", ["main.js", "notes.tmp", "report.tmp.js", "app.test.js", "build.12345678.js"])
def test_a_product_s_files_are_not(name) -> None:
    assert not is_harness_momentary(name)


def test_the_workspace_listing_leaves_the_probe_out(tmp_path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.js").write_text("export const a = 1;\n")
    (tmp_path / "app" / "main.d7cebffc.tmp.js").write_text("export const a = 2;\n")

    assert list_repository_files(str(tmp_path)) == ["app/main.js"]


def test_a_stage_s_ls_leaves_it_out() -> None:
    from app.agents.workspace_backend import _is_hidden

    assert _is_hidden(SimpleNamespace(path="/app/main.d7cebffc.tmp.js"), "/app")
    assert not _is_hidden(SimpleNamespace(path="/app/main.js"), "/app")
