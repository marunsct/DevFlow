"""Stack selection and architecture on evidence: a row of facts per candidate, and the row each decision relied on
(HK.8, LF.1301).

Measured: the stack selector was offered registry, documentation and web tools and called none of them in 24 runs, so
it chose from training data; the architect read registry releases but no support window and no advisory; nothing
anywhere said whether a candidate's current release fits this environment's toolchain (`reports/research/2026-11-24-
agents-that-work-like-a-team.md`, section (b)). The harness now reads, per candidate, the current release and its date,
the support window, the open advisories, the toolchain fit and whether a pack scaffolds it, and puts one table in front
of the selector and the architect; each decision record naming a candidate records the row it relied on. The
registries, OSV and endoflife.date are stood in for at their fetch.
"""
from __future__ import annotations

import json
import re

import pytest

from app.agents.principal_architect import ArchitectureDecisionRecord, TechnicalSpecificationOutput
from app.agents.research_brief import research_notes
from app.agents.tools_models import TechnologyChoice, TechnologyStack, ToolsAndModelsOutput
from app.stacks import stack_facts
from app.tools import lookups, public_data
from app.tools import package_registry as pr
from app.tools import release_fit

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

PYPI = {
    "fastapi": {"info": {"version": "0.121.0", "requires_python": ">=3.8"},
                "releases": {"0.121.0": [{"requires_python": ">=3.8", "upload_time_iso_8601": "2026-10-02T10:00:00Z"}],
                             "0.120.0": [{"requires_python": ">=3.8", "upload_time_iso_8601": "2026-09-01T10:00:00Z"}]}},
    "flask": {"info": {"version": "3.1.2", "requires_python": ">=3.9"},
              "releases": {"3.1.2": [{"requires_python": ">=3.9", "upload_time_iso_8601": "2025-08-19T10:00:00Z"}]}},
}
ADVISORIES = {("flask", "3.1.2"): ["GHSA-f1"]}
DETAILS = {"GHSA-f1": {"id": "GHSA-f1", "summary": "Session cookie set without its secure flag",
                       "database_specific": {"severity": "MODERATE"},
                       "affected": [{"package": {"name": "flask", "ecosystem": "PyPI"},
                                     "ranges": [{"events": [{"introduced": "0"}, {"fixed": "3.1.3"}]}]}]}}
PRODUCTS = {"result": [{"name": "postgresql", "label": "PostgreSQL", "aliases": ["postgres"]},
                       {"name": "python", "label": "Python", "aliases": []}]}
POSTGRESQL = {"result": {"name": "postgresql", "label": "PostgreSQL", "releases": [
    {"name": "18", "releaseDate": "2025-09-25", "isEol": False, "eolFrom": "2030-11-14", "isMaintained": True},
    {"name": "17", "releaseDate": "2024-09-26", "isEol": False, "eolFrom": "2029-11-08", "isMaintained": True}]}}


def _public_data(*, osv_reachable: bool = True):
    def fetch(url, headers, body=None):
        if "api.osv.dev" in url and not osv_reachable:
            raise ConnectionError("no network")
        if url.endswith("/v1/querybatch"):
            return 200, json.dumps({"results": [
                {"vulns": [{"id": i} for i in ADVISORIES.get((q["package"]["name"], q["version"]), [])]}
                for q in json.loads(body)["queries"]]}), {}
        if "/v1/vulns/" in url:
            return 200, json.dumps(DETAILS[url.rsplit("/", 1)[-1]]), {}
        if url.endswith("/api/v1/products"):
            return 200, json.dumps(PRODUCTS), {}
        if url.endswith("/api/v1/products/postgresql"):
            return 200, json.dumps(POSTGRESQL), {}
        if url.endswith("/api/v1/identifiers/purl"):
            return 200, json.dumps({"result": [{"identifier": "pkg:pypi/django", "product": {"name": "django"}}]}), {}
        return 404, "", {}

    return fetch


@pytest.fixture
def evidence(monkeypatch, tmp_path):
    """The facts on, python 3.12 here, PyPI, OSV and endoflife.date stood in for."""
    monkeypatch.setenv("STACK_FACTS", "on")
    monkeypatch.setenv("DOCS_LOOKUP_ENABLED", "off")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(pr, "_RUNTIMES", {e: "not installed" for e in pr._ECOSYSTEMS} | {"pypi": "Python 3.12.3"})  # noqa: SLF001
    for cache in (pr._CACHE, release_fit._CACHE, release_fit._NEEDS):  # noqa: SLF001
        cache.clear()
    public_data.forget()

    def registry(url, *_a, **_k):
        name = url.split("/pypi/", 1)[-1].split("/", 1)[0]
        return (200, json.dumps(PYPI[name]).encode()) if "pypi.org" in url and name in PYPI else (404, b"")

    monkeypatch.setattr(pr, "_fetch", registry)
    monkeypatch.setattr(lookups, "_get", _public_data())
    yield
    for cache in (pr._CACHE, release_fit._CACHE, release_fit._NEEDS):  # noqa: SLF001
        cache.clear()
    public_data.forget()


