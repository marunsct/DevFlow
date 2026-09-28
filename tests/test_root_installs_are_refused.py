"""`playwright install-deps` is refused, because it cannot work and is not needed.

Measured live on 2026-09-21. `specialist_ui_ux_2` ran
`npx playwright install-deps chromium` inside the worker and got::

    Installing dependencies...
    Switching to root user to install dependencies...
    Failed to install browser dependencies
    Error: Installation process exited with code: 1
    stderr: Password: su: Authentication failure

The container runs as `appuser` by design, so this fails every time. The
Dockerfile already installs the browser system libraries - it records why, from
one run, which burnt all three remediation attempts on a missing
`libglib-2.0.so.0`. And the message it returns points at credentials, so the
agent's next move is `sudo`, or abandoning browser tests altogether.

The same run's Playwright suite went on to pass twenty assertions. The failure
was never about the browser.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import CommandNotAllowed, _needs_root_the_sandbox_will_not_give


class TestItIsRefused:
    @pytest.mark.parametrize(
        "argv",
        [
            ["npx", "playwright", "install-deps", "chromium"],
            ["npx", "playwright", "install-deps"],
            ["playwright", "install-deps", "chromium"],
            ["npx", "playwright", "install", "--with-deps", "chromium"],
            ["npx", "playwright", "install", "chromium", "--with-deps"],
        ],
    )
    def test_every_spelling_that_asks_for_system_packages(self, argv):
        assert _needs_root_the_sandbox_will_not_give(argv) is not None

    def test_the_message_says_it_cannot_work_here(self):
        message = _needs_root_the_sandbox_will_not_give(
            ["npx", "playwright", "install-deps", "chromium"]
        )
        assert "unprivileged" in message
        assert "su: Authentication failure" in message, (
            "the message the agent will have just seen should be named, so it "
            "connects the refusal to the error"
        )

    def test_the_message_says_what_to_do_instead(self):
        """A refusal without a next step sends the agent round again."""
        message = _needs_root_the_sandbox_will_not_give(
            ["npx", "playwright", "install-deps", "chromium"]
        )
        assert "npx playwright test" in message

    def test_the_message_says_the_libraries_are_already_there(self):
        """Otherwise the agent concludes browser tests are impossible here."""
        message = _needs_root_the_sandbox_will_not_give(
            ["npx", "playwright", "install-deps"]
        )
        assert "already in" in message


class TestItRefusesNothingElse:
    @pytest.mark.parametrize(
        "argv",
        [
            # The plain install is a no-op against the image cache: it returned
            # `{"stdout": "", "stderr": "", "returncode": "0"}` in the run that
            # found this. Refusing it would teach distrust of a command that works.
            ["npx", "playwright", "install", "chromium"],
            ["npx", "playwright", "test", "--reporter=line"],
            ["npx", "playwright", "test"],
            # Not playwright at all.
            ["npm", "install", "-D", "@playwright/test"],
            ["npm", "test"],
            ["node", "--check", "app.js"],
            # `install-deps` for something that is not playwright.
            ["some-other-tool", "install-deps"],
        ],
    )
    def test_a_legitimate_command_is_untouched(self, argv):
        assert _needs_root_the_sandbox_will_not_give(argv) is None

    def test_an_empty_command_is_not_a_crash(self):
        assert _needs_root_the_sandbox_will_not_give([]) is None


class TestItIsWiredIntoValidation:
    def test_the_refusal_reaches_the_caller(self):
        """The helper returning a string is only half of it."""
        from app.tools.sandbox import validate_command

        with pytest.raises(CommandNotAllowed) as caught:
            validate_command(
                ["npx", "playwright", "install-deps", "chromium"], "ui_ux_specialist"
            )
        assert "unprivileged" in str(caught.value)
