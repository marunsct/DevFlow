"""The versions of the packages the harness's own files import are kept, as its scripts are.

Measured live: a drafted `package.json` pinned `@playwright/test` 1.45.0, `vite`
5.4.2 and `vitest` 2.0.0 over the scaffold's 1.64.0, ^7 and ^3.2. Nothing
installed it at first, so the scaffold's versions kept working; once the
changed manifest was installed, Playwright 1.45 hung under the runtime here
- every acceptance run, even `--list`, timed out with no output - and the
harness's own `playwright.config.js`, `vite.config.ts` and
`serve-acceptance.mjs` ran on a toolchain they were never written for.
"""
from __future__ import annotations

import json

from app.stacks import contract, pack_named


def _scaffolded(tmp_path):
    pack = pack_named("fullstack-react-fastapi")
    contract.write(tmp_path, pack, "shop", "Shop")
    for relative, content in pack.render("shop", "Shop", None).items():
        target = tmp_path / "shop" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return pack, json.loads((tmp_path / "shop" / "package.json").read_text())


def test_a_stage_s_older_toolchain_is_put_back_and_its_own_packages_kept(tmp_path):
    pack, scaffolded = _scaffolded(tmp_path)
    drafted = json.loads(json.dumps(scaffolded))
    drafted.setdefault("dependencies", {})["react-router-dom"] = "6.25.0"
    for section in ("dependencies", "devDependencies"):
        for name in ("@playwright/test", "vite", "vitest"):
            if name in drafted.get(section, {}):
                drafted[section][name] = {"@playwright/test": "1.45.0", "vite": "5.4.2", "vitest": "2.0.0"}[name]
    (tmp_path / "shop" / "package.json").write_text(json.dumps(drafted))

    repairs = contract.enforce(tmp_path)

    now = json.loads((tmp_path / "shop" / "package.json").read_text())
    for section in ("dependencies", "devDependencies"):
        for name in ("@playwright/test", "vite", "vitest"):
            if name in scaffolded.get(section, {}):
                assert now[section][name] == scaffolded[section][name]
    assert now["dependencies"]["react-router-dom"] == "6.25.0"
    assert any("@playwright/test" in repair for repair in repairs)


def test_a_toolchain_left_as_it_was_is_not_touched(tmp_path):
    _pack, scaffolded = _scaffolded(tmp_path)
    before = (tmp_path / "shop" / "package.json").read_text()

    contract.enforce(tmp_path)

    assert json.loads((tmp_path / "shop" / "package.json").read_text()) == json.loads(before)
