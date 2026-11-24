"""A stuck fixer's lookup is done the way a person does it (plan HK.3, LF.1295).

Measured before it: the stuck lookup sent one long line to Stack Overflow first, searched GitHub's issues across all
of GitHub by comment count, and handed the fixer three raw leads whose excerpt was the reporter's question; nothing
checked the versions a lead was about, an empty search was asked again by every run, and 2 of 9 looked-up defects
were fixed afterwards. Now: the installed package's own files first, several short queries, the library's own tracker
by relevance, the resolution read, a ranking by source, version and recency, behind one switch a condensed note whose
versions the harness checks, and "nothing found" remembered for a day.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from app.graph import stuck_lookup
from app.tools import lookups

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
RUST = SimpleNamespace(language="Rust", framework="Axum")
STUCK_RUST = ("error[E0599]: no method named `fetch_optional` found for struct `sqlx::query::QueryAs` in the current "
              "scope")

ISSUE_LEAD = {"items": [{"title": "E0599 on fetch_optional", "state": "closed", "comments": 4,
                         "html_url": "https://github.com/launchbadge/sqlx/issues/3",
                         "closed_at": "2026-03-02T10:00:00Z", "body": "I get E0599 when I call fetch_optional."}]}
ISSUE = {"title": "E0599 on fetch_optional", "state": "closed", "closed_at": "2026-03-02T10:00:00Z",
         "created_at": "2026-03-01T09:00:00Z", "html_url": "https://github.com/launchbadge/sqlx/issues/3",
         "user": {"login": "reporter"}, "body": "I get E0599 when I call fetch_optional."}
COMMENTS = [{"body": "Bring the `Executor` trait into scope; fixed in 0.8.3.", "author_association": "MEMBER",
             "created_at": "2026-03-02T09:58:00Z", "user": {"login": "maintainer"}}]


@pytest.fixture(autouse=True)
def _on(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("STUCK_LOOKUP_CONDENSED", raising=False)
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "on")
    for variable in ("STACKEXCHANGE_KEY", "GITHUB_TOKEN", "LOOKUP_ORDER", "LOOKUP_DAILY_CAPS"):
        monkeypatch.delenv(variable, raising=False)
    stuck_lookup._DONE.clear()  # noqa: SLF001
    yield
    stuck_lookup._DONE.clear()  # noqa: SLF001


def _stuck(error: str) -> SimpleNamespace:
    return SimpleNamespace(description="The product does not build.", actual_behavior=error,
                           attempts=[{"stage": "defect_fix_1_0", "outcome": "left open"}])


def _rust_workspace(root: Path, released: str = "2025-07-05") -> Path:
    """A Rust project that declares sqlx, whose stack facts give the release it runs and its repository."""
    workspace = root / "workspace-r"
    (workspace / ".harness").mkdir(parents=True)
    (workspace / ".harness" / "dependency-gate.json").write_text(json.dumps({"crates:sqlx": {"verdict": "allowed"}}))
    (workspace / ".harness" / "stack-facts.json").write_text(json.dumps({"dependencies": [
        {"name": "sqlx", "version": "0.8.2", "released": released, "homes": ["https://github.com/launchbadge/sqlx"]}]}))
    return workspace


class Sites:
    """The outside sources as recorded: what each request asked, and the answers chosen per test."""

    def __init__(self, answers=None):
        self.sent: list[str] = []
        self.answers = answers or {}

    def __call__(self, url, headers, body=None):
        self.sent.append(url)
        for marker, answer in self.answers.items():
            if marker in url:
                return 200, json.dumps(answer(url) if callable(answer) else answer), {}
        return 200, json.dumps({"items": []}), {}

    def queries(self, host: str) -> list[str]:
        return [parse_qs(urlsplit(u).query).get("q", [""])[0] for u in self.sent if host in u and "search" in u]


@pytest.fixture
def sites(monkeypatch):
    def install(answers=None) -> Sites:
        recorded = Sites(answers)
        monkeypatch.setattr(lookups, "_get", recorded)
        return recorded
    return install


# --- (a) local truth before the web -------------------------------------------------------------------------------

def test_a_name_the_installed_package_does_not_have_is_answered_from_its_own_files_without_asking_the_web(
        tmp_path, sites):
    site = sites()
    workspace = tmp_path / "workspace-p"
    package = workspace / ".venv" / "lib" / "python3.12" / "site-packages" / "fastclient"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("def make_client():\n    pass\n\ndef close_client():\n    pass\n")
    info = package.parent / "fastclient-2.0.1.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Name: fastclient\nVersion: 2.0.1\n\n## 2.0.0\n- `create_client` is now `make_client`\n")

    shown = stuck_lookup.section(workspace, _stuck(
        "ImportError: cannot import name 'create_client' from 'fastclient'"), SimpleNamespace(language="Python",
                                                                                             framework="FastAPI"))

    assert "`make_client`" in shown and "2.0.1" in shown, shown
    assert "2.0.0: - `create_client` is now `make_client`" in shown, "the changelog line under its release"
    assert site.sent == [], "nothing is asked of the web when the package's own files answer"
    assert not BANNED.search(shown)


def test_a_type_script_member_the_package_does_not_export_is_named_with_the_ones_it_does(tmp_path):
    from app.analysis import installed_packages

    package = tmp_path / "node_modules" / "hono"
    (package / "dist").mkdir(parents=True)
    (package / "package.json").write_text(json.dumps(
        {"version": "4.6.1", "exports": {"./testing": {"types": "./dist/testing.d.ts"}}}))
    (package / "dist" / "testing.d.ts").write_text("export declare const testClient: any;\n")
    (package / "CHANGELOG.md").write_text("# Changes\n## v4.0.0\n- removed `createClient`, use `testClient`\n")

    found = installed_packages.answer(tmp_path, "error TS2305: Module '\"hono/testing\"' has no exported member "
                                                "'createClient'.")

    assert found is not None and found.version == "4.6.1"
    assert "`testClient`" in found.as_text() and "4.0.0: - removed `createClient`" in found.as_text()


# --- (b) and (c) several short queries, the library's own tracker first --------------------------------------------

def test_short_queries_go_to_the_library_s_own_tracker_by_relevance_first_and_stop_at_the_first_answer(
        tmp_path, sites):
    site = sites({"api.github.com/search/issues": lambda url: ISSUE_LEAD if "fetch_optional" in url else {"items": []}})

    shown = stuck_lookup.section(_rust_workspace(tmp_path), _stuck(STUCK_RUST), RUST)

    asked = site.queries("api.github.com")
    assert urlsplit(site.sent[0]).hostname == "api.github.com", "the tracker before Stack Exchange"
    assert asked[0].startswith("E0599 sqlx") and all("repo:launchbadge/sqlx" in q for q in asked), asked
    assert all(len(q.replace(" repo:launchbadge/sqlx is:issue", "")) <= 110 for q in asked), asked
    assert len(asked) == 2 and "fetch_optional" in asked[1], "the next query only after the first found nothing"
    assert not any("sort=" in u for u in site.sent if "search/issues" in u), "by relevance"
    assert "launchbadge/sqlx/issues/3" in shown


def test_a_release_older_than_two_years_asks_stack_exchange_before_the_tracker(tmp_path, sites):
    site = sites()

    stuck_lookup.section(_rust_workspace(tmp_path, released="2019-01-01"), _stuck(STUCK_RUST), RUST)

    assert urlsplit(site.sent[0]).hostname == "api.stackexchange.com"


# --- (d) the resolution, not the question ---------------------------------------------------------------------------

def test_an_issue_lead_carries_the_maintainer_s_resolution_not_the_reporter_s_question(tmp_path, sites):
    sites({"search/issues": ISSUE_LEAD, "/repos/launchbadge/sqlx/issues/3/comments": COMMENTS,
           "/repos/launchbadge/sqlx/issues/3": ISSUE})

    shown = stuck_lookup.section(_rust_workspace(tmp_path), _stuck(STUCK_RUST), RUST)

    assert "Resolution (maintainer, 2026-03-02): Bring the `Executor` trait into scope; fixed in 0.8.3." in shown, shown
    assert "I get E0599 when I call" not in shown


# --- (e) ranked as people rank --------------------------------------------------------------------------------------

def test_leads_are_ranked_own_source_then_version_then_recency_then_votes():
    from app.graph.stuck_research import Evidence, ranked

    found = Evidence(error="x", library="sqlx", version="0.8.2", repository="launchbadge/sqlx")
    leads = [
        {"url": "https://stackoverflow.com/q/1", "title": "old", "excerpt": "use 0.5", "date": "2019-01-01",
         "score": "90"},
        {"url": "https://stackoverflow.com/q/2", "title": "new", "excerpt": "since 0.8.1 call it so",
         "date": "2026-01-01", "score": "3"},
        {"url": "https://github.com/someone/else/issues/4", "title": "recent", "excerpt": "x", "date": "2026-02-01"},
        {"url": "https://github.com/launchbadge/sqlx/issues/3", "title": "own", "excerpt": "x", "date": "2024-01-01"},
    ]

    order = [lead["title"] for lead in ranked(leads, found)]

    assert order == ["own", "new", "recent", "old"]


# --- (f) and (g) one condensed note behind its switch, the versions checked by the harness --------------------------

class Model:
    """The fixer's model: answers with `reply`, and keeps what it was asked."""

    def __init__(self, reply: dict):
        self.reply, self.asked = reply, []

    def invoke(self, messages, **_kwargs):
        from langchain_core.messages import AIMessage

        self.asked.append(messages)
        return AIMessage(content="```json\n" + json.dumps(self.reply) + "\n```")


