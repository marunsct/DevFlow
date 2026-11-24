"""The product manager is shown what comparable products offer, only with its switch and the run owner's consent
(plan HK.10, LF.1305).

The product manager had no outside knowledge at all, where a person in the role looks at comparable products first
(`reports/research/2026-11-24-agents-that-work-like-a-team.md`, section (b)). It is the plan's doubtful item: the
searches must describe the product, and market suggestions invite scope growth. So: only the product's type leaves,
through the outbound gate; at most three searches, summarised once, each suggestion cited; a suggestion is never
scope without the brief; and with either key off the intake is exactly as before.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from app import switches
from app.agents.product_manager import ProductManagerOutput

BRIEF = """# LinkShelf

LinkShelf keeps the reading lists of the "Acme Reading Club".

## Acceptance criteria
- Users can save a link with a title
- Users can delete a saved link
"""

TYPE_REPLY = json.dumps({"product_type": "LinkShelf bookmark manager web app", "own_names": ["Acme Reading Club"]})
SUMMARY_REPLY = json.dumps({"suggestions": [
    {"feature": "Tags for saved links", "why": "Every compared bookmark manager lets links be tagged.", "sources": [1, 2]},
    {"feature": "Browser extension", "why": "Most offer saving from the browser.", "sources": [3]},
    {"feature": "Offline reading", "why": "Nothing cited.", "sources": [9]},
]})
RESULTS = [{"title": f"Bookmark manager {n}", "url": f"https://example.org/review-{n}",
            "content": "Tags, folders, a browser extension and full-text search."} for n in range(1, 4)]


class _Model:
    """The model endpoint's stand-in: answers in turn, and keeps each request."""

    def __init__(self, *replies: str) -> None:
        self.replies, self.requests = list(replies), []

    def invoke(self, messages: Any, **_: Any) -> AIMessage:
        self.requests.append("\n".join(str(m.content) for m in messages))
        return AIMessage(content=self.replies.pop(0) if self.replies else "")


class _Runs:
    def __init__(self) -> None:
        self.overrides: dict[str, dict[str, bool]] = {}

    def switch_overrides(self, run_id: str) -> dict[str, bool]:
        return dict(self.overrides.get(run_id, {}))


@pytest.fixture
def run(monkeypatch, tmp_path):
    """Inside run `run-r`, with a private search service whose answers a spy records."""
    runs, searches = _Runs(), []
    for name, value in {"SWITCH_OVERRIDES_FROM_SETTINGS": "on", "SEARXNG_URL": "http://search.invalid",
                        "WEB_SEARCH_ENABLED": "true", "DATA_DIR": str(tmp_path / "data")}.items():
        monkeypatch.setenv(name, value)
    for name in ("PRODUCT_RESEARCH", "INTAKE_ASKS_FIRST", "ASSUMPTIONS_GATE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.server.run_store.RunStore.shared", classmethod(lambda cls: runs))
    monkeypatch.setattr(switches, "stored", lambda name: None)
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-r")
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "run-r")

    def search_service(url: str, params: dict[str, Any] | None = None) -> tuple[int, str, str]:
        searches.append(dict(params or {}))
        return 200, json.dumps({"results": RESULTS}), "application/json"

    monkeypatch.setattr("app.tools.web_search._get", search_service)
    switches._RUN_OVERRIDES.clear()  # noqa: SLF001
    yield SimpleNamespace(runs=runs, searches=searches, root=tmp_path / "workspace")
    switches._RUN_OVERRIDES.clear()  # noqa: SLF001


def _intake(**fields: Any) -> ProductManagerOutput:
    return ProductManagerOutput(**{"product_name": "LinkShelf", "core_workflows": ["Save a link"],
                                   "success_measures": ["Users can save a link with a title"], **fields})