def _choice(name, alternative, category="framework"):
    return TechnologyChoice(category=category, name=name, capability="", compatibility="", quality="", latency="",
                            cost="", privacy="", licensing="", operational_burden="", alternative=alternative,
                            replacement_criteria="")


STACK = TechnologyStack(language="Python", framework="FastAPI", frontend_framework="", database="PostgreSQL",
                        testing_framework="pytest")
COMPARISON = ToolsAndModelsOutput(
    frameworks=[_choice("FastAPI (Python)", "Flask - simpler, fewer batteries")],
    storage_options=[_choice("PostgreSQL", "none", category="storage")],
    technology_stack=STACK,
)


def _row(text, candidate):
    return next(line for line in text.splitlines() if line.startswith(f"| {candidate} |"))


def test_the_stack_selector_is_given_a_row_of_evidence_for_each_candidate(tmp_path, evidence):
    from app.stacks.stack_evidence import for_the_selector

    text = for_the_selector(COMPARISON, tmp_path)

    fastapi = _row(text, "FastAPI")
    assert "pypi `fastapi`" in fastapi and "0.121.0 (2026-10-02)" in fastapi and "none known" in fastapi
    assert "python 3.12.3" in fastapi and "yes (" in fastapi
    flask = _row(text, "Flask")
    assert "3.1.2 (2025-08-19)" in flask and "GHSA-f1 (medium, fixed in 3.1.3)" in flask
    postgres = _row(text, "PostgreSQL")
    assert "PostgreSQL 18: supported until 2030-11-14" in postgres
    assert "none" not in [line.split(" | ")[0].strip("| ").lower() for line in text.splitlines()]


def test_a_source_that_cannot_be_read_says_not_known_never_none_known(tmp_path, evidence, monkeypatch):
    from app.stacks.stack_evidence import for_the_selector

    monkeypatch.setattr(lookups, "_get", _public_data(osv_reachable=False))

    fastapi = _row(for_the_selector(COMPARISON, tmp_path), "FastAPI")

    assert "not known" in fastapi and "none known" not in fastapi


def test_the_architect_is_given_the_chosen_stack_s_evidence_and_told_to_cite_its_row(tmp_path, evidence):
    notes = research_notes(STACK, "", None, root=tmp_path)

    assert "--- Evidence for the chosen stack" in notes
    assert "0.121.0 (2026-10-02)" in _row(notes, "FastAPI")
    assert "PostgreSQL 18: supported until 2030-11-14" in _row(notes, "PostgreSQL")
    assert "`validation_evidence`" in notes and "cite the row" in notes


def _a_specification(*records):
    return TechnicalSpecificationOutput.model_construct(decisions=list(records))


def test_each_decision_naming_a_candidate_records_the_row_it_relied_on(tmp_path, evidence):
    from app.stacks.stack_evidence import for_the_selector, with_the_rows_relied_on

    for_the_selector(COMPARISON, tmp_path)
    web = ArchitectureDecisionRecord(title="Web framework", context="", decision="Use FastAPI for the service",
                                     rationale="", validation_evidence="Its own tests.")
    layout = ArchitectureDecisionRecord(title="Folders", context="", decision="One package per layer", rationale="")

    recorded = with_the_rows_relied_on(_a_specification(web, layout), tmp_path).decisions

    assert recorded[0].validation_evidence.startswith("Its own tests.\nEvidence relied on")
    assert "0.121.0 (2026-10-02)" in recorded[0].validation_evidence
    assert "Flask" not in recorded[0].validation_evidence
    assert recorded[1].validation_evidence == ""


def test_a_decision_recorded_again_does_not_cite_its_row_twice(tmp_path, evidence):
    from app.stacks.stack_evidence import for_the_selector, with_the_rows_relied_on

    for_the_selector(COMPARISON, tmp_path)
    once = with_the_rows_relied_on(_a_specification(ArchitectureDecisionRecord(
        title="Database", context="", decision="PostgreSQL", rationale="")), tmp_path)

    twice = with_the_rows_relied_on(once, tmp_path)

    assert twice.decisions[0].validation_evidence.count("Evidence relied on") == 1


def test_the_words_the_selector_and_the_architect_are_given_use_none_of_the_banned_ones(tmp_path, evidence):
    from app.stacks.stack_evidence import for_the_selector

    texts = [for_the_selector(COMPARISON, tmp_path), research_notes(STACK, "", None, root=tmp_path)]

    assert all(texts) and not any(BANNED.search(text) for text in texts)


def test_with_the_facts_off_the_requests_and_the_decisions_are_as_before(tmp_path, evidence, monkeypatch):
    from app.stacks.stack_evidence import for_the_selector, with_the_rows_relied_on

    monkeypatch.setenv("STACK_FACTS", "off")
    specification = _a_specification(ArchitectureDecisionRecord(title="Web", context="", decision="FastAPI",
                                                                rationale=""))

    assert for_the_selector(COMPARISON, tmp_path) == ""
    assert with_the_rows_relied_on(specification, tmp_path) is specification
    assert not (tmp_path / stack_facts.SHEET).exists()
