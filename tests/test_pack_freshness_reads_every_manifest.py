"""The freshness report reads every version a pack pins, in every manifest it writes.

Node 20 reached end of life and Angular 22 refused it before anything said so.
`scripts/loop/pack_freshness.py` reads each pack's pins and asks each registry
for its current release; first run: 194 pins, 78 a major version behind.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "pack_freshness.py"


@pytest.fixture(scope="module")
def freshness():
    spec = importlib.util.spec_from_file_location("pack_freshness", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FILES = {
    "package.json": '{"dependencies": {"react": "^19.1.0", "local": "file:../x"}, "devDependencies": {"vitest": "~3.2.0"}}',
    "requirements.txt": "fastapi>=0.115,<1\nuvicorn[standard]>=0.30\n",
    "go.mod": "module demo\n\ngo 1.22\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.10.0\n)\n",
    "Cargo.toml": '[package]\nname = "demo"\nversion = "0.1.0"\n\n[dependencies]\naxum = "0.8"\ntokio = { version = "1", features = ["full"] }\n',
    "pom.xml": '<project xmlns="http://maven.apache.org/POM/4.0.0"><parent><groupId>org.springframework.boot</groupId>'
               '<artifactId>spring-boot-starter-parent</artifactId><version>3.4.5</version></parent></project>',
    "composer.json": '{"require": {"php": "^8.2", "slim/slim": "^4.14"}}',
    "Gemfile": 'source "https://rubygems.org"\ngem "sinatra", "~> 4.1"\n',
    "tests/Unit.csproj": '<PackageReference Include="xunit" Version="2.9.2" />',
}


def test_every_manifest_s_pins_are_read(freshness):
    found = {(ecosystem, package, version) for _, ecosystem, package, version in freshness.pins(FILES)}

    assert found == {
        ("npm", "react", "^19.1.0"), ("npm", "vitest", "~3.2.0"),
        ("pypi", "fastapi", "0.115"), ("pypi", "uvicorn", "0.30"),
        ("go", "github.com/gin-gonic/gin", "v1.10.0"),
        ("crates", "axum", "0.8"), ("crates", "tokio", "1"),
        ("maven", "org.springframework.boot:spring-boot-starter-parent", "3.4.5"),
        ("packagist", "slim/slim", "^4.14"),
        ("rubygems", "sinatra", "4.1"),
        ("nuget", "xunit", "2.9.2"),
    }


@pytest.mark.parametrize("pinned, latest, behind", [
    ("^3.2.0", "5.0.4", True),
    ("^19.1.0", "19.2.0", False),
    ("0.115", "0.143.0", True),     # for 0.x the minor is the major
    ("0.8", "0.8.9", False),
    ("v1.10.0", "v1.12.0", False),
    ("^12.0", "v13.35.0", True),
])
def test_a_pin_is_behind_only_by_a_major_version(freshness, pinned, latest, behind):
    assert freshness._behind(pinned, latest) is behind


def test_every_pack_s_files_can_be_read(freshness):
    from app.stacks.packs import ALL_PACKS

    for pack in ALL_PACKS:
        freshness.pins(pack.render("demo-app", "Demo App", "demo_app"))


def test_the_nightly_check_never_runs_beside_a_live_run():
    script = (SCRIPT.parent / "loop.sh").read_text()
    nightly = script[script.index("nightly)"):script.index("suite)")]

    assert "status in ('running','queued','pending')" in nightly
    assert nightly.index("exit 0") < nightly.index("verify_packs.py")
