"""A stage that picks or pins a version can ask the registry what is current.

The model served here was trained before Angular 22 needed Node 22.22 and
before Node 24 stopped taking a directory for `node --test`; each cost a run
before anything said so. `look_up_package` asks the registry an ecosystem
installs from - a fixed host per ecosystem, a checked name, never an arbitrary
address - and says which runtime this environment has beside what the package
needs.
"""

from __future__ import annotations

import json
import re

import pytest

from app.tools import package_registry
from app.tools.package_registry import look_up

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(package_registry, "_CACHE", {})
    monkeypatch.setattr(package_registry, "_RUNTIMES", {})
    monkeypatch.setattr(package_registry, "runtime_here", lambda ecosystem: "v24.20.0")


def _serving(pages: dict[str, object], seen: list[str] | None = None):
    def fetch(url: str):
        if seen is not None:
            seen.append(url)
        if url not in pages:
            return 404, b"{}"
        body = pages[url]
        return 200, body if isinstance(body, bytes) else json.dumps(body).encode()

    return fetch


def test_an_npm_package_says_the_runtime_it_needs_and_the_one_here():
    fetch = _serving({"https://registry.npmjs.org/@angular/core/latest": {
        "version": "22.2.2", "engines": {"node": "^22.22.3 || >=24.15.0"},
        "peerDependencies": {"rxjs": "^7.4.0"}, "type": "module",
    }})

    found = look_up("npm", "@angular/core", fetch=fetch)

    assert found["version"] == "22.2.2"
    assert found["needs_runtime"] == {"node": "^22.22.3 || >=24.15.0"}
    assert found["peer_dependencies"] == {"rxjs": "^7.4.0"}
    assert found["this_environment_runs"] == "v24.20.0"


@pytest.mark.parametrize("ecosystem, name, url, page, version", [
    ("python", "fastapi", "https://pypi.org/pypi/fastapi/json",
     {"info": {"version": "0.143.0", "requires_python": ">=3.10"}}, "0.143.0"),
    ("rust", "axum", "https://crates.io/api/v1/crates/axum",
     {"crate": {"max_stable_version": "0.8.9"}, "versions": [{"num": "0.8.9", "rust_version": "1.80"}]}, "0.8.9"),
    ("go", "github.com/BurntSushi/toml", "https://proxy.golang.org/github.com/!burnt!sushi/toml/@latest",
     {"Version": "v1.5.0"}, "v1.5.0"),
    ("kotlin", "io.ktor:ktor-server-core-jvm",
     "https://repo1.maven.org/maven2/io/ktor/ktor-server-core-jvm/maven-metadata.xml",
     b"<metadata><versioning><release>4.0.0-beta1</release><versions><version>3.6.0</version>"
     b"<version>4.0.0-beta1</version></versions></versioning></metadata>", "3.6.0"),
    ("ruby", "sinatra", "https://rubygems.org/api/v1/gems/sinatra.json", {"version": "4.2.1"}, "4.2.1"),
    ("php", "slim/slim", "https://repo.packagist.org/p2/slim/slim.json",
     {"packages": {"slim/slim": [{"version": "5.0.0-RC1"}, {"version": "4.15.1", "require": {"php": "^8.1"}}]}},
     "4.15.1"),
    ("c#", "Serilog", "https://api.nuget.org/v3-flatcontainer/serilog/index.json",
     {"versions": ["4.3.0", "4.3.1-dev-1"]}, "4.3.0"),
])
def test_every_ecosystem_a_pack_builds_in_is_read(ecosystem, name, url, page, version):
    assert look_up(ecosystem, name, fetch=_serving({url: page}))["version"] == version


@pytest.mark.parametrize("name", ["../../etc/passwd", "a b", "x?q=1", "", "@x/../../y"])
def test_a_name_that_could_leave_the_registry_s_path_is_refused(name):
    seen: list[str] = []

    assert "error" in look_up("npm", name, fetch=_serving({}, seen))
    assert seen == []


def test_an_unknown_ecosystem_is_named_with_the_ones_there_are():
    assert "npm, pypi" in look_up("cpan", "Moose", fetch=_serving({}))["error"]


def test_a_missing_package_and_an_unreachable_registry_are_answers_not_crashes():
    assert "no package" in look_up("npm", "nothing-here", fetch=_serving({}))["error"]

    def down(url):
        raise OSError("network unreachable")

    assert "could not be read" in look_up("npm", "react", fetch=down)["error"]


def test_a_second_question_is_answered_from_what_the_first_learned():
    seen: list[str] = []
    fetch = _serving({"https://registry.npmjs.org/vite/latest": {"version": "8.1.0"}}, seen)

    look_up("npm", "vite", fetch=fetch)
    look_up("js", "vite", fetch=fetch)

    assert len(seen) == 1


def test_free_text_from_a_registry_is_cut_short():
    fetch = _serving({"https://registry.npmjs.org/long/latest": {"version": "1.0.0", "description": "x " * 5000}})

    assert len(look_up("npm", "long", fetch=fetch)["description"]) <= package_registry.MAX_TEXT


@pytest.mark.parametrize("build", ["stack_selector", "principal_architect", "specialist"])
def test_the_stages_that_choose_and_build_are_given_it(build, tmp_path):
    from app.agents.principal_architect import create_principal_architect_agent
    from app.agents.specialists import create_specialist_agent
    from app.agents.stack_selector import create_stack_selector_agent
    from app.models import CompatibleChatOpenAI

    model = CompatibleChatOpenAI(model="Qwen3.5-9B-GGUF", api_key="unused", base_url="http://localhost:9/v1")
    agent = {
        "stack_selector": lambda: create_stack_selector_agent(model=model, repo_root=tmp_path),
        "principal_architect": lambda: create_principal_architect_agent(model=model, repo_root=tmp_path),
        "specialist": lambda: create_specialist_agent("backend", model=model, repo_root=tmp_path),
    }[build]()

    assert "look_up_package" in agent.nodes["tools"].bound._tools_by_name


def test_it_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("PACKAGE_LOOKUP_ENABLED", "false")
    assert package_registry.lookup_tools() == []
    monkeypatch.setenv("PACKAGE_LOOKUP_ENABLED", "true")
    assert [t.name for t in package_registry.lookup_tools()] == ["look_up_package"]


def test_its_description_names_no_product():
    tool = package_registry.build_package_lookup_tool()

    assert not BANNED.search(tool.description)
