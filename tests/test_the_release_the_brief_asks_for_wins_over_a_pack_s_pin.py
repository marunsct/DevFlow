"""The release line a brief asks for wins over a stack pack's pinned version (LF.1311).

Found while building the stale-knowledge benchmark family: its brief asks for "Java 21, on Spring Boot 4.2 (the current
release line; not 3.x)", and the Java pack's scaffold wrote its own pin, Spring Boot 3.4.5, whatever the brief said - as
the NestJS pack wrote `^11` with 12 released. The brief's stated version is now read at the scaffold, the newest
release of that line the toolchain runs is written with the pins kept in step, a line the toolchain cannot run is a
stated cause, and a brief that asks for nothing is scaffolded exactly as before.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.graph import acceptance_nodes as nodes
from app.stacks import contract, pack_named, stack_facts, stated_releases, toolchain_fit
from app.stacks.packs import ALL_PACKS
from app.stacks.packs.java_spring_api import SPRING_4_KNOWN_ERRORS
from app.tools import package_registry as pr
from app.tools import release_fit
from tests.workflow_nodes import reported

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CONFIG = {"configurable": {"thread_id": "t"}}
CTX = nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None)
PASSED = "<testsuites><testcase name='smoke'/></testsuites>"

MAVEN = "https://repo1.maven.org/maven2/org/springframework/boot/spring-boot-starter-parent"


def _brief(constraint: str) -> str:
    return f"# Notes API\n\n## Overview\nA small HTTP service.\n\n## Technical Constraints\n- {constraint}\n"


def _maven_registry(java_needed: dict[str, str]) -> dict[str, tuple[int, str]]:
    """Maven Central for the Spring Boot parent: its release list and each release's POM with the Java it sets."""
    listed = "".join(f"<version>{v}</version>" for v in ["3.4.5", "4.0.0", "4.1.3", "4.2.0-RC1", *java_needed])
    pages = {f"{MAVEN}/maven-metadata.xml": (200, f"<metadata><versioning><versions>{listed}</versions></versioning></metadata>")}
    for version, java in java_needed.items():
        pages[f"{MAVEN}/{version}/spring-boot-starter-parent-{version}.pom"] = (
            200, f"<project><properties><java.version>{java}</java.version>"
                 "<maven.compiler.release>${java.version}</maven.compiler.release></properties></project>")
    return pages


def _npm_registry() -> dict[str, tuple[int, str]]:
    """npm for the NestJS packages: an 11 line, a 12 line whose newest differs by package, and a 13 prerelease."""
    newest_12 = {"@nestjs/core": "12.6.0", "@nestjs/common": "12.6.0", "@nestjs/platform-express": "12.5.1",
                 "@nestjs/testing": "12.6.0"}
    pages = {}
    for name, newest in newest_12.items():
        versions = ["11.0.0", "11.2.11", "12.0.0", newest, "13.0.0-alpha.1"]
        pages[f"https://registry.npmjs.org/{name}"] = (200, json.dumps({
            "versions": {v: {"engines": {"node": ">= 20"}} for v in versions},
            "time": {v: "2026-11-01T00:00:00.000Z" for v in versions},
        }))
    return pages


@pytest.fixture
def registry(monkeypatch):
    """The registries stood in for (the network is the edge), with Java 21 and Node 24 here; the URLs asked are kept."""
    pages: dict[str, tuple[int, str]] = {}
    asked: list[str] = []
    monkeypatch.setattr(pr, "_RUNTIMES", {"maven": 'openjdk version "21.0.5" 2024-10-15', "npm": "v24.11.1"})
    for cache in (pr._CACHE, release_fit._CACHE, release_fit._NEEDS):  # noqa: SLF001
        cache.clear()

    def fetch(url, *_a, **_k):
        asked.append(url)
        status, body = pages.get(url, (404, ""))
        return status, body.encode()

    monkeypatch.setattr(pr, "_fetch", fetch)
    yield SimpleNamespace(pages=pages, asked=asked)
    for cache in (pr._CACHE, release_fit._CACHE, release_fit._NEEDS):  # noqa: SLF001
        cache.clear()


