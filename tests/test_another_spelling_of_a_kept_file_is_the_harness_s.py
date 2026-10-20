"""Another spelling of a file the harness keeps is the harness's too, and is removed if written.

Measured on one gate run: the specification planned `playwright.config.ts`, a
work order drafted it beside the kept `playwright.config.js`, and Playwright
loaded it instead - no base URL, no report - so every test failed "Invalid URL"
and the harness counted none of them.
"""
from __future__ import annotations

from app.stacks import contract


def test_a_config_in_another_extension_beside_a_kept_one_is_kept_setup(monkeypatch, tmp_path):
    monkeypatch.setattr(contract, "kept_paths", lambda root: frozenset({"shop/playwright.config.js", "shop/vite.config.ts"}))

    assert contract.owned_by_the_harness(tmp_path, "shop/playwright.config.ts") == contract.KEPT_SETUP
    assert contract.owned_by_the_harness(tmp_path, "shop/vite.config.js") == contract.KEPT_SETUP
    assert contract.owned_by_the_harness(tmp_path, "shop/src/playwright.config.ts") == ""
    assert contract.owned_by_the_harness(tmp_path, "shop/src/App.tsx") == ""


def test_a_shadow_already_written_is_found_beside_its_kept_file(tmp_path):
    (tmp_path / "playwright.config.js").write_text("kept")
    (tmp_path / "playwright.config.ts").write_text("drafted")
    (tmp_path / "playwright.setup.mjs").write_text("other")

    assert [p.name for p in contract._the_files_that_shadow(tmp_path, "playwright.config.js")] == ["playwright.config.ts"]
    assert contract._the_files_that_shadow(tmp_path, "index.js") == []
