"""A test runner's configuration is configuration, whatever qualifier its name carries.

Measured on one run: a project with one Vitest configuration per suite
(`vitest.unit.config.ts`) had its testing work order refused its own runner's
configuration as "product code" five times - under a refusal that says test
configuration is the testing work order's to change.
"""

from __future__ import annotations

import pytest

from app.analysis.file_kinds import classify_file


@pytest.mark.parametrize("path", [
    "notes-api/vitest.unit.config.ts",
    "jest.integration.config.js",
    "web/playwright.e2e.config.ts",
    "vitest.config.unit.ts",
    "vitest.config.ts",
])
def test_a_runner_s_configuration_is_configuration(path):
    assert classify_file(path) == "config"


@pytest.mark.parametrize("path", ["src/config.ts", "src/app.config.ts", "src/vitest.ts", "src/unit.config.ts"])
def test_the_product_s_own_configuration_is_still_the_product(path):
    assert classify_file(path) == "application"
