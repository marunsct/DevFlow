"""The security and testing advisers and the security reviewer get the framework's own current guidance (HK.9, LF.1303).

Measured (`reports/research/2026-11-24-agents-that-work-like-a-team.md`, section (b)): the consultants and reviewers
advised from training data only, while a person in those roles reads the framework's own recommendations for the
release in use. Behind `FRAMEWORK_GUIDANCE_FOR_ADVISERS` (off until measured), the stack's framework's security and
testing guidance for the release the project uses is read once per release - Context7 pinned to the version, else the
framework's own documentation when that release is the newest - checked to be about its topic, cut short, labelled,
and given to the security and testing specialists before the specification and to the security reviewer. Off, their
requests are as before and nothing is asked.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

def _a_stack():
    from app.agents.tools_models import TechnologyStack

    return TechnologyStack(language="python", framework="FastAPI", frontend_framework="", database="SQLite",
                           testing_framework="pytest")


def _the_selection():
    from app.agents.stack_selector import StackSelectorOutput

    return StackSelectorOutput(technology_stack=STACK, rationale="It fits.")


STACK = _a_stack()

SECURITY = {"infoSnippets": [{"content": "Use OAuth2PasswordBearer for token authentication; hash every password "
                                         "and keep secrets out of the code."}],
            "codeSnippets": [{"codeTitle": "Security dependency", "codeList": [
                {"language": "python", "code": "oauth2 = OAuth2PasswordBearer(tokenUrl='token')"}]}]}
TESTING = {"infoSnippets": [{"content": "Test with TestClient; override dependencies in each test, and use a "
                                        "fixture for the test database."}], "codeSnippets": []}


class Context7:
    """Context7 stood in for at the network's edge (`lookups._get`), recording each address asked."""

    def __init__(self, versions=("0.118.0", "0.110.0"), security=SECURITY):
        self.versions, self.security, self.asked = list(versions), security, []

    def __call__(self, url, headers, body=None):
        self.asked.append(url)
        if "/libs/search" in url:
            return 200, json.dumps({"results": [{"id": "/fastapi/fastapi", "versions": self.versions}]}), {}
        if "/context" in url:
            query = parse_qs(urlsplit(url).query)["query"][0]
            return 200, json.dumps(self.security if "security" in query else TESTING), {}
        return 404, "", {}

    def library_ids(self):
        return [parse_qs(urlsplit(u).query).get("libraryId", [""])[0] for u in self.asked if "/context?" in u]


@pytest.fixture
def framework(monkeypatch, tmp_path):
    """A FastAPI project the stack facts say runs 0.118.0, its newest; Context7 stood in for. Returns (root, spy)."""
    from app.tools import lookups

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("FRAMEWORK_GUIDANCE_FOR_ADVISERS", raising=False)
    spy = Context7()
    monkeypatch.setattr(lookups, "_get", spy)
    root = tmp_path / "workspace"
    (root / ".harness").mkdir(parents=True)
    (root / ".harness" / "stack-facts.json").write_text(json.dumps({"dependencies": [
        {"ecosystem": "pypi", "package": "fastapi", "version": "0.118.0", "newest": "0.118.0", "resolved": "0.118.0"}]}))
    return root, spy


def _consultant_s_request(root, role):
    """What the consulted `role` is sent, read where it leaves the stage (its agent and the model stood in for)."""
    from workflow_nodes import run_node

    sent = []

    def gated(state, config, *, initial_request, **kwargs):
        sent.append(initial_request["messages"][-1]["content"])
        return {}

    state = {"repository": SimpleNamespace(root_path=str(root)), "document": SimpleNamespace(text="A notes service."),
             "consultation_roles": [role], "product_intake": "Notes.",
             "stack_selection": _the_selection()}
    run_node("specialist_consultation", state, str(root), patches={
        "app.graph.workflow._run_gated_agent": gated,
        "app.graph.workflow.create_specialist_advice_agent": lambda *a, **k: MagicMock()})
    return sent[0]


