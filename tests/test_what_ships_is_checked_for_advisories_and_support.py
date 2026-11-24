"""Advisories and support dates for what ships, checked after every install (HK.6, LF.1300).

Measured: the harness never saw an advisory for what it shipped - the security reviewer read code with no advisory
data, and the release checked no end of life and no advisory (`reports/research/2026-11-24-agents-that-work-like-a-
team.md`, section (b)); models pick releases with known CVEs in a third to a half of pinned tasks. After an install
resolves, the resolved names and versions now go to OSV in one batch and the runtime and frameworks to endoflife.date;
the findings are kept in the stack facts, given to the security reviewer, and named at release - a known advisory on
a shipped release as a gap naming the fixed release, one on a package for development only as a note, never a block.
The network is the edge: OSV and endoflife.date are stood in for at the lookups' fetch.
"""
from __future__ import annotations

import json
import re

import pytest

from app import completion_verdict
from app.agents.security_reviewer import build_security_review_request
from app.stacks import stack_facts, toolchain_fit
from app.tools import lookups, public_data
from app.tools import package_registry as pr
from app.tools import release_fit

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

ADVISORIES = {
    ("quickserve", "5.5.1"): ["GHSA-q1"],
    ("lintkit", "2.0.0"): ["GHSA-l1"],
}
DETAILS = {
    "GHSA-q1": {"id": "GHSA-q1", "aliases": ["CVE-2026-1111"], "summary": "Path traversal in static file serving",
                "database_specific": {"severity": "HIGH"},
                "affected": [{"package": {"name": "quickserve", "ecosystem": "npm"},
                              "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "5.5.4"}]}]}]},
    "GHSA-l1": {"id": "GHSA-l1", "summary": "Regular expression denial of service",
                "database_specific": {"severity": "CRITICAL"},
                "affected": [{"package": {"name": "lintkit", "ecosystem": "npm"},
                              "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "3.0.0"}]}]}]},
}
PRODUCTS = {"result": [{"name": "nodejs", "label": "Node.js", "aliases": ["node"]},
                       {"name": "quickserve", "label": "QuickServe", "aliases": []}]}
NODE = {"result": {"name": "nodejs", "label": "Node.js", "releases": [
    {"name": "24", "releaseDate": "2025-05-06", "isEol": False, "eolFrom": "2028-04-30", "isMaintained": True,
     "latest": {"name": "24.11.1", "date": "2025-11-11"}},
    {"name": "12", "releaseDate": "2019-04-23", "isEol": True, "eolFrom": "2022-04-30", "isMaintained": False,
     "latest": {"name": "12.22.12", "date": "2022-04-05"}}]}}


class PublicServices:
    """OSV and endoflife.date as the lookups' fetch sees them; every request kept, in order."""

    def __init__(self, *, osv_status: int = 200, osv_headers: dict[str, str] | None = None):
        self.requests: list[str] = []
        self.osv_status, self.osv_headers = osv_status, osv_headers or {}

    def __call__(self, url, headers, body=None):
        self.requests.append(url)
        if url.endswith("/v1/querybatch"):
            if self.osv_status != 200:
                return self.osv_status, "", self.osv_headers
            queries = json.loads(body)["queries"]
            return 200, json.dumps({"results": [
                {"vulns": [{"id": i} for i in ADVISORIES.get((q["package"]["name"], q["version"]), [])]}
                for q in queries]}), {}
        if "/v1/vulns/" in url:
            found = DETAILS.get(url.rsplit("/", 1)[-1])
            return (200, json.dumps(found), {}) if found else (404, "", {})
        if url.endswith("/api/v1/products"):
            return 200, json.dumps(PRODUCTS), {}
        if url.endswith("/api/v1/products/nodejs"):
            return 200, json.dumps(NODE), {}
        if url.endswith("/api/v1/identifiers/purl"):
            return 200, json.dumps({"result": []}), {}
        return 404, "", {}


@pytest.fixture
def services(monkeypatch, tmp_path):
    """The facts on, node 24 here, a fresh breaker and nothing kept from another test."""
    monkeypatch.setenv("STACK_FACTS", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(pr, "_RUNTIMES", {e: "not installed" for e in pr._ECOSYSTEMS} | {"npm": "v24.11.1"})  # noqa: SLF001
    monkeypatch.setattr(pr, "_fetch", lambda url, *a, **k: (404, b""))
    for cache in (pr._CACHE, release_fit._CACHE, release_fit._NEEDS):  # noqa: SLF001
        cache.clear()
    public_data.forget()
    fake = PublicServices()
    monkeypatch.setattr(lookups, "_get", fake)
    yield fake
    public_data.forget()


def _an_install(root):
    """A project whose install resolved one shipped package and one development tool, each with an advisory."""
    app = root / "product" / "app"
    app.mkdir(parents=True)
    (app / "package.json").write_text(json.dumps({"dependencies": {"quickserve": "^5.0.0"},
                                                  "devDependencies": {"lintkit": "^2.0.0"}}))
    (app / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {
        "": {"dependencies": {"quickserve": "^5.0.0"}, "devDependencies": {"lintkit": "^2.0.0"}},
        "node_modules/quickserve": {"version": "5.5.1", "engines": {"node": ">=22"}},
        "node_modules/lintkit": {"version": "2.0.0", "dev": True, "engines": {"node": ">=18"}},
    }}))
    return root / "product", app


def _gaps(root):
    from app.stacks import advisories

    return advisories.release_gaps(root)


def test_after_an_install_the_advisories_of_what_it_resolved_are_kept_with_their_fixed_release(tmp_path, services):
    root, app = _an_install(tmp_path)

    toolchain_fit.after_resolving(root, app)

    found = stack_facts.read(root)["advisories"]["app"]
    assert found["state"] == "known"
    quickserve = next(a for a in found["found"] if a["package"] == "quickserve")
    assert (quickserve["id"], quickserve["severity"], quickserve["fixed"], quickserve["same_major"],
            quickserve["development"]) == ("GHSA-q1", "HIGH", "5.5.4", True, False)
    assert next(a for a in found["found"] if a["package"] == "lintkit")["development"] is True


def test_a_known_advisory_on_a_shipped_release_is_a_release_gap_naming_the_fixed_release(tmp_path, services):
    root, app = _an_install(tmp_path)
    toolchain_fit.after_resolving(root, app)

    shipped = [gap for gap in _gaps(root) if "quickserve" in gap]

    assert len(shipped) == 1 and "GHSA-q1" in shipped[0] and "5.5.4" in shipped[0] and "bump" in shipped[0]
    assert completion_verdict.is_blocking(shipped[0])


def test_an_advisory_on_a_package_for_development_only_is_a_note_never_a_block(tmp_path, services):
    root, app = _an_install(tmp_path)
    toolchain_fit.after_resolving(root, app)

    development = [gap for gap in _gaps(root) if "lintkit" in gap]

    assert len(development) == 1 and "GHSA-l1" in development[0] and "3.0.0" in development[0]
    assert not completion_verdict.is_blocking(development[0])


def test_the_security_reviewer_is_given_the_advisories_and_the_runtime_s_support_window(tmp_path, services):
    root, app = _an_install(tmp_path)
    toolchain_fit.after_resolving(root, app)

    request = build_security_review_request(["app/server.js"], "Permissions: read only.", str(root))
    text = request["messages"][-1]["content"]

    assert "`quickserve` 5.5.1" in text and "GHSA-q1 (high)" in text and "fixed in 5.5.4" in text
    assert re.search(r"development only[^\n]*`lintkit` 2\.0\.0", text)
    assert "never a blocking finding" in text
    assert "Node.js 24: supported until 2028-04-30" in text


def test_a_runtime_past_its_end_of_support_is_named_at_release_as_a_note(tmp_path, services, monkeypatch):
    monkeypatch.setattr(pr, "_RUNTIMES", {e: "not installed" for e in pr._ECOSYSTEMS} | {"npm": "v12.22.0"})  # noqa: SLF001
    root, app = _an_install(tmp_path)
    toolchain_fit.after_resolving(root, app)

    past = [gap for gap in _gaps(root) if gap.startswith("What the product runs on is past its end of support:")]

    assert len(past) == 1 and "Node.js 12" in past[0] and "2022-04-30" in past[0]
    assert not completion_verdict.is_blocking(past[0])


def test_when_osv_cannot_be_reached_the_advisories_are_not_known_and_nothing_blocks(tmp_path, services, monkeypatch):
    tried: list[str] = []

    def offline(url, headers, body=None):
        tried.append(url)
        raise ConnectionError("no network")

    monkeypatch.setattr(lookups, "_get", offline)
    root, app = _an_install(tmp_path)
    toolchain_fit.after_resolving(root, app)
    (app / "package-lock.json").write_text((app / "package-lock.json").read_text().replace("5.5.1", "5.5.2"))

    toolchain_fit.after_resolving(root, app)

    assert sum(url.endswith("/v1/querybatch") for url in tried) == 1
    assert stack_facts.read(root)["advisories"]["app"]["state"].startswith("not known")
    gaps = _gaps(root)
    assert len(gaps) == 1 and gaps[0].startswith("Advisories for what ships are not known:")
    assert completion_verdict.verdict(gaps) == completion_verdict.DELIVERED


def test_a_refusal_holds_osv_and_the_next_install_does_not_ask_it_inside_the_window(tmp_path, monkeypatch, services):
    refusing = PublicServices(osv_status=429, osv_headers={"retry-after": "600"})
    monkeypatch.setattr(lookups, "_get", refusing)
    root, app = _an_install(tmp_path)
    toolchain_fit.after_resolving(root, app)
    (app / "package-lock.json").write_text((app / "package-lock.json").read_text().replace("5.5.1", "5.5.2"))

    toolchain_fit.after_resolving(root, app)

    assert sum(url.endswith("/v1/querybatch") for url in refusing.requests) == 1
    assert "refused" in stack_facts.read(root)["advisories"]["app"]["state"]


def test_the_same_resolved_set_is_not_asked_again(tmp_path, services):
    root, app = _an_install(tmp_path)
    toolchain_fit.after_resolving(root, app)

    toolchain_fit.after_resolving(root, app)

    assert sum(url.endswith("/v1/querybatch") for url in services.requests) == 1


def test_a_name_holding_the_product_s_own_word_is_not_sent(tmp_path, services, monkeypatch):
    root, app = _an_install(tmp_path)
    lock = json.loads((app / "package-lock.json").read_text())
    lock["packages"]["node_modules/product-store"] = {"version": "1.0.0"}
    (app / "package-lock.json").write_text(json.dumps(lock))
    sent: list[str] = []
    original = services.__call__

    def spy(url, headers, body=None):
        if body:
            sent.extend(q["package"]["name"] for q in json.loads(body)["queries"])
        return original(url, headers, body)

    monkeypatch.setattr(lookups, "_get", spy)

    toolchain_fit.after_resolving(root, app)

    assert "quickserve" in sent and "product-store" not in sent


def test_each_request_that_leaves_is_one_outbound_record_and_a_kept_answer_sends_none(tmp_path, services,
                                                                                       monkeypatch):
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "run-advisories")
    root, app = _an_install(tmp_path)
    toolchain_fit.after_resolving(root, app)
    (app / "package-lock.json").write_text((app / "package-lock.json").read_text().replace("2.0.0", "2.0.1"))

    toolchain_fit.after_resolving(root, app)

    lines = (tmp_path / "data" / "transcripts" / "run-advisories.jsonl").read_text().splitlines()
    sent = [r for r in map(json.loads, lines)
            if r.get("kind") == "outbound" and r.get("channel") in {"advisories", "support dates"}]
    asked = [url for url in services.requests if "osv.dev" in url or "endoflife.date" in url]
    assert len(sent) == len(asked)
    assert {(r["channel"], r["to"]) for r in sent} == {("advisories", "api.osv.dev"), ("support dates", "endoflife.date")}
    assert sum("quickserve 5.5.1" in r["sent"] for r in sent) == 2
    assert sum(url.endswith("/v1/vulns/GHSA-q1") for url in services.requests) == 1


def test_the_words_the_reviewer_and_the_release_are_given_use_none_of_the_banned_ones(tmp_path, services):
    root, app = _an_install(tmp_path)
    toolchain_fit.after_resolving(root, app)
    from app.stacks import advisories

    texts = [advisories.for_the_security_reviewer(root), *_gaps(root)]

    assert texts[0] and not any(BANNED.search(text) for text in texts)


def test_with_the_facts_off_nothing_is_asked_and_nothing_is_said(tmp_path, services, monkeypatch):
    monkeypatch.setenv("STACK_FACTS", "off")
    root, app = _an_install(tmp_path)

    toolchain_fit.after_resolving(root, app)

    assert services.requests == [] and _gaps(root) == []
    assert "Advisories and support dates" not in build_security_review_request([], "", str(root))["messages"][-1]["content"]


# --- the readers the check stands on --------------------------------------------------------------------------------

def test_one_advisory_under_two_databases_ids_is_one_entry_with_the_lowest_fix_above_the_release(tmp_path, services,
                                                                                                   monkeypatch):
    from app.tools import osv

    affected = [{"package": {"name": "Some_Lib", "ecosystem": "PyPI"}, "ranges": [{"events": [
        {"introduced": "0"}, {"fixed": "1.0.4"}, {"introduced": "2.0.0"}, {"fixed": "2.0.3"}]}]}]
    monkeypatch.setitem(DETAILS, "PYSEC-9", {"id": "PYSEC-9", "aliases": ["GHSA-q9"], "affected": affected})
    monkeypatch.setitem(DETAILS, "GHSA-q9", {"id": "GHSA-q9", "aliases": ["PYSEC-9"], "affected": affected,
                                             "database_specific": {"severity": "HIGH"}})
    monkeypatch.setitem(ADVISORIES, ("some-lib", "2.0.1"), ["PYSEC-9", "GHSA-q9"])

    found = osv.advisories([osv.Release("pypi", "some-lib", "2.0.1")], tmp_path)

    [entry] = found[osv.Release("pypi", "some-lib", "2.0.1")]
    assert (entry.severity, entry.fixed, entry.same_major) == ("HIGH", "2.0.3", True)


@pytest.mark.parametrize("version, fixed, same", [("1.4.2", "1.4.9", True), ("1.4.2", "2.0.0", False),
                                                  ("0.3.1", "0.3.5", True), ("0.3.1", "0.4.0", False)])
def test_a_fix_in_the_same_major_line_is_a_bump_and_for_a_0_x_release_the_minor_line_is_the_major(version, fixed, same):
    from app.tools import osv

    assert osv.same_major(version, fixed) is same


@pytest.mark.parametrize("files, ecosystem, development, shipped", [
    ({"requirements.txt": "fastapi==0.121.0\n", "requirements-dev.txt": "pytest==8.4.0\nfastapi\n"},
     "pypi", "pytest", "fastapi"),
    ({"pyproject.toml": '[project]\nname="x"\ndependencies=["flask"]\n[dependency-groups]\ndev=["ruff>=0.6"]\n'},
     "pypi", "ruff", "flask"),
    ({"Cargo.toml": '[dependencies]\nserde="1"\n[dev-dependencies]\ninsta="1"\n'}, "crates", "insta", "serde"),
    ({"Gemfile": 'gem "sinatra"\ngroup :development, :test do\n  gem "rspec"\nend\n'}, "rubygems", "rspec", "sinatra"),
    ({"composer.lock": '{"packages":[{"name":"slim/slim"}],"packages-dev":[{"name":"phpunit/phpunit"}]}'},
     "packagist", "phpunit/phpunit", "slim/slim"),
    ({"App.csproj": '<Project><ItemGroup><PackageReference Include="Analyzers.Kit" Version="1.0.0" '
                    'PrivateAssets="all" /><PackageReference Include="Web.Kit" Version="1.0.0" /></ItemGroup></Project>'},
     "nuget", "Analyzers.Kit", "Web.Kit"),
])
def test_each_language_s_development_only_packages_are_told_from_what_ships(tmp_path, files, ecosystem, development,
                                                                            shipped):
    from app.analysis.development_only import development_only

    for file, text in files.items():
        (tmp_path / file).write_text(text)

    found = development_only(tmp_path)

    assert found.holds(ecosystem, development) and not found.holds(ecosystem, shipped)


def test_every_package_of_a_test_project_is_for_development_only(tmp_path):
    from app.analysis.development_only import development_only

    (tmp_path / "App.Tests.csproj").write_text('<Project><ItemGroup><PackageReference Include="Microsoft.NET.Test.Sdk" '
                                               'Version="17.0.0" /></ItemGroup></Project>')

    assert development_only(tmp_path).holds("nuget", "Anything.Transitive")


@pytest.mark.parametrize("ecosystem, package, identifier", [
    ("npm", "@angular/core", "pkg:npm/%40angular/core"),
    ("pypi", "Django", "pkg:pypi/django@5.2"),
    ("maven", "org.springframework.boot:spring-boot", "pkg:maven/org.springframework.boot/spring-boot"),
])
def test_a_package_is_matched_to_its_product_by_the_identifier_endoflife_date_lists(services, monkeypatch, ecosystem,
                                                                                    package, identifier):
    from app.tools import support_dates

    listed = {"result": [{"identifier": "pkg:npm/vue", "product": {"name": "vue"}},
                         {"identifier": identifier, "product": {"name": "the-product"}}]}
    monkeypatch.setattr(lookups, "_get", lambda url, headers, body=None: (200, json.dumps(listed), {}))

    assert support_dates.product_of_package(ecosystem, package) == "the-product"


def test_a_runtime_s_support_is_read_from_the_longest_cycle_its_version_names(services, monkeypatch):
    from app.tools import support_dates

    cycles = {"result": {"name": "python", "label": "Python", "releases": [
        {"name": "3.12", "eolFrom": "2028-10-31", "isEol": False},
        {"name": "3", "eolFrom": "2020-01-01", "isEol": True},
        {"name": "3.11", "eolFrom": "2027-10-31", "isEol": False}]}}
    monkeypatch.setattr(lookups, "_get", lambda url, headers, body=None: (200, json.dumps(cycles), {}))

    entry = support_dates.support("python", "3.12.3")

    assert (entry["cycle"], entry["ends"], entry["ended"]) == ("3.12", "2028-10-31", False)
