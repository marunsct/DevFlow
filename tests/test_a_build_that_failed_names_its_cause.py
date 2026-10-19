"""A product that did not start is recorded with the line that says why.

Measured live: the page's build failed before Playwright's web server could
start, and the recorded output kept three lines from Playwright's own error and
the last eight - a list of the files a Node error object held. The build's own
line naming its cause sat between them and was cut, so every fixer of the
defect was told that the build failed and not why.
"""
from __future__ import annotations

from app.acceptance.suite import the_product_did_not_start

OUTPUT = "\n".join([
    "Error: Process from config.webServer was not able to start. Exit code: 1",
    "[WebServer] vite v6.3.5 building for production...",
    "[WebServer] transforming...",
    "[WebServer] ✗ Build failed in 48ms",
    '[WebServer] error during build:',
    '[WebServer] [vite]: Rollup failed to resolve import "react-router-dom" from "src/App.tsx".',
    "[WebServer] This is most likely unintended because it can break your application at runtime.",
    "[WebServer] node:internal/modules/run_main:107",
    "[WebServer]     throw error;",
    "[WebServer]     ^",
    "[WebServer] {",
    "[WebServer]   code: 'PLUGIN_ERROR',",
    "[WebServer]   watchFiles: [",
    "[WebServer]     'shop/index.html',",
    "[WebServer]     'shop/src/main.tsx',",
    "[WebServer]     'shop/src/App.tsx',",
    "[WebServer]     'shop/src/styles.css',",
    "[WebServer]   ]",
    "[WebServer] }",
    "[WebServer] Node.js v24.22.0",
])


def test_the_line_that_names_the_cause_is_kept():
    recorded = the_product_did_not_start(OUTPUT)

    assert 'failed to resolve import "react-router-dom" from "src/App.tsx"' in recorded
    assert "was not able to start" in recorded
    assert len(recorded) <= 2_400


def test_a_short_output_is_kept_whole():
    short = "Error: Process from config.webServer was not able to start. Exit code: 1\nModuleNotFoundError: No module named 'jose'"
    assert "No module named 'jose'" in the_product_did_not_start(short)