def _security_reviewer_s_request(root):
    from app.agents.specialists import SpecialistOutput
    from workflow_nodes import run_node

    sent = []

    def gated(state, config, *, initial_request, **kwargs):
        sent.append(initial_request["messages"][-1]["content"])
        return {}

    (root / "app").mkdir(exist_ok=True)
    (root / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    state = {"repository": SimpleNamespace(root_path=str(root)), "stack_selection": _the_selection(),
             "specialist_outputs": {"specialist_backend_0": SpecialistOutput(changed_files=["app/main.py"])}}
    run_node("security_review", state, str(root), patches={
        "app.graph.workflow._run_gated_agent": gated,
        "app.graph.workflow.create_security_reviewer_agent": lambda *a, **k: MagicMock()})
    return sent[0]


def test_the_security_adviser_is_given_the_framework_s_security_guidance_for_its_release(framework, monkeypatch):
    root, context7 = framework
    monkeypatch.setenv("FRAMEWORK_GUIDANCE_FOR_ADVISERS", "on")

    request = _consultant_s_request(root, "security_reliability")

    assert "fastapi 0.118.0: its own guidance, for the release this project uses (security)" in request
    assert "OAuth2PasswordBearer" in request and "the brief decides what the product does" in request
    assert context7.library_ids() == ["/fastapi/fastapi/0.118.0"]


def test_the_testing_adviser_is_given_the_framework_s_testing_guidance(framework, monkeypatch):
    root, _ = framework
    monkeypatch.setenv("FRAMEWORK_GUIDANCE_FOR_ADVISERS", "on")

    request = _consultant_s_request(root, "testing")

    assert "(testing)" in request and "TestClient" in request
    assert "OAuth2PasswordBearer" not in request


def test_another_adviser_is_given_none(framework, monkeypatch):
    root, context7 = framework
    monkeypatch.setenv("FRAMEWORK_GUIDANCE_FOR_ADVISERS", "on")

    request = _consultant_s_request(root, "database")

    assert "its own guidance" not in request
    assert context7.asked == []


def test_the_security_reviewer_is_given_the_framework_s_security_guidance(framework, monkeypatch):
    root, _ = framework
    monkeypatch.setenv("FRAMEWORK_GUIDANCE_FOR_ADVISERS", "on")

    request = _security_reviewer_s_request(root)

    assert "(security)" in request and "OAuth2PasswordBearer" in request


def test_off_the_advisers_and_the_reviewer_are_sent_what_they_were_and_nothing_is_asked(framework, monkeypatch,
                                                                                        tmp_path):
    root, context7 = framework
    monkeypatch.setenv("FRAMEWORK_GUIDANCE_FOR_ADVISERS", "off")

    consulted, reviewed = _consultant_s_request(root, "security_reliability"), _security_reviewer_s_request(root)

    assert "its own guidance" not in consulted and "its own guidance" not in reviewed
    assert context7.asked == []


def test_the_guidance_is_read_once_per_framework_release(framework, monkeypatch):
    from app.stacks import framework_guidance

    root, context7 = framework
    monkeypatch.setenv("FRAMEWORK_GUIDANCE_FOR_ADVISERS", "on")
    first = framework_guidance.note(STACK, "security", root)
    asked = len(context7.asked)

    again = framework_guidance.note(STACK, "security", root)

    assert again == first and len(context7.asked) == asked


def test_guidance_that_is_not_about_its_topic_is_not_given(framework, monkeypatch):
    from app.stacks import framework_guidance
    from app.tools import lookups

    root, _ = framework
    monkeypatch.setenv("FRAMEWORK_GUIDANCE_FOR_ADVISERS", "on")
    monkeypatch.setattr(lookups, "_get", Context7(security={"infoSnippets": [{"content": "Path parameters are typed."}]}))

    assert framework_guidance.note(STACK, "security", root) == ""


def test_without_the_release_in_context7_the_framework_s_own_documentation_is_read_for_the_newest(framework,
                                                                                                 monkeypatch):
    from app.stacks import framework_guidance
    from app.tools import docs, lookups

    root, _ = framework
    monkeypatch.setenv("FRAMEWORK_GUIDANCE_FOR_ADVISERS", "on")
    monkeypatch.setattr(lookups, "_get", Context7(versions=["0.100.0"]))
    readme = "# FastAPI\n\n## Security\nUse OAuth2 with password hashing; keep secrets in settings; check authorization.\n"
    monkeypatch.setattr(docs, "_fetch", lambda url: (200, json.dumps({"info": {"description": readme}}), "application/json")
                        if url == "https://pypi.org/pypi/fastapi/json" else (404, "", ""))

    note = framework_guidance.note(STACK, "security", root)

    assert "fastapi's own documentation, for 0.118.0" in note and "password hashing" in note


def test_an_older_release_is_never_given_the_newest_s_documentation(framework, monkeypatch):
    from app.stacks import framework_guidance
    from app.tools import docs, lookups

    root, _ = framework
    monkeypatch.setenv("FRAMEWORK_GUIDANCE_FOR_ADVISERS", "on")
    (root / ".harness" / "stack-facts.json").write_text(json.dumps({"dependencies": [
        {"ecosystem": "pypi", "package": "fastapi", "version": "0.99.0", "newest": "0.118.0", "resolved": "0.99.0"}]}))
    monkeypatch.setattr(lookups, "_get", Context7(versions=["0.118.0"]))
    read = []
    monkeypatch.setattr(docs, "_fetch", lambda url: read.append(url) or (404, "", ""))

    assert framework_guidance.note(STACK, "security", root) == ""
    assert read == []


def test_the_note_names_no_product_word(framework, monkeypatch):
    from app.stacks import framework_guidance

    root, _ = framework
    monkeypatch.setenv("FRAMEWORK_GUIDANCE_FOR_ADVISERS", "on")

    note = framework_guidance.note(STACK, "security", root)

    assert note and not BANNED.search(note)