def _the_intake_stage(monkeypatch, run, model: Any, intake: ProductManagerOutput) -> tuple[str, dict[str, Any]]:
    """(the request the product manager's model is sent, the stage's update), the agent's model run stubbed."""
    from app.graph import workflow
    from app.graph.context import GraphContext
    from app.graph.nodes.planning import product_manager_node

    seen: dict[str, str] = {}

    def gated(state, config, *, stage_name, agent, initial_request, output_key, next_stage):
        seen["request"] = initial_request["messages"][-1]["content"]
        return {"product_intake": intake, "stage": next_stage}

    monkeypatch.setattr(workflow, "_run_gated_agent", gated)
    monkeypatch.setattr(workflow, "create_product_manager_agent", lambda **kwargs: object())
    run.root.mkdir(exist_ok=True)
    state = {"document": SimpleNamespace(text=BRIEF, source_type="markdown", truncated=False, truncation_note=""),
             "repository": SimpleNamespace(root_path=str(run.root), branch="main", commit="abc"), "decisions": []}
    ctx = GraphContext(model=None, judgement_model=None, planning_model=model, building_model=None,
                       checkpointer=None, repo_root=str(run.root))
    update = product_manager_node(state, {"configurable": {"thread_id": "t"}}, ctx)
    return seen["request"], update


def _both_keys(run, monkeypatch) -> None:
    monkeypatch.setenv("PRODUCT_RESEARCH", "on")
    run.runs.overrides["run-r"] = {"PRODUCT_RESEARCH_CONSENTED": True}


def test_with_the_switch_and_consent_the_intake_is_shown_cited_suggestions_from_searches_of_its_type_alone(
        monkeypatch, run):
    _both_keys(run, monkeypatch)

    request, _ = _the_intake_stage(monkeypatch, run, _Model(TYPE_REPLY, SUMMARY_REPLY), _intake())

    assert "Comparable products: suggestions the brief does not require" in request
    assert "[S1] Tags for saved links" in request and "https://example.org/review-1" in request
    assert "Offline reading" not in request, "a suggestion citing no result is dropped"
    assert "deferred scope" in request
    sent = [params["q"] for params in run.searches]
    assert 1 <= len(sent) <= 3
    assert all("bookmark manager" in q for q in sent)
    assert not any(word in q.lower() for q in sent for word in ("linkshelf", "acme", "reading club"))
    assert {params["categories"] for params in run.searches} == {"general"}


def test_each_query_sent_is_an_outbound_record_the_run_page_shows(monkeypatch, run):
    from app.observability.transcript import read_transcript

    _both_keys(run, monkeypatch)

    _the_intake_stage(monkeypatch, run, _Model(TYPE_REPLY, SUMMARY_REPLY), _intake())

    recorded = [r["sent"] for r in read_transcript("run-r", {"outbound"}) if r.get("channel") == "product research"]
    assert recorded and recorded == [params["q"] for params in run.searches]


@pytest.mark.parametrize("switch, consent, lookups", [
    ("off", True, None),
    ("on", False, None),
    ("on", None, None),
    ("on", True, "off"),
], ids=["switch off", "consent refused", "consent never given", "internet lookups off"])
def test_without_both_keys_the_intake_is_exactly_as_before(monkeypatch, run, switch, consent, lookups):
    baseline_request, baseline = _the_intake_stage(monkeypatch, run, _Model(), _intake(
        success_measures=["Users can save a link with a title", "Tags for saved links [S1]"]))
    monkeypatch.setenv("PRODUCT_RESEARCH", switch)
    own: dict[str, bool] = {} if consent is None else {"PRODUCT_RESEARCH_CONSENTED": consent}
    if lookups:
        from app.internet_lookups import switches_for

        own.update(switches_for(lookups))
    run.runs.overrides["run-r"] = own
    model = _Model(TYPE_REPLY, SUMMARY_REPLY)

    request, update = _the_intake_stage(monkeypatch, run, model, _intake(
        success_measures=["Users can save a link with a title", "Tags for saved links [S1]"]))

    assert request == baseline_request
    assert update["product_intake"] == baseline["product_intake"]
    assert run.searches == [] and model.requests == []
    assert not (run.root / ".harness" / "research" / "product-research.json").exists()


