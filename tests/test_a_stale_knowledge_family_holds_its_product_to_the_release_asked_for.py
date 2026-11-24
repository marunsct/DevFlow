"""A benchmark family that only outside knowledge can move: a brief asking for a framework's current major line, newer
than a model's training data, with the release named as data in bench.json (plan HK, LF.1309).

Measured before it: every benchmark family already scored full hidden marks, so a lookup, a stack-facts sheet or an
API card could not move a hidden score anywhere; and a product built on the older line a model knows would pass the
same nine hidden tests, so the family's quality set holds the product to the line its brief asks for.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = sorted(p for p in (ROOT / "benchmarks").iterdir()
                  if (p / "bench.json").is_file() and "asked_release" in json.loads((p / "bench.json").read_text()))


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _release_check(family: Path):
    return _module(family / "quality" / "test_built_on_the_release_asked_for.py", f"release_check_{family.name}")


def test_there_is_a_family_built_to_need_outside_knowledge():
    assert [family.name for family in FAMILIES] == ["notes-api-stale-knowledge"]


@pytest.mark.parametrize("family", FAMILIES, ids=lambda p: p.name)
def test_the_brief_asks_for_the_release_its_bench_names_and_nothing_a_person_would_not_write(family):
    spec = json.loads((family / "bench.json").read_text())
    asked = spec["asked_release"]
    brief = (family / "brief.md").read_text()
    constraints = brief.split("## Technical Constraints", 1)[1]

    assert f"{asked['framework']} {asked['major']}" in constraints
    assert asked["latest"].split(".")[0] == asked["major"]
    assert spec["tests_from"] == "notes-api" and spec["held_out_since"]
    assert not re.search(r"\b(?:harness|benchmark|stale|training data|model|lookup)\b", brief, re.I)


@pytest.mark.parametrize("family", FAMILIES, ids=lambda p: p.name)
def test_the_family_s_quality_set_holds_the_brief_s_other_edges_too(family):
    """The notes-api quality set unchanged, beside the release check."""
    ours = family / "quality" / "test_notes_api_quality.py"
    assert ours.read_bytes() == (ROOT / "benchmarks" / "notes-api" / "quality" / "test_notes_api_quality.py").read_bytes()


POM = """<project><modelVersion>4.0.0</modelVersion>
  <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId>
    <version>{parent}</version><relativePath/></parent>
  <properties><java.version>21</java.version></properties>
  <dependencies><dependency><groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webmvc</artifactId></dependency></dependencies>
</project>"""

BOM_BY_PROPERTY = """<project><properties><boot.line>{version}</boot.line></properties>
  <dependencyManagement><dependencies><dependency><groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-dependencies</artifactId><version>${{boot.line}}</version><type>pom</type>
    <scope>import</scope></dependency></dependencies></dependencyManagement></project>"""


@pytest.mark.parametrize("files, on_the_line", [
    ({"pom.xml": POM.format(parent="4.2.0")}, True),
    ({"pom.xml": POM.format(parent="3.4.5")}, False),
    ({"service/pom.xml": BOM_BY_PROPERTY.format(version="4.0.10")}, True),
    ({"service/pom.xml": BOM_BY_PROPERTY.format(version="3.5.3")}, False),
    ({"build.gradle.kts": 'plugins {\n    id("org.springframework.boot") version "4.1.3"\n}\n'}, True),
    ({"build.gradle": "plugins {\n    id 'org.springframework.boot' version '3.5.3'\n}\n"}, False),
], ids=["parent-4", "parent-3", "bom-property-4", "bom-property-3", "gradle-kts-4", "gradle-3"])
def test_a_product_declaring_the_asked_line_passes_the_release_check_and_one_on_an_older_line_does_not(
        tmp_path, files, on_the_line):
    family = ROOT / "benchmarks" / "notes-api-stale-knowledge"
    asked = json.loads((family / "bench.json").read_text())["asked_release"]
    for path, text in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    check = _release_check(family)

    versions = check.declared_versions(tmp_path, asked["ecosystem"], asked["package"])

    assert len(versions) == 1
    assert (check.off_the_line(versions, asked["major"]) == []) is on_the_line


def test_a_product_whose_manifests_declare_nothing_of_the_package_fails_the_release_check(tmp_path):
    family = ROOT / "benchmarks" / "notes-api-stale-knowledge"
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "pom.xml").write_text(POM.format(parent="4.2.0"))

    assert _release_check(family).declared_versions(tmp_path, "maven", "org.springframework.boot") == []


def test_the_scorer_gives_a_quality_set_its_benchmark_s_own_folder(tmp_path, monkeypatch):
    """The release check reads the release asked for from bench.json; the quality set runs in a copy elsewhere."""
    score = _module(ROOT / "scripts" / "bench" / "score.py", "bench_score")
    bench = tmp_path / "bench"
    (bench / "quality").mkdir(parents=True)
    (bench / "bench.json").write_text('{"kind": "http_api", "runner": "pytest", "asked_release": {"major": "4"}}')
    (bench / "quality" / "test_x.py").write_text("def test_x():\n    pass\n")
    work = tmp_path / "work"
    work.mkdir()
    runs = []

    def ran(argv, cwd, env=None, timeout=900):  # the subprocess edge
        runs.append(env)
        Path(next(a for a in argv if a.startswith("--junitxml=")).split("=", 1)[1]).write_text(
            '<testsuite><testcase name="x"/></testsuite>')
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(score, "_run", ran)
    monkeypatch.setattr(score, "_python_runner", lambda: Path("python3"))

    score._the_quality_set(bench, work, "pytest", {"PRODUCT_DIR": str(work / "product")}, [], "http_api")

    assert len(runs) == 1
    assert json.loads((Path(runs[0]["BENCH_DIR"]) / "bench.json").read_text())["asked_release"] == {"major": "4"}