def _a_fixer_with_a_lead(tmp_path, sites, model):
    sites({"search/issues": ISSUE_LEAD, "/repos/launchbadge/sqlx/issues/3/comments": COMMENTS,
           "/repos/launchbadge/sqlx/issues/3": ISSUE})
    return stuck_lookup.for_a_fixer(_rust_workspace(tmp_path), _stuck(STUCK_RUST), [], RUST, round_=1, model=model)


def test_switched_off_the_leads_are_shown_and_the_model_is_not_called(tmp_path, sites):
    model = Model({"applies": True})

    shown = _a_fixer_with_a_lead(tmp_path, sites, model)

    assert "What others found for this error" in shown and not model.asked


def test_switched_on_one_call_gives_a_checked_note_instead_of_the_leads(tmp_path, sites, monkeypatch):
    monkeypatch.setenv("STUCK_LOOKUP_CONDENSED", "on")
    model = Model({"applies": True, "cause": "The `Executor` trait is not in scope.",
                   "change": "Add `use sqlx::Executor;` where the query runs.", "versions": "sqlx 0.7",
                   "source": "1"})

    shown = _a_fixer_with_a_lead(tmp_path, sites, model)

    request = model.asked[0][-1].content
    assert len(model.asked) == 1 and "does not run" in request and "0.8.2" in request
    assert "A note on this error, condensed from what others found" in shown
    assert "Change: Add `use sqlx::Executor;` where the query runs." in shown
    assert "another release line (0.7)" in shown and "0.8.2" in shown, "the harness labels another major line"
    assert "Resolution (maintainer" not in shown, "the raw leads no longer enter the request"
    assert not BANNED.search(shown + request + model.asked[0][0].content)