def test_a_suggestion_the_intake_put_in_scope_is_moved_to_deferred_scope_and_never_becomes_a_criterion(
        monkeypatch, run):
    from app.acceptance.criteria import number

    _both_keys(run, monkeypatch)
    written = _intake(success_measures=["Users can save a link with a title", "Tags for saved links [S1]"],
                      mvp_candidates=["Saving links", "A browser extension [S2]"])

    _, update = _the_intake_stage(monkeypatch, run, _Model(TYPE_REPLY, SUMMARY_REPLY), written)

    intake = update["product_intake"]
    assert not any("Tags" in m for m in intake.success_measures)
    assert intake.mvp_candidates == ["Saving links"]
    assert any(d.startswith("Tags for saved links") and "the brief does not require it" in d
               for d in intake.deferred_scope)
    assert not any("Tags" in c.text for c in number("A one-line brief.", intake))
    record = json.loads((run.root / ".harness" / "research" / "product-research.json").read_text())
    assert sorted(record["taken"]) == ["S1", "S2"]
    [decision] = [d for d in update["decisions"] if d["point"] == "product_research"]
    assert "S1" in decision["decision"] and "S2" in decision["decision"]


def test_a_suggestion_the_brief_already_names_stays_where_the_intake_put_it(monkeypatch, run):
    from app.agents.product_research import kept_as_suggestions

    suggestions = [{"id": "S1", "feature": "Delete a saved link", "why": "", "sources": [1]}]

    intake, taken, moved = kept_as_suggestions(
        _intake(core_workflows=["Delete a saved link [S1]"]), suggestions, "Users can delete a saved link.")

    assert intake.core_workflows == ["Delete a saved link (also common in comparable products: S1)"]
    assert moved == [] and list(taken) == ["S1"]


def test_the_research_is_done_once_a_run_however_often_the_intake_runs(monkeypatch, run):
    _both_keys(run, monkeypatch)
    _the_intake_stage(monkeypatch, run, _Model(TYPE_REPLY, SUMMARY_REPLY), _intake())
    searched, model = len(run.searches), _Model(TYPE_REPLY, SUMMARY_REPLY)

    request, _ = _the_intake_stage(monkeypatch, run, model, _intake())

    assert "[S1] Tags for saved links" in request
    assert len(run.searches) == searched and model.requests == []


def test_consent_is_read_from_the_run_alone_never_the_environment_or_the_admin_page(monkeypatch, run):
    from app.agents.product_research import consented

    monkeypatch.setenv("PRODUCT_RESEARCH_CONSENTED", "on")
    monkeypatch.setattr(switches, "stored", lambda name: True)

    assert consented() is False
    run.runs.overrides["run-r"] = {"PRODUCT_RESEARCH_CONSENTED": True}
    switches._RUN_OVERRIDES.clear()  # noqa: SLF001
    assert consented() is True


def test_what_the_model_is_told_avoids_the_banned_words(monkeypatch, run):
    import re

    from app.agents import product_research

    _both_keys(run, monkeypatch)
    model = _Model(TYPE_REPLY, SUMMARY_REPLY)
    request, _ = _the_intake_stage(monkeypatch, run, model, _intake())
    told = [request.split("--- Comparable products")[1], *model.requests]

    for text in told:
        own = text.replace(BRIEF[:6000], "")
        assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", own, re.I), own
    assert product_research.RULE in request


def _new_run(client, tmp_path) -> str:
    brief = tmp_path / "brief.md"
    brief.write_text("A product")
    with open(brief, "rb") as handle:
        return client.post("/api/runs", files=[("files", ("brief.md", handle, "text/plain"))]).json()["run_id"]


def test_a_run_started_with_consent_keeps_it_as_its_own_setting_and_no_switch_list_can_give_it(client, tmp_path):
    from app.server.run_store import RunStore

    consenting, without, smuggled = (_new_run(client, tmp_path) for _ in range(3))

    assert client.post(f"/api/runs/{consenting}/start", json={
        "product_research": True, "workspace_label": "consented"}).status_code == 202
    assert client.post(f"/api/runs/{without}/start", json={"workspace_label": "not-consented"}).status_code == 202
    assert client.post(f"/api/runs/{smuggled}/start", json={
        "switches": {"PRODUCT_RESEARCH_CONSENTED": True}}).status_code == 422

    assert RunStore.shared().switch_overrides(consenting) == {"PRODUCT_RESEARCH_CONSENTED": True}
    assert RunStore.shared().switch_overrides(without) == {}