def _state(root: Path, pack: str, brief: str) -> dict[str, Any]:
    (root / ".project-directory").write_text("notes\n")
    (root / "notes").mkdir(exist_ok=True)
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "document": SimpleNamespace(text=brief),
        "product_intake": SimpleNamespace(product_name="Notes", success_measures=[]),
        "stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(product_kind="http_api")),
        "stack_pack": pack,
    }


def _scaffolded_by_the_node(tmp_path, monkeypatch, pack: str, brief: str, ok=lambda attempt: True):
    """The scaffold stage as it ships, the scaffold itself recording the pack it was given: (packs given, update)."""
    given = []

    def fake(root, pack, project, title, package=None):
        given.append(pack)
        good = ok(len(given))
        return SimpleNamespace(ok=good, problem="" if good else "the unit smoke test did not compile")

    monkeypatch.setattr("app.stacks.scaffold.scaffold", fake)
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)
    update = nodes.scaffold(_state(tmp_path, pack, brief), CONFIG, CTX)
    return given, update


def _runner(root: Path, fails_when: str = ""):
    """The sandbox stood in for: every command passes, and a smoke test writes a passing report - unless the project's
    manifest holds `fails_when`."""
    def run(argv, category, working_directory):
        if category != "test":
            return {"returncode": "0", "stdout": "", "stderr": ""}
        project = root / working_directory
        if fails_when and fails_when in (project / "pom.xml").read_text():
            return {"returncode": "1", "stdout": "", "stderr": "[ERROR] cannot find symbol WebMvcTest"}
        pack = contract.the_pack(root)[0]
        unit = list(argv) == pack.commands(working_directory)["unit_test"]
        target = project / (pack.unit_report if unit else pack.acceptance_report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(PASSED)
        return {"returncode": "0", "stdout": "", "stderr": ""}

    return run


def _parent_version(pom: str) -> str:
    return re.search(r"<artifactId>spring-boot-starter-parent</artifactId>\s*<version>([^<]+)</version>", pom).group(1)


# --- the line a brief asks for ------------------------------------------------------------------------------------

@pytest.mark.parametrize("pack, text, line", [
    ("java-spring-api", "Java 21, on Spring Boot 4.2 (the current release line; not 3.x)", (4, 2)),
    ("java-spring-api", "Built with spring-boot v4", (4,)),
    ("java-spring-api", "Not Spring Boot 3.x but SpringBoot 4.1.2.", (4, 1, 2)),
    ("java-spring-api", "Spring Boot, any recent release", ()),
    ("java-spring-api", "Java 21 with Spring", ()),
    ("node-nest-api", "TypeScript on NestJS 12", (12,)),
    ("node-nest-api", "Nest.js@12, Node 24", (12,)),
    ("node-nest-api", "NestJS 2026 edition", ()),
])
def test_the_release_line_a_brief_names_beside_a_framework_is_read(pack, text, line) -> None:
    assert stated_releases.asked_line(_brief(text), pack_named(pack).release_families[0]) == line


def test_the_brief_s_constraints_are_read_before_its_overview() -> None:
    brief = "# P\n\n## Overview\nA port of an old Spring Boot 3.2 service.\n\n## Technical Constraints\n- Spring Boot 4\n"

    assert stated_releases.asked_line(brief, pack_named("java-spring-api").release_families[0]) == (4,)


# --- the scaffold writes it -----------------------------------------------------------------------------------------

def test_a_spring_boot_4_2_brief_is_scaffolded_on_4_2_with_its_starters_and_tests_in_step(tmp_path, monkeypatch, registry):
    registry.pages.update(_maven_registry({"4.2.0": "17", "4.2.1": "17", "5.0.0-M1": "21"}))

    given, update = _scaffolded_by_the_node(tmp_path, monkeypatch, "java-spring-api",
                                            _brief("Java 21, on Spring Boot 4.2 (the current release line; not 3.x)"))

    files = given[0].render("notes", "Notes")
    assert _parent_version(files["pom.xml"]) == "4.2.1"
    assert "<artifactId>spring-boot-starter-webmvc</artifactId>" in files["pom.xml"]
    assert "<artifactId>spring-boot-starter-webmvc-test</artifactId>" in files["pom.xml"]
    smoke = "\n".join(given[0].rendered_smoke_files("notes", "Notes").values())
    assert "import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;" in smoke
    assert "tools.jackson" in "\n".join(given[0].golden_example.values())
    assert "4.2.1" in update["decisions"][0]["rationale"]
    sheet = stack_facts.read(tmp_path)
    assert [(e["asked"], e["pinned"], e["pack_pin"]) for e in sheet["stated_releases"]] == [("4.2", "4.2.1", "3.4.5")]


def test_a_nestjs_12_brief_pins_every_nest_package_at_its_own_newest_12_release(tmp_path, monkeypatch, registry):
    registry.pages.update(_npm_registry())

    given, _ = _scaffolded_by_the_node(tmp_path, monkeypatch, "node-nest-api", _brief("TypeScript on NestJS 12"))

    manifest = json.loads(given[0].render("notes", "Notes")["package.json"])
    pinned = {**manifest["dependencies"], **manifest["devDependencies"]}
    assert {name: pinned[name] for name in pinned if name.startswith("@nestjs/")} == {
        "@nestjs/core": "^12.6.0", "@nestjs/common": "^12.6.0", "@nestjs/platform-express": "^12.5.1",
        "@nestjs/testing": "^12.6.0"}
    assert (pinned["rxjs"], pinned["reflect-metadata"]) == ("^7.8.1", "^0.2.2")


@pytest.mark.parametrize("pack", ["java-spring-api", "node-nest-api"])
def test_a_brief_that_names_no_release_is_scaffolded_byte_for_byte_as_the_pack_and_asks_no_registry(
        tmp_path, monkeypatch, registry, pack):
    given, update = _scaffolded_by_the_node(tmp_path, monkeypatch, pack, _brief("Data kept in a JSON file"))

    assert given[0].render("notes", "Notes") == pack_named(pack).render("notes", "Notes")
    assert given[0].rendered_smoke_files("notes", "Notes") == pack_named(pack).rendered_smoke_files("notes", "Notes")
    assert registry.asked == []
    assert "stated_releases" not in stack_facts.read(tmp_path)


def test_the_scaffold_s_files_on_the_asked_release_stay_the_scaffold_s_for_every_later_reading(tmp_path, monkeypatch,
                                                                                                registry):
    """The contract records the versions written, so the stub checks and the kept files read what was written."""
    from app.stacks.scaffold import files_still_as_the_scaffold_wrote_them

    registry.pages.update(_maven_registry({"4.2.1": "17"}))
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner", lambda root: _runner(Path(root)))
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)

    update = nodes.scaffold(_state(tmp_path, "java-spring-api", _brief("Spring Boot 4.2")), CONFIG, CTX)

    assert update["scaffold_result"]["ok"], update["scaffold_result"]["problem"]
    assert _parent_version((tmp_path / "notes" / "pom.xml").read_text()) == "4.2.1"
    assert "notes/pom.xml" in files_still_as_the_scaffold_wrote_them(tmp_path)
    assert contract.enforce(tmp_path) == []


