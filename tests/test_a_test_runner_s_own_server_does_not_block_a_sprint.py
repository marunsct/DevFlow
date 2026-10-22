"""A gating finding about the server a test runner starts does not send a sprint back.

The pipeline asks for that server: a page is tested in a browser, the browser
needs it served, and the runner's configuration starts something to serve it.
One run's fix stage wrote `serve.js` because the browser suite had nothing to
start; the security review found, correctly, a path traversal in it, and the
milestone review made that blocking on the last revision allowed - for a brief
that is a static page with no server.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.graph.workflow import _findings_about_a_server_only_the_tests_start

TRAVERSAL = (
    "The static file server in `serve.js` resolves request paths directly using "
    "`resolve(ROOT, '.' + reqPath)` without sanitizing for path traversal."
)


class _Finding(SimpleNamespace):
    def model_copy(self, update):
        return _Finding(**{**self.__dict__, **update})


class _Review(SimpleNamespace):
    def model_copy(self, update):
        return _Review(**{**self.__dict__, **update})


def _project(root: Path, config_command: str) -> None:
    project = root / "app"
    project.mkdir()
    (project / "package.json").write_text('{"name": "app", "type": "module"}', encoding="utf-8")
    (project / "index.html").write_text("<html><body></body></html>\n", encoding="utf-8")
    (project / "serve.js").write_text("import { createServer } from 'http';\ncreateServer(() => {}).listen(3000);\n", encoding="utf-8")
    (project / "playwright.config.js").write_text(
        f"export default {{ webServer: {{ command: '{config_command}', port: 3000 }} }};\n",
        encoding="utf-8",
    )


def _after(root: Path, *descriptions: str, severity: str = "blocking"):
    review = _Review(findings=[_Finding(severity=severity, description=d) for d in descriptions])
    return _findings_about_a_server_only_the_tests_start(review, str(root))


def test_the_finding_is_kept_and_stops_gating(tmp_path: Path) -> None:
    _project(tmp_path, "node serve.js")

    after = _after(tmp_path, TRAVERSAL, "Deleting a task does nothing.")

    assert [finding.severity for finding in after.findings] == ["minor", "blocking"]
    assert "started by the test runner's own configuration" in after.findings[0].description
    assert TRAVERSAL in after.findings[0].description


def test_a_server_nothing_in_the_tests_starts_is_the_product_s(tmp_path: Path) -> None:
    _project(tmp_path, "npx http-server . -p 3000")

    after = _after(tmp_path, TRAVERSAL)

    assert [finding.severity for finding in after.findings] == ["blocking"]


def test_a_finding_that_also_names_a_product_file_is_left_alone(tmp_path: Path) -> None:
    _project(tmp_path, "node serve.js")

    after = _after(tmp_path, "`serve.js` and `index.html` both expose user input without escaping it.")

    assert [finding.severity for finding in after.findings] == ["blocking"]


def test_a_finding_that_names_no_file_is_left_alone(tmp_path: Path) -> None:
    _project(tmp_path, "node serve.js")

    after = _after(tmp_path, "The server does not validate its input.")

    assert [finding.severity for finding in after.findings] == ["blocking"]
