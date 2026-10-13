"""Every run downloaded its own copy of Chromium.

`sandbox._child_environment` has always preferred an image-level browser cache
at `~/.cache/ms-playwright` and fallen back to a per-run one only when that is
absent. It was absent: nothing ever put a browser in the image.

Measured on 2026-09-19 across the stored workspaces: 22 of them held
`.agent-home/.cache/ms-playwright`, 0.6 to 1.2 GB each, 8.5 GB in total. Not
one byte was ever reused by another run, and every run paid the download
before it could test a page.

The Dockerfile now installs Chromium as `appuser`, whose home is where the
preferred path resolves to. Writable on purpose: when a run installs a
Playwright whose browser revision is not in the image, it downloads the
missing one into the shared cache and every later run gets it, so the first
run after a Playwright release pays once for all of them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.tools.sandbox import _child_environment


def test_the_image_cache_is_preferred_when_it_exists(tmp_path, monkeypatch):
    image_cache = tmp_path / "home" / ".cache" / "ms-playwright"
    image_cache.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    environment = _child_environment(str(workspace), None)

    assert environment["PLAYWRIGHT_BROWSERS_PATH"] == str(image_cache)


def test_the_run_keeps_its_own_cache_when_the_image_has_none(tmp_path, monkeypatch):
    """The fallback that carried every run until now, and still has to work."""
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))

    workspace = tmp_path / "workspace"
    (workspace / ".agent-home" / ".cache" / "ms-playwright").mkdir(parents=True)

    environment = _child_environment(str(workspace), None)

    assert environment["PLAYWRIGHT_BROWSERS_PATH"].startswith(str(workspace))


def test_nothing_is_set_when_no_browser_exists_anywhere(tmp_path, monkeypatch):
    """Playwright's own default is better than a path to nothing."""
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert "PLAYWRIGHT_BROWSERS_PATH" not in _child_environment(str(workspace), None)


def test_the_run_home_is_still_inside_the_workspace(tmp_path, monkeypatch):
    """npm, pip and cargo caches must not become shared state."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    environment = _child_environment(str(workspace), None)

    assert environment["HOME"] == str(workspace / ".agent-home")
    assert environment["TMPDIR"] != str(workspace / ".agent-home"), "short, for sockets: see test_a_tool_can_listen_on_a_socket_in_its_temporary_directory"


def test_the_image_actually_installs_a_browser():
    """The half of this that lives outside Python.

    The preference has been in `_child_environment` since it was written and
    was dead code for want of this line, which is exactly the shape of bug
    this file exists to stop coming back.
    """
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")

    install = re.search(r"^RUN npx .*playwright(?:@\S+)? install chromium", text, re.M)
    assert install, "the image must ship a browser for the preferred path to exist"

    # As `appuser`, or it lands in root's home and the preference misses.
    before = text[: install.start()]
    assert before.rstrip().endswith("USER appuser") or "\nUSER appuser\n" in before
    assert before.rindex("USER appuser") > before.rindex("USER root") if "USER root" in before else True