# --- what is said when the line is not built ----------------------------------------------------------------------

def test_a_line_the_toolchain_cannot_run_keeps_the_pack_s_pin_and_is_a_stated_cause(tmp_path, monkeypatch, registry):
    monkeypatch.setenv("STACK_FACTS", "on")
    registry.pages.update(_maven_registry({"5.0.0": "25", "5.0.1": "25"}))

    given, update = _scaffolded_by_the_node(tmp_path, monkeypatch, "java-spring-api", _brief("Spring Boot 5"))

    assert _parent_version(given[0].render("notes", "Notes")["pom.xml"]) == "3.4.5"
    first, = toolchain_fit.with_fit_causes(tmp_path, [reported("The service does not start")])
    cause = first.actual_behavior
    assert toolchain_fit.FIT_CAUSE in cause
    assert all(fact in cause for fact in ("Spring Boot 5", "5.0.1", "java >=25", "21.0.5", "3.4.5"))
    assert "Spring Boot 5" in update["decisions"][0]["rationale"]
    assert any("5.0.1" in gap for gap in stack_facts.release_gaps(tmp_path))


def test_a_line_the_registry_does_not_list_keeps_the_pack_s_pin_and_says_so(tmp_path, monkeypatch, registry):
    registry.pages.update(_maven_registry({"4.2.1": "17"}))

    given, _ = _scaffolded_by_the_node(tmp_path, monkeypatch, "java-spring-api", _brief("Spring Boot 9"))

    assert _parent_version(given[0].render("notes", "Notes")["pom.xml"]) == "3.4.5"
    why = stack_facts.read(tmp_path)["stated_releases"][0]["why"]
    assert "lists no stable 9 release" in why and "4.2.1" in why


