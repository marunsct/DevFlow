"""A dependency added to the manifest is installed before the harness measures the product.

Measured live: fast delivery drafted `package.json` with `react-router-dom` in it,
in one model call with no command run after it, and nothing installed it. Every
test round built the page against the scaffold's `node_modules`, the build failed
to resolve the import, and the product "did not start" for the acceptance suite
round after round - while its manifest was right.
"""
from __future__ import annotations

import json

from app.stacks import contract, pack_named
from app.acceptance import suite


def _project(tmp_path):
    pack = pack_named("fullstack-react-fastapi")
    contract.write(tmp_path, pack, "shop", "Shop")
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "package.json").write_text(json.dumps({"dependencies": {"react": "18.3.1"}}))
    (tmp_path / "shop" / "requirements.txt").write_text("fastapi\n")
    return pack


class _Runner:
    def __init__(self):
        self.ran = []

    def __call__(self, argv, category, working_directory):
        self.ran.append((list(argv), category))
        return {"returncode": "0", "stdout": "", "stderr": ""}


def _installs(runner):
    return [argv for argv, category in runner.ran if category == "install"]


def test_a_changed_manifest_is_installed_and_an_unchanged_one_is_not(tmp_path):
    pack = _project(tmp_path)
    runner = _Runner()
    contract.installed(tmp_path, runner)  # as the scaffold left it
    runner.ran.clear()

    contract.install_if_the_manifests_changed(tmp_path, runner)
    assert _installs(runner) == []

    (tmp_path / "shop" / "package.json").write_text(
        json.dumps({"dependencies": {"react": "18.3.1", "react-router-dom": "6.25.0"}})
    )
    contract.install_if_the_manifests_changed(tmp_path, runner)
    assert _installs(runner) == [list(argv) for argv in pack.commands("shop", None)["install"]]

    runner.ran.clear()
    contract.install_if_the_manifests_changed(tmp_path, runner)
    assert _installs(runner) == []


def test_the_suite_installs_a_changed_manifest_before_it_runs(tmp_path):
    _project(tmp_path)
    runner = _Runner()
    contract.installed(tmp_path, runner)
    runner.ran.clear()
    (tmp_path / "shop" / "requirements.txt").write_text("fastapi\nhttpx\n")

    suite.run(tmp_path, runner=runner, save=False)

    categories = [category for _argv, category in runner.ran]
    assert "install" in categories
    if "test" in categories:
        assert categories.index("install") < categories.index("test")


def test_a_failed_install_is_tried_again_next_time(tmp_path):
    _project(tmp_path)
    contract.installed(tmp_path, _Runner())
    (tmp_path / "shop" / "package.json").write_text(json.dumps({"dependencies": {"left-pad": "1.3.0"}}))

    class Failing(_Runner):
        def __call__(self, argv, category, working_directory):
            super().__call__(argv, category, working_directory)
            return {"returncode": "1", "stdout": "", "stderr": "network"}

    contract.install_if_the_manifests_changed(tmp_path, Failing())
    again = _Runner()
    contract.install_if_the_manifests_changed(tmp_path, again)
    assert _installs(again)
