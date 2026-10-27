"""A unit test that never settles fails at the runner's per-test limit, not at the sandbox's five minutes.

Measured on one run: a unit test wrapped the promise-based `sqlite` API in callbacks that never fire; its promise never
settled and `node --test` waited until the sandbox's 300-second limit, on every unit run the harness made. Each pack
that runs Node's test runner gives every test a limit, so the hang fails in seconds and names its test.
"""
from __future__ import annotations

import json

import pytest

from app.stacks.packs import ALL_PACKS


def _node_test_scripts():
    found = []
    for pack in ALL_PACKS:
        manifest = (pack.files or {}).get("package.json")
        if not manifest:
            continue
        try:
            scripts = json.loads(manifest.replace("{{project}}", "p").replace("{{title}}", "T").replace("{{package}}", "p")).get("scripts", {})
        except ValueError:
            continue
        for name, script in scripts.items():
            if "node --test" in script or "node --import" in script and "--test" in script:
                found.append((pack.name, name, script))
    return found


def test_there_are_node_test_runner_packs():
    assert _node_test_scripts()


@pytest.mark.parametrize("pack,name,script", _node_test_scripts())
def test_each_gives_every_test_a_limit(pack, name, script):
    assert "--test-timeout=" in script, f"{pack} {name}: {script}"
