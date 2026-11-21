"""The generated Playwright configuration pipes the server's stdout as well as its stderr.

Measured on a Java run: Playwright ignores a `webServer`'s stdout unless told to pipe it, and Spring writes its startup
errors there, so a product that did not start said only "Exit code: 1" through three attempts while its fixers
rewrote files that were not the cause. Python and PHP write theirs to stderr, which is why their runs showed them.
"""
from __future__ import annotations

from app.stacks.packs import _javascript as js


def test_the_server_s_stdout_and_stderr_are_both_piped():
    config = js.playwright_config("sh start.sh", "/health")

    assert "stdout: 'pipe'" in config and "stderr: 'pipe'" in config
    assert config.index("stdout: 'pipe'") > config.index("webServer")


def test_the_page_checking_form_of_the_configuration_pipes_them_too():
    assert "stdout: 'pipe'" in js.playwright_config("node scripts/serve.mjs", "/", checks_the_page=True)
