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


def test_every_measurement_the_harness_runs_installs_first(tmp_path, monkeypatch):
    """Measured live: a fixer's own check after its fix - one acceptance file at a
    time, and the unit run - went through neither the suite's run nor CI's, so the
    manifest it had fixed was measured uninstalled and the defect stayed open."""
    from app.stacks.scaffold import sandbox_runner
    from app.tools.sandbox import SandboxExecutor

    pack = _project(tmp_path)
    contract.installed(tmp_path)
    (tmp_path / "shop" / "package.json").write_text(json.dumps({"dependencies": {"react-router-dom": "6.25.0"}}))
    ran = []
    monkeypatch.setattr(SandboxExecutor, "execute", staticmethod(
        lambda command, **kw: ran.append((list(command), kw["category"])) or {"returncode": 0, "stdout": ""}))

    sandbox_runner(tmp_path)(["npx", "playwright", "test", "acceptance/auth.spec.js"], "probe", "shop")

    installs = [argv for argv, category in ran if category == "install"]
    assert installs == [list(argv) for argv in pack.commands("shop", None)["install"]]
    assert ran[-1] == (["npx", "playwright", "test", "acceptance/auth.spec.js"], "probe")


def test_a_failed_install_says_what_the_installer_said(tmp_path):
    """Measured on one gate run: a JavaScript package written into `requirements.txt` failed every install,
    and the note said only that the command failed."""
    _project(tmp_path)
    runner = _Runner()
    contract.installed(tmp_path, runner)
    (tmp_path / "shop" / "requirements.txt").write_text("fastapi\nrecharts\n")

    def failing(argv, category, working_directory):
        return {"returncode": "1", "stdout": "",
                "stderr": "ERROR: No matching distribution found for recharts\n"}

    notes = contract.install_if_the_manifests_changed(tmp_path, failing)

    assert notes and "No matching distribution found for recharts" in notes[0]


class _FailingRunner:
    def __init__(self, said):
        self.said = said

    def __call__(self, argv, category, working_directory):
        return {"returncode": "1", "stdout": "", "stderr": self.said}


def test_a_pinned_version_the_registry_lacks_comes_back_with_the_one_it_has(tmp_path, monkeypatch):
    """Measured: a fixer pinned `async-mutex@^2.3.0`; every rewrite from the installer's message pinned another missing
    version, because the message names the missing one and not the existing ones."""
    from app.tools import package_registry

    _project(tmp_path)
    (tmp_path / "shop" / "package.json").write_text(json.dumps({"dependencies": {"async-mutex": "^2.3.0"}}))
    monkeypatch.setattr(package_registry, "enabled", lambda: True)
    asked = []
    monkeypatch.setattr(package_registry, "look_up",
                        lambda ecosystem, name, **kw: asked.append((ecosystem, name)) or {"version": "0.5.0"})
    said = ("npm error code ETARGET\nnpm error notarget No matching version found for async-mutex@^2.3.0.\n"
            "npm error notarget In most cases you or one of your dependencies are requesting a package version that "
            "doesn't exist.")

    notes = contract.install_if_the_manifests_changed(tmp_path, _FailingRunner(said))

    assert asked == [("npm", "async-mutex")]
    assert len(notes) == 1 and contract.INSTALL_FAILED in notes[0] and "No matching version found" in notes[0]
    assert "current release of `async-mutex` is 0.5.0" in notes[0]


def test_a_scoped_package_and_a_python_requirement_are_looked_up_too():
    found = []
    from app.stacks.contract import _NO_SUCH_VERSION

    for ecosystem, pattern in _NO_SUCH_VERSION:
        found += [(ecosystem, name) for name in pattern.findall(
            "npm notarget No matching version found for @hono/node-server@^9.0.0.\n"
            "ERROR: No matching distribution found for fastapi==99.0\n"
            "ERROR: Could not find a version that satisfies the requirement uvicorn==99 (from versions: 0.1)")]
    assert ("npm", "@hono/node-server") in found
    assert ("pypi", "fastapi") in found and ("pypi", "uvicorn") in found


def test_the_note_goes_without_the_lookup_when_the_registry_cannot_be_read(tmp_path, monkeypatch):
    from app.tools import package_registry

    _project(tmp_path)
    (tmp_path / "shop" / "package.json").write_text(json.dumps({"dependencies": {"x": "^9"}}))
    monkeypatch.setattr(package_registry, "enabled", lambda: True)
    monkeypatch.setattr(package_registry, "look_up", lambda *a, **k: {"error": "no registry"})

    notes = contract.install_if_the_manifests_changed(
        tmp_path, _FailingRunner("npm error notarget No matching version found for x@^9."))

    assert len(notes) == 1 and "current release" not in notes[0]


def test_the_versions_that_exist_survive_the_cut_a_defect_makes_of_the_note(tmp_path, monkeypatch):
    """The defect built from the note keeps its first 900 characters; with several missing versions the registry's
    answers, written after the installer's own lines, were cut off before the last of them."""
    from app.tools import package_registry

    _project(tmp_path)
    (tmp_path / "shop" / "package.json").write_text(json.dumps({"dependencies": {"a-lib": "^9"}}))
    monkeypatch.setattr(package_registry, "enabled", lambda: True)
    monkeypatch.setattr(package_registry, "look_up", lambda ecosystem, name, **kw: {"version": "0.5.0"})
    said = ("npm warn ERESOLVE overriding peer dependency\n" * 40
            + "".join(f"npm error notarget No matching version found for library-number-{n}@^9.0.0.\n" for n in range(1, 4)))

    note = contract.install_if_the_manifests_changed(tmp_path, _FailingRunner(said))[0]

    assert "current release of `library-number-3` is 0.5.0" in note[:900]
