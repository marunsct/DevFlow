"""The files a stage is shown leave out a folder a tool fills, known by the manifest beside it.

Measured on one Ruby run: Bundler installed the gems into `vendor/bundle` beside the `Gemfile`, and every stage's
listing named them - `vendor/bundle/ruby/3.3.0/cache/puma-6.6.1.gem` and "... and 780 more".
"""
from __future__ import annotations

from pathlib import Path

from app.agents import project_memory
from app.tools.repository import list_repository_files


def _a_ruby_project(root: Path) -> None:
    (root / "notes-api" / "vendor" / "bundle" / "ruby" / "gems" / "rack-3.2.8" / "lib").mkdir(parents=True)
    (root / "notes-api" / "vendor" / "bundle" / "ruby" / "gems" / "rack-3.2.8" / "lib" / "rack.rb").write_text("module Rack; end\n")
    (root / "notes-api" / "Gemfile").write_text("source 'https://rubygems.org'\ngem 'rack'\n")
    (root / "notes-api" / "app.rb").write_text("require 'rack'\n")


def test_the_listing_leaves_out_what_bundler_installed(tmp_path):
    _a_ruby_project(tmp_path)

    listed = list_repository_files(tmp_path)

    assert "notes-api/app.rb" in listed and "notes-api/Gemfile" in listed
    assert not any("/vendor/" in name for name in listed), listed


def test_the_project_memory_leaves_it_out_too(tmp_path):
    _a_ruby_project(tmp_path)

    held = project_memory.current(tmp_path)

    assert "notes-api/app.rb" in held
    assert not any("/vendor/" in name for name in held), list(held)


def test_a_vendor_folder_with_no_manifest_beside_it_is_the_project_s(tmp_path):
    (tmp_path / "site" / "vendor").mkdir(parents=True)
    (tmp_path / "site" / "vendor" / "chart.js").write_text("export const chart = 1;\n")

    assert "site/vendor/chart.js" in list_repository_files(tmp_path)
