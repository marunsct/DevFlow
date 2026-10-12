"""A release adds what someone who did not write the product needs to test and ship it.

From the stack pack, because the pack holds the commands the harness actually
ran: the CI pipeline runs exactly those, and a service gets a container that
starts it the way its own start script does. The generators this replaces kept
a second model of every stack and wrote a plaintext password, a root image and
`curl | sh` into the files they made; the same properties are pinned here for
what replaced them.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

import pytest

from app.stacks import pack_named
from app.stacks import release
from app.stacks.packs import ALL_PACKS
from app.stacks.scaffold import scaffold

#: Every pack whose product is a running service: one with an HTTP interface.
SERVICES = {p.name for p in ALL_PACKS if p.kind in {"http_api", "fullstack"}}


def _files(name: str) -> dict[str, str]:
    return release.files_for(pack_named(name), "shop", "Shop", "shop")


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda p: p.name)
def test_every_pack_s_ci_runs_the_commands_the_harness_ran(pack) -> None:
    workflow = release.files_for(pack, "shop", "Shop", "shop")[".github/workflows/shop.yml"]
    commands = pack.commands("shop", "shop")
    ran = re.findall(r'- run: "(.*)"', workflow)
    expected = [shlex.join(argv) for argv in commands["install"]]
    assert ran[: len(expected)] == expected
    assert ran[-2:] == [shlex.join(commands["unit_test"]), shlex.join(commands["acceptance_test"])]
    assert 'working-directory: "shop"' in workflow
    assert pack.ci_setup, "a CI runner needs the pack's runtime set up"
    assert "curl" not in workflow and "| sh" not in workflow


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_a_service_gets_a_container_that_is_safe_by_default(name: str) -> None:
    dockerfile = _files(name)["shop/Dockerfile"]
    user = re.findall(r"^USER (\S+)$", dockerfile, re.M)
    assert user and user[-1] not in {"root", "0"}
    assert not re.search(r"(PASSWORD|SECRET|TOKEN|API_KEY)\s*=", dockerfile)
    # Dependencies before the source, so a code change does not reinstall them.
    assert dockerfile.index("COPY . .") > dockerfile.index("RUN ")
    assert "HOST=0.0.0.0" in dockerfile
    assert "{{" not in dockerfile
    ignored = _files(name)["shop/.dockerignore"]
    assert "data/" in ignored and "acceptance/" in ignored


def test_the_node_container_starts_it_the_way_its_start_script_does() -> None:
    pack = pack_named("node-http-api")
    start = pack.kept_scripts["start"]
    assert f"CMD {[*start.split()]}".replace("'", '"') in _files("node-http-api")["shop/Dockerfile"]


def test_the_python_container_serves_the_product_s_package() -> None:
    assert "uvicorn shop.main:app" in _files("python-http-api")["shop/Dockerfile"]


def test_a_page_a_cli_or_a_library_gets_no_container() -> None:
    for name in {p.name for p in ALL_PACKS} - SERVICES:
        assert not [path for path in _files(name) if "Dockerfile" in path], name


def test_the_services_listen_where_they_are_told() -> None:
    node = pack_named("node-http-api").render("shop", "Shop")["src/index.js"]
    assert "process.env.HOST || '127.0.0.1'" in node
    python = pack_named("python-http-api").render("shop", "Shop", "shop")["start.sh"]
    assert '--host "${HOST:-127.0.0.1}"' in python


def _runner(root: Path, pack):
    def run(argv, category, working_directory):
        commands = pack.commands(working_directory)
        if category == "test":
            unit = list(argv) == commands["unit_test"]
            target = root / working_directory / (pack.unit_report if unit else pack.acceptance_report)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("<testsuites><testcase name='smoke'/></testsuites>")
        return {"returncode": "0", "stdout": "", "stderr": ""}

    return run


def test_the_release_writes_them_once_and_never_over_the_product_s_own(tmp_path: Path) -> None:
    pack = pack_named("node-http-api")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert scaffold(tmp_path, pack, "shop", "Shop", run=_runner(tmp_path, pack)).ok
    (tmp_path / "shop" / "Dockerfile").write_text("FROM scratch\n")

    added = release.write(tmp_path)

    assert added.written == [".github/workflows/shop.yml", "shop/.dockerignore"]
    assert added.kept == ["shop/Dockerfile"]
    assert (tmp_path / "shop" / "Dockerfile").read_text() == "FROM scratch\n"
    assert "not built here" in added.describe()
    # A second release (after a change request) adds nothing and reports
    # only the product's own file.
    again = release.write(tmp_path)
    assert again.written == [] and again.kept == ["shop/Dockerfile"]


def test_a_project_no_pack_scaffolded_gets_nothing_and_the_release_says_so(tmp_path: Path) -> None:
    added = release.write(tmp_path)
    assert added.written == []
    assert "No stack pack covers this product" in added.describe()


def test_packaging_that_fails_is_reported_not_swallowed(tmp_path: Path, monkeypatch) -> None:
    pack = pack_named("node-http-api")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert scaffold(tmp_path, pack, "shop", "Shop", run=_runner(tmp_path, pack)).ok

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(release, "files_for", broken)
    added = release.write(tmp_path)

    assert "failed (OSError: disk full)" in added.describe()
    assert "lacks the CI pipeline" in added.describe()
