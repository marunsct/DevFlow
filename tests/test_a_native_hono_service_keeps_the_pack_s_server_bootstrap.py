"""The Node-native Hono pack keeps `src/main.ts`, the file that serves `createApp()`; a stage that rewrites it has it put back.

Measured on three small-model runs: the team rewrote the bootstrap (a host written `127.0.0-1`, a call to a
`startServer` that was not exported, an import of a module that did not exist) and the product did not start for
the first half hour of each; the application is the team's work, the bootstrap that serves it is not.
"""
from __future__ import annotations

from app.stacks import contract, pack_named


def test_the_pack_keeps_its_main_file():
    pack = pack_named("node-hono-native-api")
    assert "src/main.ts" in pack.kept_files
    assert "createApp" in pack.files["src/main.ts"] and "127.0.0.1" in pack.files["src/main.ts"]


def test_a_bootstrap_with_a_wrong_host_is_put_back(tmp_path):
    pack = pack_named("node-hono-native-api")
    contract.write(tmp_path, pack, "notes", "Notes")
    project = tmp_path / "notes"
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.ts").write_text("const hostname = process.env.HOST || '127.0.0-1';\n")

    repairs = contract.enforce(tmp_path)

    assert "127.0.0.1" in (project / "src" / "main.ts").read_text()
    assert any("src/main.ts" in line for line in repairs)
