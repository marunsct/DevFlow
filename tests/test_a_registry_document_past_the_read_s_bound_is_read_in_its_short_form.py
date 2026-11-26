"""A registry document longer than the read takes is read in its abbreviated form, and a read that fails says so (LF.1586).

Measured in two runs' worker logs: "Could not read the releases of npm playwright: Unterminated string starting at
... char 8388411", also for `@playwright/test` and `@types/node`, eight times in 15 minutes. The read stops at 8 MiB
and npm's whole documents of those packages are 11-17 MB, so the JSON failed, the release check of each package was
skipped, and nothing but an info line said so. npm serves an abbreviated document (`engines` and `deprecated` per
release) and PyPI a simple JSON index (`requires-python`, `yanked` and `upload-time` per file).
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.tools import release_fit

CAPTURED = Path(__file__).parent / "captured"
#: A whole document as the read leaves it when the registry's is longer than 8 MiB: cut inside a string.
CUT = b'{"_id": "a-package", "versions": {"1.0.0": {"readme": "' + b"x" * (8 * 1024 * 1024 + 64)


def _registry(short_form: bytes):
    """A registry whose whole document is past the read's bound and which serves `short_form` when asked for it."""
    asked: list[tuple[str, str]] = []

    def fetch(url: str, accept: str = "") -> tuple[int, bytes]:
        asked.append((url, accept))
        return (200, short_form) if accept else (200, CUT)

    return fetch, asked


def test_npm_s_abbreviated_document_is_read_when_the_whole_one_is_cut():
    fetch, asked = _registry((CAPTURED / "npm-abbreviated-document-is-number.json").read_bytes())

    found = {r.version: r for r in release_fit.releases("npm", "is-number", fetch=fetch)}

    assert found["7.0.0"].needs == ">=0.12.0" and found["6.0.0"].needs == ">=0.10.0"
    assert asked[-1] == ("https://registry.npmjs.org/is-number", "application/vnd.npm.install-v1+json")


def test_the_release_check_runs_on_the_abbreviated_document():
    fetch, _ = _registry((CAPTURED / "npm-abbreviated-document-is-number.json").read_bytes())

    assert release_fit.newest_that_fits("npm", "is-number", "node v24.1.0", fetch=fetch)["version"] == "7.0.0"


def test_pypi_s_simple_index_is_read_when_the_whole_document_is_cut():
    fetch, asked = _registry((CAPTURED / "pypi-simple-json-iniconfig.json").read_bytes())

    found = {r.version: r for r in release_fit.releases("pypi", "iniconfig", fetch=fetch)}

    assert found["2.3.1"].needs == ">=3.10" and found["2.3.1"].released == "2026-10-06"
    assert asked[-1] == ("https://pypi.org/simple/iniconfig/", "application/vnd.pypi.simple.v1+json")


def test_a_release_read_that_cannot_be_made_is_said_as_a_skipped_check(caplog):
    def only_the_whole_document(url: str) -> tuple[int, bytes]:
        return 200, CUT

    with caplog.at_level(logging.INFO, logger="app.tools.release_fit"):
        assert release_fit.releases("npm", "a-large-package", fetch=only_the_whole_document) == []

    warned = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("a-large-package" in line and "skipped" in line for line in warned)
