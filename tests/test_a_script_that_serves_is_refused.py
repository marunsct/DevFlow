"""A script that starts a server is refused like any server command.

One run's QA stage ran `node scripts/serve.mjs` - a stack pack's static server,
which the pack's acceptance configuration starts itself - and the call sat
until its timeout.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import CommandNotAllowed, _a_script_that_serves, validate_command


@pytest.fixture
def project(tmp_path):
    app = tmp_path / "app"
    (app / "scripts").mkdir(parents=True)
    (app / "scripts" / "serve.mjs").write_text("import { createServer } from 'node:http';\ncreateServer(() => {}).listen(port);\n")
    (app / "scripts" / "build.mjs").write_text("console.log('built');\n")
    (app / "tests").mkdir()
    (app / "tests" / "server.test.js").write_text("const s = createServer(); s.listen(0); s.close();\n")
    (app / "main.py").write_text("from http.server import HTTPServer\nHTTPServer(('', 8000), H).serve_forever()\n")
    return tmp_path


def test_a_serving_script_is_named(project) -> None:
    assert _a_script_that_serves(["node", "scripts/serve.mjs"], project) == "scripts/serve.mjs"
    assert _a_script_that_serves(["python3", "main.py"], project) == "main.py"


def test_other_scripts_and_tests_run(project) -> None:
    assert _a_script_that_serves(["node", "scripts/build.mjs"], project) is None
    assert _a_script_that_serves(["node", "tests/server.test.js"], project) is None
    assert _a_script_that_serves(["node", "--test", "scripts/serve.mjs"], project) is None
    assert _a_script_that_serves(["python", "-m", "pytest"], project) is None


def test_the_command_is_refused_before_it_can_hang(project) -> None:
    with pytest.raises(CommandNotAllowed, match="runs until it is stopped"):
        validate_command(["node", "scripts/serve.mjs"], "testing_specialist", project)
