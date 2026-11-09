"""Every pack's start binds the host it is given, so the product can be reached from a container (harness review HR2.PR.3).

21 of 68 shipped `start.sh` hard-wired `127.0.0.1` with no `HOST`: started in a container the product answered no one
outside it. The default stays 127.0.0.1; `HOST` changes it.
"""
from __future__ import annotations

import re

import pytest

from app.stacks.packs import ALL_PACKS

_ALLOWED = ("HOST:-127.0.0.1", "HOST || '127.0.0.1'")


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda p: p.name)
def test_no_start_hard_wires_the_loopback_address(pack) -> None:
    files = pack.render("app", "App")
    for name in ("start.sh", "scripts/serve-acceptance.mjs"):
        for line in files.get(name, "").splitlines():
            if line.lstrip().startswith(("#", "//")) or "http://" in line or "fetch" in line:
                continue
            for found in re.finditer(r"127\.0\.0\.1", line):
                around = line[max(0, found.start() - 25):found.end() + 2]
                assert any(allowed in around for allowed in _ALLOWED), f"{pack.name} {name}: {line.strip()}"


def test_the_shell_starts_quote_the_host_they_bind() -> None:
    starts = {p.name: p.render("app", "App").get("start.sh", "") for p in ALL_PACKS}
    for name in ("ruby-sinatra-api", "ruby-rails-api", "php-slim-api", "php-laravel-api", "fullstack-django"):
        if starts.get(name):
            assert '"${HOST:-127.0.0.1}' in starts[name], name


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda p: p.name)
def test_a_shell_variable_in_a_javascript_config_is_literal_text(pack) -> None:
    """The start sits in a JavaScript template string: an unescaped `${HOST:-...}` is a syntax error there."""
    for name, text in pack.render("app", "App").items():
        if name.endswith((".js", ".ts", ".mjs", ".cjs")):
            assert not re.search(r"(?<!\\)\$\{[A-Z_][A-Z0-9_]*[:}-]", text), f"{pack.name} {name}"