def test_a_setup_on_the_asked_line_that_fails_its_smoke_test_is_set_up_on_the_pack_s_pin_and_says_so(
        tmp_path, monkeypatch, registry):
    registry.pages.update(_maven_registry({"4.2.1": "17"}))
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner", lambda root: _runner(Path(root), fails_when="4.2.1"))
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)

    update = nodes.scaffold(_state(tmp_path, "java-spring-api", _brief("Spring Boot 4.2")), CONFIG, CTX)

    assert update["scaffold_result"]["ok"], update["scaffold_result"]["problem"]
    pom = (tmp_path / "notes" / "pom.xml").read_text()
    assert _parent_version(pom) == "3.4.5" and "spring-boot-starter-webmvc" not in pom
    assert "releases" not in contract.read(tmp_path)
    fact, = stack_facts.read(tmp_path)["stated_releases"]
    assert (fact["pinned"], "did not pass its own smoke test" in fact["why"]) == ("3.4.5", True)
    assert "4.2.1" in update["decisions"][0]["rationale"]


# --- who is told ------------------------------------------------------------------------------------------------------

def test_every_fixer_is_told_the_release_the_brief_asks_for_and_what_is_pinned(tmp_path, monkeypatch, registry):
    monkeypatch.setenv("STACK_FACTS", "on")
    registry.pages.update(_maven_registry({"4.2.1": "17"}))
    _scaffolded_by_the_node(tmp_path, monkeypatch, "java-spring-api", _brief("Spring Boot 4.2"))

    told = stack_facts.for_a_fixer(tmp_path)

    assert stated_releases.FIXER_LINE in told and "Spring Boot 4.2" in told and "pinned 4.2.1" in told
    assert "older line does not meet the brief" in told


def test_what_the_choices_say_uses_no_banned_word(tmp_path, monkeypatch, registry):
    monkeypatch.setenv("STACK_FACTS", "on")
    registry.pages.update({**_maven_registry({"4.2.1": "17", "5.0.1": "25"}), **_npm_registry()})
    said = []
    for pack, constraint in (("java-spring-api", "Spring Boot 4.2"), ("java-spring-api", "Spring Boot 5"),
                             ("java-spring-api", "Spring Boot 9"), ("node-nest-api", "NestJS 12")):
        root = tmp_path / f"{pack}-{constraint.split()[-1]}"
        root.mkdir()
        _scaffolded_by_the_node(root, monkeypatch, pack, _brief(constraint))
        said += [stack_facts.for_a_fixer(root), *stack_facts.release_gaps(root),
                 toolchain_fit.with_fit_causes(root, [reported("x")])[0].actual_behavior]
    choice = stated_releases.choose(pack_named("java-spring-api"), _brief("Spring Boot 4.2"), tmp_path)
    said += [stated_releases.fall_back(tmp_path, "notes", "Notes", None, choice, "it failed").said,
             *SPRING_4_KNOWN_ERRORS.values()]

    assert all(text for text in said[:3])
    assert not [text for text in said if BANNED.search(text)]


# --- what the packs declare -------------------------------------------------------------------------------------------

def test_every_pin_a_pack_declares_is_found_in_its_files_on_every_line_it_declares() -> None:
    """A place that matches nothing would leave the pack's pin written whatever the brief asked."""
    missing = []
    for pack in ALL_PACKS:
        for family in pack.release_families:
            for line, variant in {"": None, **family.lines}.items():
                files = {**pack.files, **(variant.files if variant else {})}
                for package, path, _pattern in family.places:
                    if not stated_releases.pinned_in(files, family, package):
                        missing.append(f"{pack.name} {family.title} {line or 'own line'}: {package} in {path}")
    assert {p.name for p in ALL_PACKS if p.release_families} >= {"java-spring-api", "node-nest-api"}
    assert missing == []