def test_a_note_that_does_not_apply_says_so_and_carries_no_change(tmp_path, sites, monkeypatch):
    monkeypatch.setenv("STUCK_LOOKUP_CONDENSED", "on")

    shown = _a_fixer_with_a_lead(tmp_path, sites, Model({"applies": False}))

    assert "none of it applies to this project" in shown and "Change:" not in shown


@pytest.mark.parametrize(("versions", "runs", "another"), [
    ("sqlx 0.7", "0.8.2", "0.7"), ("bcrypt >= 4.1", "4.2.0", ""), ("fixed in 5.0.0", "4.2.0", "5"), ("", "4.2.0", ""),
])
def test_the_harness_names_another_release_line_than_the_one_the_project_runs(versions, runs, another):
    from app.graph.stuck_research import Evidence, another_line

    assert another_line(versions, Evidence(error="x", library="lib", version=runs)) == another


# --- (h) nothing found is remembered; each note is recorded ---------------------------------------------------------

def test_an_error_nobody_wrote_about_is_not_asked_again_by_the_next_run(tmp_path, sites):
    first = sites()
    stuck_lookup.section(_rust_workspace(tmp_path), _stuck(STUCK_RUST), RUST)
    stuck_lookup._DONE.clear()  # noqa: SLF001 - the next run in this process
    second = sites()

    stuck_lookup.section(_rust_workspace(tmp_path / "next"), _stuck(STUCK_RUST), RUST)

    assert first.sent and not [u for u in second.sent if "search" in u], second.sent


def test_each_note_is_recorded_with_its_id_its_sources_and_its_defect(tmp_path, sites, monkeypatch):
    recorded = []
    monkeypatch.setattr("app.observability.transcript.record", lambda *a, **k: recorded.append(k))
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "run-x")
    sites({"search/issues": ISSUE_LEAD})
    workspace = _rust_workspace(tmp_path)

    shown = stuck_lookup.section(workspace, _stuck(STUCK_RUST), RUST)

    notes = [json.loads(line) for line in (workspace / ".harness" / "research" / "notes.jsonl").read_text().splitlines()]
    note = notes[-1]
    ledger = [r for r in recorded if r.get("event") == "lookup"]
    assert note["id"] and f"(note {note['id']})" in shown and note["defect_id"]
    assert [s["url"] for s in note["sources"]] == ["https://github.com/launchbadge/sqlx/issues/3"]
    assert note["verdict"] == "leads" and note["queries"][0].startswith("E0599 sqlx")
    assert ledger and ledger[-1]["note"] == note["id"] and ledger[-1]["defect_id"] == note["defect_id"]
    assert ledger[-1]["sources"] == ["https://github.com/launchbadge/sqlx/issues/3"] and ledger[-1]["verdict"] == "leads"


def test_a_fixer_that_is_not_stuck_is_unchanged(tmp_path, sites):
    site = sites()
    workspace = _rust_workspace(tmp_path)

    shown = stuck_lookup.section(workspace, SimpleNamespace(description="x", actual_behavior=STUCK_RUST,
                                                            attempts=[]), RUST)

    assert shown == "" and not site.sent and not (workspace / ".harness" / "research").exists()


def test_across_all_of_github_the_error_s_message_is_asked_as_one_phrase(sites):
    """Measured on the replay set: asked as loose words, "password cannot be longer than 72 bytes" found issue #72 of
    unrelated projects."""
    site = sites()

    lookups.look_up("ValueError: password cannot be longer than 72 bytes, truncate manually if necessary", "python")

    assert site.queries("api.github.com") == ['"password cannot be longer than 72 bytes" is:issue']


def test_the_library_s_tracker_asked_first_leaves_room_for_stack_exchange(sites):
    issues = {"items": [{"title": f"issue {n}", "state": "closed", "html_url": f"https://github.com/o/lib/issues/{n}",
                         "body": "x"} for n in range(3)]}
    question = {"items": [{"title": "q", "link": "https://stackoverflow.com/q/9", "accepted_answer_id": 4,
                           "last_activity_date": 1_700_000_000}]}
    sites({"search/issues": issues, "search/advanced": question,
           "/answers/": {"items": [{"answer_id": 4, "body": "<p>The answer.</p>"}]}})

    found = lookups.look_up("LibError: it broke", "", repository="o/lib", first=("github issues",))["found"]

    assert [f["url"] for f in found] == ["https://github.com/o/lib/issues/0", "https://github.com/o/lib/issues/1",
                                         "https://stackoverflow.com/q/9"]
